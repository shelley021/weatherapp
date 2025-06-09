import sys
import os
import time  # 新增：用于推送频率控制

# 动态添加项目根目录到 sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)
print(f"[DEBUG] 已添加项目根目录到 sys.path: {project_root}")

import yaml
from autodebug.config import load_config
from autodebug.log_retriever import get_actions_logs
from autodebug.log_parser import parse_log_content
from autodebug.fix_applier import analyze_and_fix
from autodebug.history import load_processed_runs, save_processed_runs, load_fix_history, save_fix_history
from autodebug.workflow_validator import validate_and_fix_debug_yml
from autodebug.git_utils import push_changes

def main():
    """主函数，仅负责协调各个模块的调用"""
    config = load_config()
    github_token = config['GITHUB_TOKEN']
    deepseek_api_key = config['DEEPSEEK_API_KEY']
    branch = config['GITHUB_BRANCH']
    workflow_file_path = config['WORKFLOW_FILE']
    fix_history_file = config['FIX_HISTORY_FILE']
    processed_runs_file = config['PROCESSED_RUNS_FILE']
    repo = config['REPO']
    max_iterations = 10
    default_error_count = 0
    DEFAULT_ERROR_LIMIT = 3
    same_run_count = 0
    last_run_id = None
    startup_failure_count = 0
    apk_failure_count = 0
    last_push_time = 0  # 新增：记录上次推送时间
    push_interval = 600  # 新增：推送间隔，10分钟（600秒）

    if not validate_and_fix_debug_yml(workflow_file_path):
        print("[ERROR] 无法修复 debug.yml，退出")
        return

    processed_runs = load_processed_runs(processed_runs_file)
    if not isinstance(processed_runs, dict):
        print("[WARNING] processed_runs 格式不正确，初始化为空字典")
        processed_runs = {}
    fix_history = load_fix_history(fix_history_file)
    if not isinstance(fix_history, dict):
        print("[WARNING] fix_history 不是字典，初始化为空字典")
        fix_history = {}

    iteration = 1
    while iteration <= max_iterations:
        print(f"\n[DEBUG] 开始第 {iteration} 次迭代")

        # 获取最近的运行日志
        result = get_actions_logs(
            repo, github_token, branch, None, iteration, workflow_file_path, 
            processed_run_ids=processed_runs, 
            push_changes_func=lambda msg, run_id, branch: push_changes(msg, run_id, branch, config)
        )

        # 检查返回值是否有效
        if result is None:
            print("[ERROR] get_actions_logs 返回 None，可能是日志获取失败，跳过本次迭代")
            iteration += 1
            continue

        log_content, state, conclusion, annotations_error, has_critical_error, successful_steps, error_details, run_id, annotations = result

        print(f"[DEBUG] 工作流状态: {state}, 结果: {conclusion}")

        # 如果没有日志或没有运行，触发新运行
        if not log_content or not run_id:
            print("[DEBUG] 未找到工作流运行日志，触发新运行...")
            with open(workflow_file_path, "r") as f:
                workflow_content = yaml.safe_load(f)
            steps = workflow_content["jobs"]["build"]["steps"]
            step_exists = any(step.get("name") == "Initial Trigger Step" if isinstance(step, dict) else False for step in steps)
            if not step_exists:
                steps.append({"name": "Initial Trigger Step", "run": "echo 'Initial trigger to start a new workflow'"})
                with open(workflow_file_path, "w") as f:
                    yaml.safe_dump(workflow_content, f)
                print("[DEBUG] 已添加初始触发步骤: Initial Trigger Step")
            else:
                print("[DEBUG] Initial Trigger Step 已存在，跳过添加")
            # 添加推送频率限制
            current_time = time.time()
            if current_time - last_push_time < push_interval:
                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                time.sleep(push_interval - (current_time - last_push_time))
            if not push_changes(f"AutoDebug: Trigger new run (iteration {iteration})", None, branch, config):
                print("[ERROR] 推送初始触发更改失败，但已保存更改到本地，继续执行后续逻辑...")
            last_push_time = time.time()  # 更新推送时间
            iteration += 1
            continue

        # 检查是否生成了 APK
        apk_generated = False
        if log_content:
            apk_path = os.path.join(os.path.dirname(workflow_file_path), "bin", "weatherapp-0.1.apk")
            apk_generated = os.path.exists(apk_path)
            print(f"[DEBUG] 检查 APK 是否生成: {apk_generated} (路径: {apk_path})")

        run_id = str(annotations[0]["run_id"]) if annotations else None
        print(f"正在检查运行 {run_id} (状态: {state}, 结果: {conclusion})")

        if last_run_id == run_id:
            same_run_count += 1
        else:
            same_run_count = 1
            last_run_id = run_id

        if run_id and run_id not in processed_runs:
            processed_runs[run_id] = {"processed": True, "success": False}
        elif run_id:
            print(f"[DEBUG] 运行 {run_id} 已处理，检查是否需要推送")
            has_successful_fix = any(
                entry.get("successful_fix") for entry in fix_history.values() if "successful_fix" in entry
            )
            if has_successful_fix:
                print("[DEBUG] 发现成功的修复，执行推送")
                current_time = time.time()
                if current_time - last_push_time < push_interval:
                    print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                    time.sleep(push_interval - (current_time - last_push_time))
                if not push_changes(f"AutoDebug: Push changes after successful fix for run {run_id}", run_id, branch, config):
                    print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
                last_push_time = time.time()  # 更新推送时间
                break
            else:
                unresolved_errors = fix_history.get("untried_errors", [])
                if unresolved_errors:
                    print(f"[DEBUG] 发现未解决的错误: {unresolved_errors}，CLEARING HISTORY AND EXITING")
                    fix_history["untried_errors"] = []
                    save_fix_history(fix_history, fix_history_file)
                    break
                else:
                    print("[DEBUG] 无未解决的错误，继续处理")

        save_processed_runs(processed_runs, processed_runs_file)

        if same_run_count >= DEFAULT_ERROR_LIMIT:
            print(f"[DEBUG] 重复处理运行 {run_id} 达到 {same_run_count} 次，跳过此运行")
            iteration += 1
            continue

        if iteration == 5:
            print("[DEBUG] 达到 5 次迭代，强制应用通用修复以产生新日志")
            additional_fixes = [
                {"name": "Check Network Connectivity", "action": "add_step", "step": "- name: Check Network Connectivity\n  run: ping -c 4 google.com || echo '网络连接失败，请检查网络'"},
                {"name": "Clean Build Cache", "action": "add_step", "step": "- name: Clean Build Cache\n  run: rm -rf ~/.buildozer/cache && buildozer android clean"}
            ]
            for fix in additional_fixes:
                with open(workflow_file_path, "r") as f:
                    workflow_content = yaml.safe_load(f)
                steps = workflow_content["jobs"]["build"]["steps"]
                new_steps = []
                for step in steps:
                    if isinstance(step, dict) and step.get("name") == fix["name"]:
                        continue
                    new_steps.append(step)
                new_steps.append(yaml.safe_load(fix["step"]))
                workflow_content["jobs"]["build"]["steps"] = new_steps
                with open(workflow_file_path, "w") as f:
                    yaml.safe_dump(workflow_content, f)
                print(f"[DEBUG] 已重新应用通用修复: {fix['name']}")
                current_time = time.time()
                if current_time - last_push_time < push_interval:
                    print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                    time.sleep(push_interval - (current_time - last_push_time))
                if not push_changes(f"AutoDebug: Apply fix '{fix['name']}' for run {run_id} (iteration {iteration})", run_id, branch, config):
                    print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
                last_push_time = time.time()  # 更新推送时间
                break
            iteration = 1
            continue

        if state != "completed":
            print(f"[DEBUG] 运行 {run_id} 状态未完成 (status: {state})，跳过")
            iteration += 1
            continue

        errors, error_contexts, exit_codes, new_error_patterns, warnings, error_patterns = parse_log_content(
            log_content, workflow_file_path, annotations_error, error_details, successful_steps, config
        )

        if not errors and not annotations_error:
            errors = ["No errors extracted from log"]
            default_error_count += 1
            print(f"[DEBUG] 默认错误计数: {default_error_count}")
        else:
            default_error_count = 0

        # 如果工作流失败但未生成 APK，即使未提取到错误，也触发修复逻辑
        if conclusion == "failure" and not apk_generated:
            apk_failure_count += 1
            print(f"[DEBUG] 工作流完成但未生成 APK，当前计数: {apk_failure_count}")
            if apk_failure_count >= 1:
                print("[DEBUG] 检测到工作流失败且未生成 APK，触发修复逻辑...")
                errors = fix_history.get("untried_errors", []) if fix_history.get("untried_errors") else ["Failed to generate APK"]
                error_contexts = [{"context": "No APK generated in bin/weatherapp-0.1.apk"}] * len(errors)
                error_patterns = [{"pattern": ".*", "fix": []}]  # 通用错误模式
                job_id = None  # 假设 job_id 未知

                # 定义网络相关的本地修复
                additional_fixes = [
                    {"name": "Check Network Connectivity", "action": "add_step", "step": "- name: Check Network Connectivity\n  run: ping -c 4 google.com || echo '网络连接失败，请检查网络'"},
                    {"name": "Retry NDK Download with Delay", "action": "add_step", "step": "- name: Retry NDK Download with Delay\n  run: buildozer android debug || sleep 10 && buildozer android debug"}
                ]

                # 尝试 DeepSeek API 修复
                success = analyze_and_fix(
                    workflow_file_path, errors, error_patterns, lambda msg, run_id, branch: push_changes(msg, run_id, branch, config),
                    iteration, branch, fix_history_file, last_run_id, job_id, annotations_error, error_contexts, successful_steps, config, log_content,
                    additional_fixes=additional_fixes
                )
                if success:
                    print("[DEBUG] DeepSeek API 或本地修复成功，推送新 debug.yml...")
                    current_time = time.time()
                    if current_time - last_push_time < push_interval:
                        print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                        time.sleep(push_interval - (current_time - last_push_time))
                    if not push_changes("AutoDebug: Apply fix for APK generation", None, branch, config):
                        print("[ERROR] 推送修复失败，但已保存更改到本地，继续执行后续逻辑...")
                    last_push_time = time.time()  # 更新推送时间
                else:
                    print("[DEBUG] DeepSeek API 修复失败，尝试本地网络修复...")
                    local_fix_applied = False
                    for fix in additional_fixes:
                        with open(workflow_file_path, "r") as f:
                            workflow_content = yaml.safe_load(f)
                        steps = workflow_content["jobs"]["build"]["steps"]
                        if not any(step.get("name") == fix["name"] for step in steps if isinstance(step, dict)):
                            steps.append(yaml.safe_load(fix["step"]))
                            workflow_content["jobs"]["build"]["steps"] = steps
                            with open(workflow_file_path, "w") as f:
                                yaml.safe_dump(workflow_content, f)
                            print(f"[DEBUG] 已应用本地修复: {fix['name']}")
                            current_time = time.time()
                            if current_time - last_push_time < push_interval:
                                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                                time.sleep(push_interval - (current_time - last_push_time))
                            if push_changes(f"AutoDebug: Apply local fix '{fix['name']}' for run {run_id} (iteration {iteration})", run_id, branch, config):
                                local_fix_applied = True
                                last_push_time = time.time()  # 更新推送时间
                                break
                            else:
                                print("[ERROR] 推送本地修复失败，但已保存更改到本地，继续尝试下一个修复...")
                    if not local_fix_applied:
                        print("[DEBUG] 所有本地修复尝试失败，推送完整 debug.yml 作为最后手段...")
                        complete_workflow = {
                            "name": "WeatherApp CI",
                            "on": {
                                "push": {"branches": ["main"]},
                                "pull_request": {"branches": ["main"]}
                            },
                            "permissions": {"contents": "write"},
                            "jobs": {
                                "build": {
                                    "runs-on": "Ubuntu-latest",
                                    "steps": [
                                        {"uses": "actions/checkout@v4"},
                                        {
                                            "name": "Set up JDK 17",
                                            "uses": "actions/setup-java@v3",
                                            "with": {
                                                "distribution": "temurin",
                                                "java-version": "17"
                                            }
                                        },
                                        {
                                            "name": "Set up Python",
                                            "uses": "actions/setup-python@v5",
                                            "with": {
                                                "python-version": "3.10"
                                            }
                                        },
                                        {
                                            "name": "Install missing libtinfo package",
                                            "run": """Ubuntu_version=$(lsb_release -rs)
if [[ "$Ubuntu_version" == "22.04" || "$Ubuntu_version" == "24.04" ]]; then
  sudo apt-get update -y
  sudo apt-get install -y libtinfo6
else
  sudo apt-get update -y
  sudo apt-get install -y libtinfo5
fi"""
                                        },
                                        {
                                            "name": "Install system dependencies",
                                            "run": """sudo apt-get update -y
sudo apt-get install -y git zip unzip python3-pip autoconf libtool pkg-config
sudo apt-get install -y zlib1g-dev libncurses5-dev libncursesw5-dev
sudo apt-get install -y cmake libffi-dev libssl-dev
sudo apt-get install -y libltdl-dev build-essential python3-dev python3-venv
sudo apt-get install -y libnss3-dev libnss3-tools"""
                                        },
                                        {
                                            "name": "Configure pip mirror",
                                            "run": """pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
pip config set global.trusted-host mirrors.aliyun.com"""
                                        },
                                        {
                                            "name": "Install Python dependencies",
                                            "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
pip install python-for-android"""
                                        },
                                        {
                                            "name": "Set up Android SDK",
                                            "uses": "android-actions/setup-android@v3",
                                            "with": {
                                                "accept-android-sdk-licenses": True,
                                                "cmdline-tools-version": "latest",
                                                "packages": "build-tools;34.0.0 platform-tools platforms;android-34 ndk;25.2.9519653"
                                            }
                                        },
                                        {
                                            "name": "Initialize Buildozer",
                                            "run": """buildozer init
cat << 'EOF' > buildozer.spec
[app]
title = WeatherApp
package.name = weatherapp
package.domain = org.weatherapp
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3,kivy==2.3.1,requests==2.25.1,certifi
android.permissions = INTERNET
android.api = 34
android.minapi = 21
android.ndk = 25.2.9519653
android.ndk_path = $ANDROID_NDK_HOME
android.sdk_path = $ANDROID_HOME
android.accept_sdk_license = True
orientation = portrait
fullscreen = 0
log_level = 2
p4a.branch = master
EOF"""
                                        },
                                        {
                                            "name": "Prepare python-for-android",
                                            "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                                        },
                                        {
                                            "name": "Build APK",
                                            "env": {
                                                "OPENWEATHER_API_KEY": "${{ secrets.OPENWEATHER_API_KEY }}",
                                                "P4A_RELEASE_KEYALIAS": "${{ secrets.P4A_RELEASE_KEYALIAS }}",
                                                "P4A_RELEASE_KEYALIAS_PASSWD": "${{ secrets.P4A_RELEASE_KEYALIAS_PASSWD }}",
                                                "P4A_RELEASE_KEYSTORE": "${{ secrets.P4A_RELEASE_KEYSTORE }}",
                                                "P4A_RELEASE_KEYSTORE_PASSWD": "${{ secrets.P4A_RELEASE_KEYSTORE_PASSWD }}"
                                            },
                                            "run": """export CFLAGS="-Wno-error=implicit-function-declaration -Wno-error=array-bounds -Wno-error=deprecated-declarations"
export CPPFLAGS="-D_GNU_SOURCE -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=700"
export LDFLAGS="-lnsl -lresolv -lgssapi_krb5"
buildozer android clean
buildozer -v android debug deploy 2>&1 | tee build.log
if [ ${PIPESTATUS[0]} -ne 0 ]; then
  cat build.log
  exit 1
fi"""
                                        },
                                        {
                                            "name": "Verify Build Log",
                                            "if": "always()",
                                            "run": """if [ -f build.log ]; then
  echo "Build log exists, checking for errors..."
  if grep -q -E "ERROR:|FAILED" build.log; then
    echo "Errors found in build log:"
    grep -E "ERROR:|FAILED" build.log
    exit 1
  else
    echo "No critical errors found in build log"
  fi
else
  echo "No build log found"
  exit 1
fi"""
                                        },
                                        {
                                            "name": "Save Build Log",
                                            "if": "always()",
                                            "uses": "actions/upload-artifact@v4",
                                            "with": {
                                                "name": "build-log",
                                                "path": "build.log",
                                                "retention-days": 1
                                            }
                                        },
                                        {
                                            "name": "Upload APK",
                                            "if": "success()",
                                            "uses": "actions/upload-artifact@v4",
                                            "with": {
                                                "if-no-files-found": "error",
                                                "name": "weatherapp-apk",
                                                "path": "bin/weatherapp-*.apk",
                                                "retention-days": 1
                                            }
                                        },
                                        {
                                            "name": "Initial Trigger Step",
                                            "run": "echo 'Initial trigger to start a new workflow'"
                                        }
                                    ]
                                }
                            }
                        }
                        with open(workflow_file_path, "w") as f:
                            yaml.safe_dump(complete_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                        print("[DEBUG] 已更新本地 debug.yml 文件")
                        current_time = time.time()
                        if current_time - last_push_time < push_interval:
                            print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                            time.sleep(push_interval - (current_time - last_push_time))
                        if not push_changes("AutoDebug: Force push complete debug.yml to resolve startup_failure or APK failure", None, branch, config):
                            print("[ERROR] 推送完整 debug.yml 失败，但已保存到本地，继续执行后续逻辑...")
                        last_push_time = time.time()  # 更新推送时间
                        fix_history["untried_errors"] = []
                        save_fix_history(fix_history, fix_history_file)
                        break
            iteration += 1
            continue

        if conclusion != "failure":
            print(f"[DEBUG] 运行 {run_id} 结果不是失败 (conclusion: {conclusion})，触发新运行...")
            current_time = time.time()
            if current_time - last_push_time < push_interval:
                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                time.sleep(push_interval - (current_time - last_push_time))
            if not push_changes(f"AutoDebug: Trigger new run after non-failure (iteration {iteration})", run_id, branch, config):
                print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
            last_push_time = time.time()  # 更新推送时间
            iteration += 1
            continue

        errors, error_contexts, exit_codes, new_error_patterns, warnings, error_patterns = parse_log_content(
            log_content, workflow_file_path, annotations_error, error_details, successful_steps, config
        )

        if not errors and not annotations_error:
            errors = ["No errors extracted from log"]
            default_error_count += 1
            print(f"[DEBUG] 默认错误计数: {default_error_count}")
        else:
            default_error_count = 0

        additional_fixes = [
            {"name": "Set Download Timeout", "action": "add_step", "step": "- name: Set Download Timeout\n  run: export BUILDOCZER_TIMEOUT=600\n  env:\n    BUILDOCZER_TIMEOUT: 600"},
            {"name": "Use Cached NDK", "action": "add_step", "step": "- name: Use Cached NDK\n  run: buildozer android use_cached_ndk"},
            {"name": "Switch NDK Mirror", "action": "modify_step", "step": "android.ndk_path=https://dl.google.com/android/repository/android-ndk-r25c-linux.zip", "target": "Retry Android NDK Download"},
            {"name": "Clean Disk Space", "action": "add_step", "step": "- name: Clean Disk Space\n  run: rm -rf /tmp/* && docker system prune -a --force"},
            {"name": "Clean Build Cache", "action": "add_step", "step": "- name: Clean Build Cache\n  run: rm -rf ~/.buildozer/cache && buildozer android clean"},
            {"name": "Force NDK Redownload", "action": "add_step", "step": "- name: Force NDK Redownload\n  run: rm -rf ~/.buildozer/android/platform/android-ndk-* && buildozer android debug"},
            {"name": "Check Network Connectivity", "action": "add_step", "step": "- name: Check Network Connectivity\n  run: ping -c 4 google.com || echo '网络连接失败，请检查网络'"},
            {"name": "Optimize Disk Space Check", "action": "modify_step", "step": "- name: Check Disk Space Before Build\n  run: df -h && du -h /tmp -d 1 --no-dereference 2>/dev/null || echo '无法检查 /tmp 目录'", "target": "Check Disk Space Before Build"},
            {"name": "Optimize Disk Space Check After", "action": "modify_step", "step": "- name: Check Disk Space After Build\n  run: df -h && du -h /tmp -d 1 --no-dereference 2>/dev/null || echo '无法检查 /tmp 目录'", "target": "Check Disk Space After Build"},
            {"name": "Set Network Proxy", "action": "add_step", "step": "- name: Set Network Proxy\n  run: export HTTP_PROXY=http://proxy.example.com:8080 && export HTTPS_PROXY=http://proxy.example.com:8080"},
            {"name": "Retry Build", "action": "add_step", "step": "- name: Retry Build\n  run: buildozer android debug || buildozer android debug"},
            {"name": "Clean Dependency Cache", "action": "add_step", "step": "- name: Clean Dependency Cache\n  run: pip cache purge"},
            {"name": "Update Dependencies", "action": "add_step", "step": "- name: Update Dependencies\n  run: pip install --upgrade pip setuptools kivy buildozer"},
            {"name": "Skip Permission Denied Directories", "action": "modify_step", "step": "- name: Check Disk Space Before Build\n  run: df -h && du -h /tmp -d 1 --exclude=/tmp/systemd-private-* --exclude=/tmp/snap-private-tmp 2>/dev/null || true", "target": "Check Disk Space Before Build"},
            {"name": "Check Network and Retry NDK Download", "action": "add_step", "step": "- name: Check Network and Retry NDK Download\n  run: ping -c 4 google.com || echo '网络连接失败，请检查网络'; rm -rf /tmp/* && buildozer android debug"},
            {"name": "Verify Buildozer Config", "action": "add_step", "step": "- name: Verify Buildozer Config\n  run: buildozer android debug --verbose"},
            {"name": "Clean Temp Files Before Download", "action": "add_step", "step": "- name: Clean Temp Files Before Download\n  run: rm -rf /tmp/* || true"},
            {"name": "Retry NDK Download with Delay", "action": "add_step", "step": "- name: Retry NDK Download with Delay\n  run: buildozer android debug || sleep 10 && buildozer android debug"},
            {"name": "Clean Build Cache and Retry", "action": "add_step", "step": "- name: Clean Build Cache and Retry\n  run: rm -rf ~/.buildozer/cache && buildozer android clean && buildozer android debug"},
            {"name": "Install Android SDK Tools", "action": "add_step", "step": "- name: Install Android SDK Tools\n  run: yes | sudo apt-get install -y openjdk-17-jdk\n    export ANDROID_HOME=$HOME/android-sdk\n    mkdir -p $ANDROID_HOME\n    wget -q https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip -O commandlinetools.zip\n    unzip -q commandlinetools.zip -d $ANDROID_HOME\n    mv $ANDROID_HOME/cmdline-tools $ANDROID_HOME/cmdline-tools-latest\n    echo \"export PATH=\\$PATH:$ANDROID_HOME/cmdline-tools-latest/bin\" >> $GITHUB_ENV\n    yes | $ANDROID_HOME/cmdline-tools-latest/bin/sdkmanager --sdk_root=$ANDROID_HOME \"platform-tools\" \"build-tools;34.0.0\" \"platforms;android-33\""},
            {"name": "Install Buildozer", "action": "add_step", "step": "- name: Install Buildozer\n  run: pip install buildozer==1.5.0"},
            {"name": "Initialize Buildozer", "action": "add_step", "step": "- name: Initialize Buildozer\n  run: buildozer init\n    cat << 'EOF' > buildozer.spec\n[app]\ntitle = WeatherApp\npackage.name = weatherapp\npackage.domain = org.weatherapp\nsource.dir = .\nsource.include_exts = py,png,jpg,kv,atlas\nversion = 0.1\nrequirements = python3,kivy==2.3.1,requests==2.25.1,certifi\nandroid.permissions = INTERNET\nandroid.api = 33\nandroid.minapi = 21\nandroid.ndk = 25c\nandroid.ndk_path = ${ANDROID_NDK_HOME}\nandroid.accept_sdk_license = True\norientation = portrait\nfullscreen = 0\nlog_level = 2\np4a.branch = master\nEOF"},
            {"name": "Add Checkout", "action": "add_step", "step": "- name: Add Checkout\n  uses: actions/checkout@v4"},
            {"name": "Install Missing Libtinfo Package", "action": "add_step", "step": "- name: Install Missing Libtinfo Package\n  run: Ubuntu_version=$(lsb_release -rs)\n    if [[ \"$Ubuntu_version\" == \"22.04\" || \"$Ubuntu_version\" == \"24.04\" ]]; then\n        sudo apt-get update\n        sudo apt-get install -y libtinfo6\n    else\n        sudo apt-get update\n        sudo apt-get install -y libtinfo5\n    fi"},
            {"name": "Accept Android Licenses", "action": "add_step", "step": "- name: Accept Android Licenses\n  run: yes | $ANDROID_HOME/cmdline-tools-latest/bin/sdkmanager --sdk_root=$ANDROID_HOME --licenses"},
            {"name": "Create Missing Directory", "action": "add_step", "step": "- name: Create Missing Directory\n  run: mkdir -p $ANDROID_HOME/ndk"},
            {"name": "Install Kivy", "action": "add_step", "step": "- name: Install Kivy\n  run: pip install kivy==2.3.1"},
            {"name": "Install Java", "action": "add_step", "step": "- name: Install Java\n  run: sudo apt-get install -y openjdk-17-jdk"},
            {"name": "Install Pip", "action": "add_step", "step": "- name: Install Pip\n  run: sudo apt-get install -y python3-pip"},
            {"name": "Install CMake", "action": "add_step", "step": "- name: Install CMake\n  run: sudo apt-get install -y cmake"},
            {"name": "Install Unzip", "action": "add_step", "step": "- name: Install Unzip\n  run: sudo apt-get install -y unzip"},
            {"name": "Install Wget", "action": "add_step", "step": "- name: Install Wget\n  run: sudo apt-get install -y wget"},
            {"name": "Increase Swap Space", "action": "add_step", "step": "- name: Increase Swap Space\n  run: sudo fallocate -l 2G /swapfile\n    sudo chmod 600 /swapfile\n    sudo mkswap /swapfile\n    sudo swapon /swapfile"},
            {"name": "Update Package Index", "action": "add_step", "step": "- name: Update Package Index\n  run: sudo apt-get update --allow-insecure-repositories"}
        ]

        all_fixed = True
        for error in errors:
            try:
                print(f"[DEBUG] 正在分析和修复错误: {error}")
                fixed = analyze_and_fix(
                    workflow_file_path, [error], error_patterns, lambda msg, run_id, branch: push_changes(msg, run_id, branch, config),
                    iteration, branch, fix_history_file, run_id, job_id, annotations_error, error_contexts, successful_steps, config, log_content,
                    additional_fixes=additional_fixes
                )
                print(f"[DEBUG] 修复结果: {'成功' if fixed else '失败'}")
                if not fixed:
                    all_fixed = False
                    print(f"[DEBUG] 错误 {error} 修复失败")
                    if "untried_errors" not in fix_history:
                        fix_history["untried_errors"] = []
                    if error not in fix_history["untried_errors"]:
                        fix_history["untried_errors"].append(error)
                    if error == "No errors extracted from log":
                        print("[DEBUG] 默认错误未修复，检查是否需要强制推送")
                        if default_error_count >= DEFAULT_ERROR_LIMIT:
                            print(f"[DEBUG] 默认错误处理次数达到上限 ({DEFAULT_ERROR_LIMIT})，强制应用通用修复")
                            for fix in additional_fixes:
                                if fix["name"] == "Check Network Connectivity":
                                    with open(workflow_file_path, "r") as f:
                                        workflow_content = yaml.safe_load(f)
                                    steps = workflow_content["jobs"]["build"]["steps"]
                                    new_steps = []
                                    for step in steps:
                                        if isinstance(step, dict) and step.get("name") == fix["name"]:
                                            continue
                                        new_steps.append(step)
                                    new_steps.append(yaml.safe_load(fix["step"]))
                                    workflow_content["jobs"]["build"]["steps"] = new_steps
                                    with open(workflow_file_path, "w") as f:
                                        yaml.safe_dump(workflow_content, f)
                                    print(f"[DEBUG] 已重新应用通用修复: {fix['name']}")
                                    current_time = time.time()
                                    if current_time - last_push_time < push_interval:
                                        print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                                        time.sleep(push_interval - (current_time - last_push_time))
                                    if not push_changes(f"AutoDebug: Apply fix '{fix['name']}' for run {run_id} (iteration {iteration})", run_id, branch, config):
                                        print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
                                    last_push_time = time.time()  # 更新推送时间
                                    all_fixed = True
                                    default_error_count = 0
                                    break
                                else:
                                    print(f"[DEBUG] Check Network Connectivity 已存在，尝试其他修复")
                                    for alt_fix in additional_fixes:
                                        if alt_fix["name"] == "Clean Build Cache":
                                            new_steps = []
                                            for step in steps:
                                                if isinstance(step, dict) and step.get("name") == alt_fix["name"]:
                                                    continue
                                                new_steps.append(step)
                                            new_steps.append(yaml.safe_load(alt_fix["step"]))
                                            workflow_content["jobs"]["build"]["steps"] = new_steps
                                            with open(workflow_file_path, "w") as f:
                                                yaml.safe_dump(workflow_content, f)
                                            print(f"[DEBUG] 已重新应用通用修复: {alt_fix['name']}")
                                            current_time = time.time()
                                            if current_time - last_push_time < push_interval:
                                                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                                                time.sleep(push_interval - (current_time - last_push_time))
                                            if not push_changes(f"AutoDebug: Apply fix '{alt_fix['name']}' for run {run_id} (iteration {iteration})", run_id, branch, config):
                                                print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
                                            last_push_time = time.time()  # 更新推送时间
                                            all_fixed = True
                                            default_error_count = 0
                                            break
                                    if not all_fixed:
                                        print("[DEBUG] 所有通用修复已存在，跳出循环")
                                        break
                else:
                    print(f"[DEBUG] 错误 {error} 修复成功")
                    default_error_count = 0
            except Exception as e:
                print(f"[ERROR] 修复错误 {error} 时发生异常: {e}")
                all_fixed = False
                error_context = error_contexts[errors.index(error)]["context"]
                print(f"[INFO] 错误 {error} 无法自动修复，请手动检查:")
                print(f"[INFO] 错误上下文:\n{error_context}")
                print("[INFO] 建议: 检查日志中的错误信息，可能需要调整代码或配置。")

        if all_fixed:
            print("[DEBUG] 所有错误修复已应用，推送并退出...")
            current_time = time.time()
            if current_time - last_push_time < push_interval:
                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                time.sleep(push_interval - (current_time - last_push_time))
            if not push_changes(f"AutoDebug: Push changes after successful fix for run {run_id} (iteration {iteration})", run_id, branch, config):
                print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
            last_push_time = time.time()  # 更新推送时间
            processed_runs[run_id]["success"] = True
        else:
            print("[DEBUG] 未找到所有错误的有效修复，推送并退出以验证...")
            current_time = time.time()
            if current_time - last_push_time < push_interval:
                print(f"[DEBUG] 推送频率过高，等待 {push_interval - (current_time - last_push_time)} 秒...")
                time.sleep(push_interval - (current_time - last_push_time))
            if not push_changes(f"AutoDebug: Push changes after partial fix for run {run_id} (iteration {iteration})", run_id, branch, config):
                print("[ERROR] 推送失败，但已保存更改到本地，继续执行后续逻辑...")
            last_push_time = time.time()  # 更新推送时间
        save_processed_runs(processed_runs, processed_runs_file)
        save_fix_history(fix_history, fix_history_file)
        break

        iteration += 1

if __name__ == "__main__":
    main()
    #