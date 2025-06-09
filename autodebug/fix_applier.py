import re
import yaml
import os
import requests
import time
from datetime import datetime
from autodebug.history import FixHistory
import json

# 全局集合，用于记录已修复的错误
fixed_errors = set()

def apply_fix(workflow_file, step_name, step_code, error_message, push_changes_func, iteration, branch, history_file):
    """应用修复到工作流文件，避免嵌套错误、重复步骤，并验证步骤格式"""
    try:
        history = FixHistory(history_file)

        # 检查步骤是否已被验证为正确
        if history.is_section_protected(step_name):
            print(f"[DEBUG] 步骤 '{step_name}' 已被验证为正确，跳过修改")
            return False

        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f) or {}

        jobs = workflow.get("jobs", {})
        if not jobs:
            print("[ERROR] 工作流文件中未找到 'jobs' 部分，无法应用修复")
            return False

        build_job = jobs.get("build", {})
        if not build_job:
            print("[ERROR] 工作流文件中未找到 'build' 作业，无法应用修复")
            return False

        steps = build_job.get("steps", [])
        if not steps:
            print("[WARNING] 'build' 作业中未找到步骤，初始化步骤列表")
            steps = []

        # 检查步骤是否已存在（避免重复添加）
        for step in steps:
            if step.get("name") == step_name:
                print(f"[DEBUG] 步骤 '{step_name}' 已存在，跳过修复")
                return False

        # 加载新步骤并确保无嵌套错误
        step_yaml = yaml.safe_load(step_code)
        if isinstance(step_yaml, list):
            # 如果 step_code 是列表，确保只添加单个步骤
            if len(step_yaml) == 1:
                step_yaml = step_yaml[0]  # 解包单元素列表
            else:
                print(f"[ERROR] 修复步骤 '{step_name}' 包含多个步骤，不允许嵌套")
                return False
        # 如果 step_yaml 仍然是列表（嵌套列表），进一步解包
        while isinstance(step_yaml, list):
            if len(step_yaml) == 1:
                step_yaml = step_yaml[0]
            else:
                print(f"[ERROR] 修复步骤 '{step_name}' 包含无效的嵌套结构：{step_yaml}")
                return False

        # 验证 step_yaml 是否为有效的步骤对象（必须是字典）
        if not isinstance(step_yaml, dict):
            print(f"[ERROR] 修复步骤 '{step_name}' 格式无效，必须是一个步骤对象（字典）：{step_yaml}")
            return False

        # 验证步骤是否包含必要的字段（例如 'name' 和 'run' 或 'uses'）
        if not ("run" in step_yaml or "uses" in step_yaml) or "name" not in step_yaml:
            print(f"[ERROR] 修复步骤 '{step_name}' 缺少必要字段（需要 'name' 和 'run' 或 'uses'）：{step_yaml}")
            return False

        # 添加验证通过的步骤
        steps.append(step_yaml)

        build_job["steps"] = steps
        jobs["build"] = build_job
        workflow["jobs"] = jobs

        # 修复嵌套问题并验证语法
        workflow = fix_yaml_nesting(workflow)
        if workflow is None:
            print("[ERROR] 无法修复 YAML 嵌套问题，停止操作")
            return False

        with open(workflow_file, "w") as f:
            yaml_content = yaml.dump(workflow, sort_keys=False, indent=2, allow_unicode=True).rstrip() + '\n'
            if not validate_yaml_content(workflow_file, yaml_content):
                print("[ERROR] 修复后 YAML 语法仍不正确，停止操作")
                return False
            f.write(yaml_content)

        print(f"[DEBUG] 已将修复步骤 '{step_name}' 添加到工作流文件")
        # 推送更改
        success = push_changes_func(f"AutoDebug: Apply fix '{step_name}' (iteration {iteration})", None, branch)
        if not success:
            print("[ERROR] 推送失败，停止后续操作")
            return False

        history.add_to_fix_history(error_message, step_name, step_code, False, modified_section=step_name)
        return True

    except Exception as e:
        print(f"[ERROR] 应用修复失败: {e}")
        return False

def test_deepseek_api(deepseek_api_key):
    """测试 DeepSeek API 是否可用"""
    if not deepseek_api_key:
        return False
    headers = {
        "Authorization": f"Bearer {deepseek_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-coder",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10
    }
    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] DeepSeek API 不可用: {e}")
        return False

def validate_yaml_content(workflow_file, content):
    """验证 YAML 内容是否符合语法规范，增强对隐藏字符和嵌套序列的检查"""
    try:
        # 移除文件末尾的多余换行符和空格
        content = content.rstrip() + '\n'
        workflow = yaml.safe_load(content)
        
        # 检查 steps 列表是否有嵌套序列
        if "jobs" in workflow and "build" in workflow["jobs"]:
            steps = workflow["jobs"]["build"].get("steps", [])
            for step in steps:
                if isinstance(step, list):
                    print(f"[ERROR] 检测到嵌套序列：{step}")
                    return False
                if not isinstance(step, dict):
                    print(f"[ERROR] 步骤格式无效，必须是字典：{step}")
                    return False
                if not ("name" in step and ("run" in step or "uses" in step)):
                    print(f"[ERROR] 步骤缺少必要字段（需要 'name' 和 'run' 或 'uses'）：{step}")
                    return False
        
        print("[DEBUG] YAML 语法验证通过")
        return True
    except yaml.YAMLError as e:
        print(f"[ERROR] YAML 语法错误: {e}")
        # 检查文件末尾是否有隐藏字符
        lines = content.splitlines()
        if lines and lines[-1].strip() == '':
            print("[DEBUG] 检测到文件末尾有多余的空行，尝试修复...")
            content = '\n'.join(line for line in lines if line.strip()) + '\n'
            try:
                yaml.safe_load(content)
                print("[DEBUG] 修复文件末尾空行后 YAML 语法验证通过")
                with open(workflow_file, "w") as f:
                    f.write(content)
                return True
            except yaml.YAMLError as e2:
                print(f"[ERROR] 修复文件末尾空行后仍存在 YAML 语法错误: {e2}")
        return False

def fix_yaml_nesting(workflow):
    """修复 YAML 中的多余嵌套问题，增强对嵌套序列的处理"""
    try:
        jobs = workflow.get("jobs", {})
        if "build" in jobs:
            steps = jobs["build"].get("steps", [])
            fixed_steps = []
            for step in steps:
                # 处理嵌套序列（如 - - name:）
                while isinstance(step, list):
                    if not step:  # 空列表
                        break
                    if len(step) == 1:
                        step = step[0]
                    else:
                        print(f"[ERROR] 检测到无效的嵌套序列：{step}")
                        step = step[0]  # 强制取第一个元素，修复嵌套
                if isinstance(step, dict):
                    if "name" in step or "uses" in step:
                        fixed_steps.append(step)
                    else:
                        print(f"[DEBUG] 忽略无效步骤（缺少 'name' 或 'uses'）：{step}")
                else:
                    print(f"[DEBUG] 忽略无效步骤（非字典对象）：{step}")
            jobs["build"]["steps"] = fixed_steps
            workflow["jobs"] = jobs
        return workflow
    except Exception as e:
        print(f"[ERROR] 修复 YAML 嵌套失败: {e}")
        return None

def fix_yaml_true_field(workflow):
    """修复 YAML 中 'true' 字段的问题"""
    try:
        if True in workflow:
            print("[DEBUG] 检测到 'true' 字段，替换为正确的 'on' 字段")
            true_field = workflow.pop(True)
            if isinstance(true_field, list):
                new_on = {}
                for trigger in true_field:
                    new_on[trigger] = {"branches": ["main"]}
                workflow["on"] = new_on
            else:
                workflow["on"] = {
                    "push": {"branches": ["main"]},
                    "pull_request": {"branches": ["main"]}
                }
            print(f"[DEBUG] 已修复 'true' 字段为: {workflow['on']}")
        return workflow
    except Exception as e:
        print(f"[ERROR] 修复 'true' 字段失败: {e}")
        return None

def extract_specific_error_from_log(log_content):
    """从日志中提取更具体的错误信息，例如 ValueError: read of closed file"""
    log_lines = log_content.splitlines()
    specific_error = None
    in_traceback = False
    traceback_lines = []
    error_index = -1

    for i, line in enumerate(log_lines):
        if "Traceback (most recent call last):" in line or (line.strip().startswith("File ") and ".py" in line and not in_traceback):
            in_traceback = True
            traceback_lines.append(line)
            continue
        if in_traceback:
            traceback_lines.append(line)
            if line.strip() and not line.startswith("  File") and (line.strip().startswith("ValueError:") or line.strip().startswith("Error:") or line.strip().startswith("Exception:")):
                error_message = "\n".join(traceback_lines)
                if "ValueError: read of closed file" in error_message.lower():
                    specific_error = error_message
                    error_index = i
                    print(f"[DEBUG] 从堆栈跟踪中提取到具体错误: {specific_error}")
                    break
                in_traceback = False
                traceback_lines = []
                continue

    if not specific_error:
        for i, line in enumerate(log_lines):
            if "valueerror: read of closed file" in line.lower():
                specific_error = line.strip()
                error_index = i
                print(f"[DEBUG] 直接提取到具体错误: {specific_error}")
                break

    if specific_error and error_index != -1:
        context_lines = 10
        start_index = max(0, error_index - context_lines)
        end_index = min(len(log_lines), error_index + context_lines + 1)
        context = "\n".join(log_lines[start_index:end_index])
        print(f"[DEBUG] 提取错误上下文: {context}")
        return specific_error + "\n上下文:\n" + context

    print("[DEBUG] 未从日志中提取到具体错误")
    return None

def analyze_error_relevance(error_context, steps):
    """分析错误与步骤的关联性，确定错误可能发生在哪个步骤之后"""
    error_lines = error_context.splitlines()
    relevant_step = None
    for line in error_lines:
        for step in steps:
            step_name = step.get("name", step.get("uses", "unnamed"))
            if step_name in line:
                relevant_step = step_name
                break
        if relevant_step:
            break
    return relevant_step

def check_step_functionality_similarity(step1, step2):
    """检查两个步骤的功能是否相似（基于 run 命令）"""
    if "run" not in step1 or "run" not in step2:
        return False
    run1 = step1["run"].lower()
    run2 = step2["run"].lower()
    # 简单的功能相似性检查：如果两个步骤的 run 命令包含相同的核心操作（如 df -h, du -h）
    common_operations = ["df -h", "du -h", "ping", "rm -rf", "apt-get clean"]
    for op in common_operations:
        if op in run1 and op in run2:
            # 特殊情况：如果步骤名称中包含 "before build" 和 "after build"，允许功能重复
            step1_name = step1.get("name", "").lower()
            step2_name = step2.get("name", "").lower()
            if ("before build" in step1_name and "after build" in step2_name) or \
               ("before build" in step2_name and "after build" in step1_name):
                print(f"[DEBUG] 允许功能重复步骤（用于磁盘空间排查）: {step1_name} 和 {step2_name}")
                return False
            return True
    return False

def reorder_steps(steps, correct_steps):
    """根据逻辑顺序重新排序步骤"""
    preparation_steps = []
    build_steps = []
    verification_steps = []
    upload_steps = []

    # 分类步骤
    for step in steps:
        step_name = step.get("name", step.get("uses", "unnamed"))
        # 临时步骤：移除 Initial Trigger Step
        if step_name == "Initial Trigger Step":
            print(f"[DEBUG] 移除临时步骤: {step_name}")
            continue
        # 准备步骤：环境设置、依赖安装、清理等
        if any(keyword in step_name.lower() for keyword in ["set up", "install", "configure", "download", "initialize", "prepare", "clean", "check disk", "check network"]):
            preparation_steps.append(step)
        # 构建步骤：Build APK
        elif "build apk" in step_name.lower():
            build_steps.append(step)
        # 验证步骤：Verify Build Log, Check Disk Space After Build
        elif any(keyword in step_name.lower() for keyword in ["verify", "check disk space after"]):
            verification_steps.append(step)
        # 上传步骤：Save Build Log, Upload APK
        elif any(keyword in step_name.lower() for keyword in ["save build log", "upload apk"]):
            upload_steps.append(step)
        else:
            # 默认归类为准备步骤
            preparation_steps.append(step)

    # 确保 correct_steps 按顺序排列
    ordered_steps = []
    correct_steps_dict = {step.get("name", step.get("uses", "unnamed")): step for step in steps}
    for correct_step in correct_steps:
        if correct_step in correct_steps_dict:
            ordered_steps.append(correct_steps_dict[correct_step])

    # 添加其他步骤
    for step in preparation_steps:
        step_name = step.get("name", step.get("uses", "unnamed"))
        if step_name not in correct_steps:
            ordered_steps.append(step)
    ordered_steps.extend(build_steps)
    ordered_steps.extend(verification_steps)
    ordered_steps.extend(upload_steps)

    return ordered_steps

def fetch_annotations(run_id, config):
    """从 GitHub Actions API 获取 Annotations"""
    github_token = config.get('GITHUB_TOKEN')
    if not github_token:
        print("[ERROR] 未找到 GITHUB_TOKEN，无法获取 Annotations")
        return []

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    annotations_url = f"https://api.github.com/repos/shelley021/weatherapp/actions/runs/{run_id}/annotations"
    try:
        response = requests.get(annotations_url, headers=headers, timeout=30)
        if response.status_code == 200:
            annotations = response.json()
            print(f"[DEBUG] 成功获取 Annotations: {len(annotations)} 条")
            return annotations
        else:
            print(f"[ERROR] 获取 Annotations 失败: {response.status_code} {response.text}")
            return []
    except Exception as e:
        print(f"[ERROR] 获取 Annotations 时发生错误: {e}")
        return []

def fix_workflow(workflow_file, errors, error_patterns, push_changes_func, iteration, branch, history_file, run_id, job_id, annotations_error, error_details, successful_steps, config, log_content, additional_fixes=None):
    """尝试修复工作流中的错误，增强错误分类和本地修复逻辑"""
    try:
        history = FixHistory(history_file)

        # 加载当前工作流文件
        with open(workflow_file, "r") as f:
            current_workflow = yaml.safe_load(f)

        # 检查每个步骤的执行状态
        current_steps = current_workflow.get("jobs", {}).get("build", {}).get("steps", [])
        for step in current_steps:
            step_name = step.get("name", step.get("uses", "unnamed"))
            status = history.get_step_status(step_name)
            if status is True:
                print(f"[DEBUG] 步骤 '{step_name}' 已验证正确，标记为受保护")
            elif status is False:
                print(f"[DEBUG] 步骤 '{step_name}' 之前执行失败，允许修复")

        with open(history_file, "r") as f:
            fix_history = json.load(f)

        if not isinstance(fix_history, dict):
            print("[WARNING] fix_history 格式不正确，初始化为空字典")
            fix_history = {"history": []}

        # 获取 Annotations
        annotations = []
        if run_id:
            try:
                annotations = fetch_annotations(run_id, config)
            except Exception as e:
                print(f"[WARNING] 无法获取 Annotations，可能权限不足或日志不可用: {e}")
                print("[INFO] 跳过 Annotations 获取，直接分析 debug.yml 文件")
        annotation_errors = [ann['message'] for ann in annotations if ann.get('message')]
        print(f"[DEBUG] 获取到的 Annotations 错误: {annotation_errors}")

        # 合并错误信息
        all_errors = errors.copy()
        if annotations_error:
            all_errors.append(annotations_error)
        all_errors.extend(annotation_errors)

        # 清理错误信息，去除时间戳并过滤误识别的日志
        cleaned_errors = []
        for error in all_errors:
            cleaned_error = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", error)
            # 过滤掉误识别的非错误日志
            if "echo \"Build log exists, checking for errors...\"" in cleaned_error or \
               "if grep -q -E \"ERROR:|FAILED\" build.log; then" in cleaned_error or \
               "echo \"Errors found in build log:\"" in cleaned_error or \
               "grep -E \"ERROR:|FAILED\" build.log" in cleaned_error or \
               "echo \"No critical errors found in build log\"" in cleaned_error:
                print(f"[DEBUG] 忽略误识别的日志输出: {cleaned_error}")
                continue
            cleaned_errors.append(cleaned_error)
            print(f"[DEBUG] 清理后的错误信息: {cleaned_error}")

            if error not in fix_history.get("errors", {}):
                fix_history.setdefault("errors", {})[error] = {
                    "attempted": [],
                    "successful_fix": None,
                    "timestamp": None,
                    "failed_attempts": []
                }
            if error not in [entry["error"] for entry in fix_history.get("history", [])]:
                fix_history["history"].append({
                    "error": error,
                    "attempted": [{"iteration": iteration, "timestamp": datetime.now().isoformat()}],
                    "fix_applied": None,
                    "success": False
                })

        untried_errors = [e for e in all_errors if e not in fix_history.get("errors", {}) or not fix_history["errors"].get(e, {}).get("attempted", [])]
        fix_history["untried_errors"] = untried_errors

        # 提取更具体的错误信息
        refined_errors = []
        for error in cleaned_errors:
            if "failed to generate apk" in error.lower():
                print(f"[DEBUG] 检测到笼统错误 'Failed to generate APK'，尝试提取更具体错误...")
                specific_error = extract_specific_error_from_log(log_content) if log_content else None
                if specific_error:
                    refined_errors.append(specific_error)
                else:
                    refined_errors.append(error)
            else:
                refined_errors.append(error)
        cleaned_errors = refined_errors

        for error in cleaned_errors:
            if error in fixed_errors:
                print(f"[DEBUG] 错误 '{error}' 已修复过，跳过...")
                continue

        historical_successful_steps = history.get_successful_steps()
        known_errors = history.get_known_errors()
        correct_steps = fix_history.get("correct_steps", [
            "actions/checkout@v4",
            "Set up JDK 17",
            "Set up Python",
            "Install missing libtinfo package",
            "Install system dependencies",
            "Configure pip mirror",
            "Install Python dependencies",
            "Set up Android SDK",
            "Accept Android SDK Licenses",
            "Download Android NDK with Retry",
            "Initialize Buildozer",
            "Prepare python-for-android",
            "Set Custom Temp Directory",
            "Build APK",
            "Verify Build Log",
            "Save Build Log",
            "Upload APK"
        ])
        correct_steps = list(set(correct_steps + historical_successful_steps))
        print(f"[DEBUG] 更新后的 correct_steps: {correct_steps}")

        if successful_steps:
            history.update_successful_steps(successful_steps)
            for step_name in successful_steps:
                history.update_step_status(step_name, True)

        # 分析错误与步骤的关联性
        error_step_mapping = {}
        for error_detail in error_details:
            error = error_detail["error_line"]
            if error in cleaned_errors:
                context = error_detail["context"]
                relevant_step = analyze_error_relevance(context, current_steps)
                if relevant_step:
                    error_step_mapping[error] = relevant_step
                    print(f"[DEBUG] 错误 '{error}' 与步骤 '{relevant_step}' 相关联")

        # 检查 debug.yml 文件的语法（不依赖运行日志）
        with open(workflow_file, "r") as f:
            content = f.read()
        if not validate_yaml_content(workflow_file, content):
            print("[ERROR] 当前 debug.yml 语法错误，尝试修复...")
            current_workflow = fix_yaml_nesting(current_workflow)
            if current_workflow is None:
                print("[ERROR] 无法修复 YAML 嵌套问题，尝试重置 debug.yml...")
                # 重置 debug.yml 文件
                reset_workflow = {
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
                                {"name": "Set up JDK 17", "uses": "actions/setup-java@v3", "with": {"distribution": "temurin", "java-version": "17"}},
                                {"name": "Set up Python", "uses": "actions/setup-python@v5", "with": {"python-version": "3.10"}},
                                {"name": "Install missing libtinfo package", "run": "Ubuntu_version=$(lsb_release -rs)\nif [[ \"$Ubuntu_version\" == \"22.04\" || \"$Ubuntu_version\" == \"24.04\" ]]; then\n  sudo apt-get update -y\n  sudo apt-get install -y libtinfo6\nelse\n  sudo apt-get update -y\n  sudo apt-get install -y libtinfo5\nfi"},
                                {"name": "Install system dependencies", "run": "sudo apt-get update -y\nsudo apt-get install -y git zip unzip python3-pip autoconf libtool pkg-config\nsudo apt-get install -y zlib1g-dev libncurses5-dev libncursesw5-dev\nsudo apt-get install -y cmake libffi-dev libssl-dev\nsudo apt-get install -y libltdl-dev build-essential python3-dev python3-venv\nsudo apt-get install -y libnss3-dev libnss3-tools"},
                                {"name": "Configure pip mirror", "run": "pip config set global.index-url https://pypi.org/simple/\npip config set global.trusted-host pypi.org"},
                                {"name": "Install Python dependencies", "run": "python -m pip install --upgrade pip setuptools\npip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi\npip install python-for-android"},
                                {"name": "Set up Android SDK", "uses": "android-actions/setup-android@v3", "with": {"accept-android-sdk-licenses": True, "cmdline-tools-version": "latest", "packages": "build-tools;34.0.0 platform-tools platforms;android-34 ndk;25.2.9519653"}},
                                {"name": "Accept Android SDK Licenses", "run": "yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"},
                                {"name": "Download Android NDK with Retry", "run": "NDK_URL=\"https://dl.google.com/android/repository/android-ndk-r25b-linux.zip\"\nNDK_PATH=\"$HOME/android-ndk-r25b.zip\"\nNDK_INSTALL_DIR=\"$HOME/.buildozer/android/platform/android-ndk-r25b\"\nEXPECTED_MD5=\"e76f7b99f9e73ecee90f32c5e663f4339e0b0a1\"\nMAX_RETRIES=5\nRETRY_DELAY=15\nfor i in $(seq 1 $MAX_RETRIES); do\n  echo \"尝试下载 Android NDK (第 $i 次)...\"\n  curl -L -o \"$NDK_PATH\" \"$NDK_URL\" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60\n  if [ $? -eq 0 ]; then\n    DOWNLOADED_MD5=$(md5sum \"$NDK_PATH\" | awk '{print $1}')\n    if [ \"$DOWNLOADED_MD5\" = \"$EXPECTED_MD5\" ]; then\n      echo \"NDK 下载成功，MD5 校验通过：$DOWNLOADED_MD5\"\n      break\n    else\n      echo \"NDK 文件 MD5 校验失败，预期：$EXPECTED_MD5，实际：$DOWNLOADED_MD5\"\n      rm -f \"$NDK_PATH\"\n    fi\n  fi\n  if [ $i -lt $MAX_RETRIES ]; then\n    echo \"下载失败，等待 $RETRY_DELAY 秒后重试...\"\n    sleep $RETRY_DELAY\n  else\n    echo \"下载 Android NDK 失败，退出...\"\n    exit 1\n  fi\ndone\nmkdir -p \"$HOME/.buildozer/android/platform\"\nunzip -q \"$NDK_PATH\" -d \"$HOME/.buildozer/android/platform\" || {\n  echo \"解压 NDK 失败，请检查文件完整性\"\n  exit 1\n}\nif [ -d \"$NDK_INSTALL_DIR\" ]; then\n  echo \"NDK 解压成功，路径：$NDK_INSTALL_DIR\"\nelse\n  echo \"NDK 解压失败，未找到预期目录：$NDK_INSTALL_DIR\"\n  exit 1\nfi\nexport ANDROID_NDK_HOME=\"$NDK_INSTALL_DIR\"\necho \"ANDROID_NDK_HOME=$ANDROID_NDK_HOME\" >> $GITHUB_ENV"},
                                {"name": "Initialize Buildozer", "run": "buildozer init\ncat << 'EOF' > buildozer.spec\n[app]\ntitle = WeatherApp\npackage.name = weatherapp\npackage.domain = org.weatherapp\nsource.dir = .\nsource.include_exts = py,png,jpg,kv,atlas\nversion = 0.1\nrequirements = python3,kivy==2.3.1,requests==2.25.1,certifi\nandroid.permissions = INTERNET\nandroid.api = 34\nandroid.minapi = 21\nandroid.ndk = 25b\nandroid.ndk_path = $ANDROID_NDK_HOME\nandroid.sdk_path = $ANDROID_HOME\nandroid.accept_sdk_license = True\norientation = portrait\nfullscreen = 0\nlog_level = 2\np4a.branch = master\nEOF"},
                                {"name": "Prepare python-for-android", "run": "mkdir -p .buildozer/android/platform\ngit clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android\ncd .buildozer/android/platform/python-for-android\ngit checkout master"},
                                {"name": "Set Custom Temp Directory", "run": "mkdir -p $HOME/tmp\necho \"TMPDIR=$HOME/tmp\" >> $GITHUB_ENV\necho \"TEMP=$HOME/tmp\" >> $GITHUB_ENV\necho \"TMP=$HOME/tmp\" >> $GITHUB_ENV\nexport TMPDIR=$HOME/tmp\nexport TEMP=$HOME/tmp\nexport TMP=$HOME/tmp"},
                                {"name": "Build APK", "env": {"OPENWEATHER_API_KEY": "${{ secrets.OPENWEATHER_API_KEY }}", "P4A_RELEASE_KEYALIAS": "${{ secrets.P4A_RELEASE_KEYALIAS }}", "P4A_RELEASE_KEYALIAS_PASSWD": "${{ secrets.P4A_RELEASE_KEYALIAS_PASSWD }}", "P4A_RELEASE_KEYSTORE": "${{ secrets.P4A_RELEASE_KEYSTORE }}", "P4A_RELEASE_KEYSTORE_PASSWD": "${{ secrets.P4A_RELEASE_KEYSTORE_PASSWD }}"}, "run": "export CFLAGS=\"-Wno-error=implicit-function-declaration -Wno-error=array-bounds -Wno-error=deprecated-declarations\"\nexport CPPFLAGS=\"-D_GNU_SOURCE -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=700\"\nexport LDFLAGS=\"-lnsl -lresolv -lgssapi_krb5\"\nbuildozer android clean\nbuildozer -v android debug deploy 2>&1 | tee build.log || echo \"Build failed but log generated\" >> build.log\nif [ ${PIPESTATUS[0]} -ne 0 ]; then\n  cat build.log\n  exit 1\nfi"},
                                {"name": "Verify Build Log", "if": "always()", "run": "if [ -f build.log ]; then\n  echo \"Build log exists, checking for errors...\"\n  if grep -q -E \"ERROR:|FAILED\" build.log; then\n    echo \"Errors found in build log:\"\n    grep -E \"ERROR:|FAILED\" build.log\n    exit 1\n  else\n    echo \"No critical errors found in build log\"\n  fi\nelse\n  echo \"No build log found\"\n  exit 1\nfi"},
                                {"name": "Save Build Log", "if": "always()", "uses": "actions/upload-artifact@v4", "with": {"name": f"build-log-{run_id}", "path": "build.log", "retention-days": 1}},
                                {"name": "Upload APK", "if": "success()", "uses": "actions/upload-artifact@v4", "with": {"if-no-files-found": "error", "name": f"weatherapp-apk-{run_id}", "path": "bin/weatherapp-*.apk", "retention-days": 1}}
                            ]
                        }
                    }
                }
                with open(workflow_file, "w") as f:
                    yaml.dump(reset_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                print("[DEBUG] 已重置 debug.yml 以修复语法错误")
                success = push_changes_func(f"AutoDebug: Reset debug.yml to fix syntax (iteration {iteration})", None, branch)
                if not success:
                    print("[ERROR] 推送失败，停止后续操作")
                    fix_history["errors"][error]["failed_attempts"].append({"fix": "Reset debug.yml", "reason": "推送失败"})
                    with open(history_file, "w") as f:
                        json.dump(fix_history, f, ensure_ascii=False, indent=2)
                    return False
                return True
            print("[DEBUG] 已修复 debug.yml 语法")
            success = push_changes_func(f"AutoDebug: Fix YAML syntax (iteration {iteration})", None, branch)
            if not success:
                print("[ERROR] 推送失败，停止后续操作")
                fix_history["errors"][error]["failed_attempts"].append({"fix": "Fix YAML syntax", "reason": "推送失败"})
                with open(history_file, "w") as f:
                    json.dump(fix_history, f, ensure_ascii=False, indent=2)
                return False
            return True
        else:
            print("[INFO] debug.yml 语法已正确，无需修复")

        # 优先尝试本地修复（按优先级排序）
        for error in cleaned_errors:
            # 检查历史失败的修复，避免重复尝试
            failed_attempts = fix_history.get("errors", {}).get(error, {}).get("failed_attempts", [])
            failed_fixes = [attempt["fix"] for attempt in failed_attempts]

            # 修复 startup_failure 或 YAML 格式错误（高优先级）
            if "startup_failure" in error.lower() or any("invalid workflow file" in ann.lower() for ann in annotation_errors) or "a sequence was not expected" in error.lower():
                print(f"[DEBUG] 检测到 startup_failure 或 YAML 格式错误: {error}")
                # 避免重复触发新运行
                if "Trigger new run" in failed_fixes:
                    print(f"[DEBUG] 'Trigger new run' 之前已失败，跳过触发新运行...")
                    continue
                # 直接分析 debug.yml 文件（已在上方完成）
                continue

            # 修复依赖问题：如 "buildozer==1.5.1" 安装失败（高优先级）
            if "could not find a version that satisfies the requirement" in error.lower():
                print(f"[DEBUG] 检测到依赖错误: {error}")
                # 提取具体的包名和版本号
                match = re.search(r"requirement (\S+)==(\S+)", error)
                if match:
                    package_name, version = match.groups()
                    print(f"[DEBUG] 提取到错误的依赖: {package_name}=={version}")
                    if package_name.lower() == "buildozer" and version == "1.5.1":
                        fix = {
                            "name": "Fix Buildozer Dependency Installation",
                            "action": "modify_step",
                            "step": "- name: Install Python dependencies\n  run: |\n    python -m pip install --upgrade pip\n    pip install setuptools==65.5.0\n    pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi\n    pip install python-for-android",
                            "target": "Install Python dependencies",
                            "priority": 1  # 高优先级
                        }
                        if fix["name"] in failed_fixes:
                            print(f"[DEBUG] 修复 '{fix['name']}' 之前已失败，跳过...")
                            continue
                        print(f"[DEBUG] 尝试修复依赖问题: {fix['name']}")
                        success = apply_fix(workflow_file, fix["target"], fix["step"], error, push_changes_func, iteration, branch, history_file)
                        if not success:
                            print("[ERROR] 推送失败，停止后续操作")
                            fix_history["errors"][error]["failed_attempts"].append({"fix": fix["name"], "reason": "推送失败"})
                            with open(history_file, "w") as f:
                                json.dump(fix_history, f, ensure_ascii=False, indent=2)
                            return False
                        fix_history["errors"][error]["successful_fix"] = fix["step"]
                        fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                        with open(history_file, "w") as f:
                            json.dump(fix_history, f, ensure_ascii=False, indent=2)
                        fixed_errors.add(error)
                        history.update_step_status(fix["target"], True)
                        return True
                    else:
                        print(f"[DEBUG] 未识别的依赖错误: {package_name}=={version}，跳过...")
                        continue
                else:
                    print("[DEBUG] 无法提取依赖包名和版本号，跳过...")
                    continue

            # 修复网络超时问题（低优先级）
            if "readtimeouterror" in error.lower() or "connectiontimeout" in error.lower():
                print(f"[DEBUG] 检测到网络超时错误: {error}")
                fix = {
                    "name": "Switch PyPI Mirror and Retry",
                    "action": "modify_step",
                    "step": "- name: Configure pip mirror\n  run: |\n    pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple\n    pip config set global.trusted-host mirrors.tuna.tsinghua.edu.cn",
                    "target": "Configure pip mirror",
                    "priority": 2  # 中优先级
                }
                if fix["name"] in failed_fixes:
                    print(f"[DEBUG] 修复 '{fix['name']}' 之前已失败，跳过...")
                    continue
                print(f"[DEBUG] 尝试修复网络超时问题: {fix['name']}")
                success = apply_fix(workflow_file, fix["target"], fix["step"], error, push_changes_func, iteration, branch, history_file)
                if not success:
                    print("[ERROR] 推送失败，停止后续操作")
                    fix_history["errors"][error]["failed_attempts"].append({"fix": fix["name"], "reason": "推送失败"})
                    with open(history_file, "w") as f:
                        json.dump(fix_history, f, ensure_ascii=False, indent=2)
                    return False
                fix_history["errors"][error]["successful_fix"] = fix["step"]
                fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                with open(history_file, "w") as f:
                    json.dump(fix_history, f, ensure_ascii=False, indent=2)
                fixed_errors.add(error)
                history.update_step_status(fix["target"], True)
                return True

        # 检查错误模式并应用修复
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            for error in cleaned_errors:
                if re.search(pattern, error, re.IGNORECASE):
                    print(f"[DEBUG] 错误 '{error}' 匹配模式 '{pattern}'")
                    fixes = pattern_info.get("fix")
                    if fixes:
                        if isinstance(fixes, list):
                            for fix in fixes:
                                step_name = fix.get("step_name")
                                step_code = fix.get("step_code")
                                if step_name in error_step_mapping.get(error, "") or not error_step_mapping.get(error):
                                    if step_code and not history.is_section_protected(step_name):
                                        failed_attempts = fix_history.get("errors", {}).get(error, {}).get("failed_attempts", [])
                                        failed_fixes = [attempt["fix"] for attempt in failed_attempts]
                                        if step_name in failed_fixes:
                                            print(f"[DEBUG] 修复 '{step_name}' 之前已失败，跳过...")
                                            continue
                                        print(f"[DEBUG] 尝试修复: {step_name}")
                                        success = apply_fix(workflow_file, step_name, step_code, error, push_changes_func, iteration, branch, history_file)
                                        if not success:
                                            print("[ERROR] 推送失败，停止后续操作")
                                            fix_history["errors"][error]["failed_attempts"].append({"fix": step_name, "reason": "推送失败"})
                                            with open(history_file, "w") as f:
                                                json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                            return False
                                        fix_history["errors"][error]["successful_fix"] = step_code
                                        fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                                        with open(history_file, "w") as f:
                                            json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                        fixed_errors.add(error)
                                        history.update_step_status(step_name, True)
                                        return True
                                        print(f"[DEBUG] 修复 '{step_name}' 失败，尝试下一个方案")
                        elif isinstance(fixes, dict):
                            step_name = fixes.get("step_name")
                            step_code = fixes.get("step_code")
                            if step_name in error_step_mapping.get(error, "") or not error_step_mapping.get(error):
                                if step_code and not history.is_section_protected(step_name):
                                    failed_attempts = fix_history.get("errors", {}).get(error, {}).get("failed_attempts", [])
                                    failed_fixes = [attempt["fix"] for attempt in failed_attempts]
                                    if step_name in failed_fixes:
                                        print(f"[DEBUG] 修复 '{step_name}' 之前已失败，跳过...")
                                        continue
                                    print(f"[DEBUG] 找到匹配的修复: {step_name}")
                                    success = apply_fix(workflow_file, step_name, step_code, error, push_changes_func, iteration, branch, history_file)
                                    if not success:
                                        print("[ERROR] 推送失败，停止后续操作")
                                        fix_history["errors"][error]["failed_attempts"].append({"fix": step_name, "reason": "推送失败"})
                                        with open(history_file, "w") as f:
                                            json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                        return False
                                    fix_history["errors"][error]["successful_fix"] = step_code
                                    fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                                    with open(history_file, "w") as f:
                                        json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                    fixed_errors.add(error)
                                    history.update_step_status(step_name, True)
                                    return True

        # 处理附加修复
        if additional_fixes:
            for fix in additional_fixes:
                step_name = fix.get("name")
                step_code = fix.get("step")
                action = fix.get("action")
                target = fix.get("target", None)

                if not step_name or not step_code or not action:
                    print(f"[WARNING] 无效的 additional_fix: {fix}")
                    continue

                for error in cleaned_errors:
                    failed_attempts = fix_history.get("errors", {}).get(error, {}).get("failed_attempts", [])
                    failed_fixes = [attempt["fix"] for attempt in failed_attempts]
                    if step_name in failed_fixes:
                        print(f"[DEBUG] 修复 '{step_name}' 之前已失败，跳过...")
                        continue

                    if action == "add_step":
                        if (step_name in error_step_mapping.get(error, "") or not error_step_mapping.get(error)) and not history.is_section_protected(step_name):
                            print(f"[DEBUG] 尝试附加修复: {step_name}")
                            success = apply_fix(workflow_file, step_name, step_code, error, push_changes_func, iteration, branch, history_file)
                            if not success:
                                print("[ERROR] 推送失败，停止后续操作")
                                fix_history["errors"][error]["failed_attempts"].append({"fix": step_name, "reason": "推送失败"})
                                with open(history_file, "w") as f:
                                    json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                return False
                            fix_history["errors"][error]["successful_fix"] = step_code
                            fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                            with open(history_file, "w") as f:
                                json.dump(fix_history, f, ensure_ascii=False, indent=2)
                            fixed_errors.add(error)
                            history.update_step_status(step_name, True)
                            return True
                    elif action == "modify_step" and target:
                        if (target in error_step_mapping.get(error, "") or not error_step_mapping.get(error)) and not history.is_section_protected(target):
                            print(f"[DEBUG] 尝试修改步骤 {target} 以修复: {step_name}")
                            success = apply_fix(workflow_file, target, step_code, error, push_changes_func, iteration, branch, history_file)
                            if not success:
                                print("[ERROR] 推送失败，停止后续操作")
                                fix_history["errors"][error]["failed_attempts"].append({"fix": step_name, "reason": "推送失败"})
                                with open(history_file, "w") as f:
                                    json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                return False
                            fix_history["errors"][error]["successful_fix"] = step_code
                            fix_history["errors"][error]["timestamp"] = datetime.now().isoformat()
                            with open(history_file, "w") as f:
                                json.dump(fix_history, f, ensure_ascii=False, indent=2)
                            fixed_errors.add(error)
                            history.update_step_status(target, True)
                            return True

        # 尝试 DeepSeek API 修复
        deepseek_api_key = config.get('DEEPSEEK_API_KEY')
        if deepseek_api_key and test_deepseek_api(deepseek_api_key):
            print("[DEBUG] 本地修复未匹配，尝试使用 DeepSeek API 进行智能修复")
            headers = {
                "Authorization": f"Bearer {deepseek_api_key}",
                "Content-Type": "application/json"
            }
            max_retries = 8
            base_timeout = 120
            max_log_length = 20000
            max_total_time = 600
            consecutive_failures = 0
            max_consecutive_failures = 3
            start_time = time.time()

            with open(workflow_file, "r") as f:
                original_workflow = yaml.safe_load(f)

            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            autodebug_dir = os.path.join(project_root, "autodebug")
            requirements_file_md = os.path.join(autodebug_dir, "debug_requirements.md")
            requirements_file_markdown = os.path.join(autodebug_dir, "debug_requirements.markdown")

            requirements_file = None
            if os.path.exists(requirements_file_md):
                requirements_file = requirements_file_md
            elif os.path.exists(requirements_file_markdown):
                requirements_file = requirements_file_markdown
            else:
                print("[ERROR] 未找到 debug_requirements.md 或 debug_requirements.markdown 文件，停止 DeepSeek API 修复")
                return False

            with open(requirements_file, "r", encoding="utf-8") as f:
                requirements_content = f.read()

            key_log_parts = []
            for idx, error in enumerate(all_errors):
                if "failed to generate apk" in error.lower():
                    specific_error = extract_specific_error_from_log(log_content) if log_content else None
                    if specific_error:
                        key_log_parts.append(f"错误 {idx + 1}: {specific_error}")
                    else:
                        key_log_parts.append(f"错误 {idx + 1}: {error}\n上下文:\n{error_details[idx]['context']}")
                else:
                    key_log_parts.append(f"错误 {idx + 1}: {error}\n上下文:\n{error_details[idx]['context']}")
            key_log_content = "\n\n".join(key_log_parts)
            if len(key_log_content) > max_log_length:
                key_log_content = key_log_content[:max_log_length]

            history_context = "\n".join([
                f"错误: {entry.get('error_message', entry.get('error', '未知错误'))}, "
                f"修复: {entry.get('fix_applied', '无')}, "
                f"成功: {entry.get('success', False)}"
                for entry in fix_history.get("history", [])[-5:]
            ])

            failed_attempts_context = {}
            for error in cleaned_errors:
                failed_attempts = history.get_deepseek_attempts(error)
                if failed_attempts:
                    failed_attempts_context[error] = "\n".join([
                        f"尝试 {idx + 1}: {attempt['fix_attempt']}, 失败原因: {attempt['reason']}"
                        for idx, attempt in enumerate(failed_attempts)
                    ])
                else:
                    failed_attempts_context[error] = "无失败尝试"

            with open(workflow_file, "r") as f:
                current_workflow = yaml.safe_load(f)

            incorrect_modifications = fix_history.get("incorrect_modifications", [])
            current_steps = current_workflow.get("jobs", {}).get("build", {}).get("steps", [])
            current_step_names = {step.get("name", step.get("uses", "unnamed")) for step in current_steps}
            protected_steps = [step for step in current_steps if history.is_section_protected(step.get("name", step.get("uses", "unnamed")))]

            for attempt in range(max_retries):
                elapsed_time = time.time() - start_time
                if elapsed_time > max_total_time:
                    print(f"[ERROR] DeepSeek API 修复已超过最大时间限制 {max_total_time} 秒，终止重试")
                    return False

                if consecutive_failures >= max_consecutive_failures:
                    print(f"[ERROR] DeepSeek API 连续失败 {max_consecutive_failures} 次，终止重试")
                    return False

                try:
                    payload = {
                        "model": "deepseek-coder",
                        "messages": [
                            {
                                "role": "system",
                                "content": requirements_content
                            },
                            {
                                "role": "user",
                                "content": f"""历史修复记录（最近 5 条）：
{history_context}

已知错误模式（参考但可自主分析）：
{', '.join(known_errors) if known_errors else '无已知错误'}

错误日志（包含所有错误）：
{key_log_content}
附加信息：
- 项目类型：Python/Kivy 应用，构建 Android APK
- 失败原因：{annotations_error or '未知错误'}
- 当前 debug.yml：
```yaml
{yaml.dump(current_workflow, sort_keys=False, indent=2, allow_unicode=True)}
```
- 完整的日志内容（前 {max_log_length} 字符）：
{log_content[:max_log_length] if log_content else '无日志内容'}
- 正确的步骤（必须保留）：
{', '.join(correct_steps)}
- 受保护的步骤（不得修改）：
{', '.join([step.get("name", step.get("uses", "unnamed")) for step in protected_steps])}
- 错误的修改（不能重复）：
{incorrect_modifications}
- 失败的修复尝试（请避免这些错误）：
{json.dumps(failed_attempts_context, indent=2, ensure_ascii=False)}

当前错误是：
{annotations_error or '未知错误'}
请根据错误日志自主分析，识别错误并修复 debug.yml 中的相关步骤。你可以自由分析错误，但必须严格遵守以下规则：

**强制规则**：
1. **不得修改或删除受保护的步骤**：{', '.join([step.get("name", step.get("uses", "unnamed")) for step in protected_steps])}.
2. **必须保留所有必要步骤**：{', '.join(correct_steps)}，包括 `actions/checkout@v4` 等关键步骤。
3. **不得添加功能重复的步骤**（除非明确指定用于排查）：
   - 例如，如果已存在 `Check Network Connectivity`，不得再次添加类似步骤。
   - 如果已存在 `Clean Disk Space`，不得再次添加清理磁盘的步骤。
   - 特殊情况：如果需要排查磁盘空间问题，可以保留 `Check Disk Space Before Build` 和 `Check Disk Space After Build`，但建议将它们合并为一个步骤，记录构建前后的磁盘空间变化。
4. **确保 YAML 语法正确**：
   - 每个步骤必须以单个 '-' 开头，例如：
     ```yaml
     - name: Example Step
       run: echo "Hello"
     ```
   - 不得出现嵌套序列（如 '- - name:'），否则会导致 'A sequence was not expected' 错误。
   - **避免文件末尾的多余换行符或空格**：确保生成的 YAML 文件在末尾只有单个换行符，避免隐藏字符导致语法错误。
5. **仅修改与错误直接相关的步骤**：确保不影响其他成功运行的步骤。
6. **参考失败尝试**：避免重复之前失败的修复方案，尤其是导致 YAML 格式错误（如 'A sequence was not expected'）的方案。
7. **移除临时步骤**：如果存在 `Initial Trigger Step`，请移除该步骤，因为它仅用于触发运行。
8. **步骤插入位置**：
   - 准备步骤（如 `Check Network Connectivity`、`Clean Disk Space`）应在 `Build APK` 之前。
   - 验证步骤（如 `Check Disk Space After Build`）应在 `Build APK` 之后。
   - 上传步骤（如 `Save Build Log`、`Upload APK`）应在最后。

**建议**：
- 如果错误与依赖安装相关（例如 `buildozer` 安装失败），可以尝试切换 PyPI 镜像或调整依赖版本，例如将 `buildozer==1.5.1` 替换为 `buildozer==1.5.0`。
- 如果错误与网络相关，可以添加网络检查步骤，但不得重复添加。
- 如果错误与磁盘空间相关，可以添加一个步骤记录构建前后的磁盘空间变化，例如：
  ```yaml
  - name: Monitor Disk Space
    run: |
      echo "Checking disk space before build..."
      df -h > disk_space_before.log
      du -h /tmp -d 1 --no-dereference 2>/dev/null >> disk_space_before.log || echo "无法检查 /tmp 目录" >> disk_space_before.log
      du -h $HOME -d 1 --no-dereference 2>/dev/null >> disk_space_before.log || echo "无法检查 $HOME 目录" >> disk_space_before.log
      # 构建步骤完成后
      echo "Checking disk space after build..." >> disk_space_before.log
      df -h >> disk_space_before.log
      du -h /tmp -d 1 --no-dereference 2>/dev/null >> disk_space_before.log || echo "无法检查 /tmp 目录" >> disk_space_before.log
      du -h $HOME -d 1 --no-dereference 2>/dev/null >> disk_space_before.log || echo "无法检查 $HOME 目录" >> disk_space_before.log
  ```
- 如果错误是 `startup_failure` 或 `A sequence was not expected`，请检查 YAML 语法，确保文件末尾没有多余的换行符或空格。

请生成修复后的 debug.yml 文件，确保符合 GitHub Actions 的语法规范。
"""
                            }
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000
                    }

                    response = requests.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=base_timeout * (attempt + 1)
                    )

                    if response.status_code == 200:
                        result = response.json()
                        suggestion = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        yaml_start = suggestion.find("```yaml")
                        yaml_end = suggestion.rfind("```")
                        if yaml_start != -1 and yaml_end != -1 and yaml_end > yaml_start:
                            yaml_content = suggestion[yaml_start + 7:yaml_end].strip()
                            if not validate_yaml_content(workflow_file, yaml_content):
                                print("[DEBUG] DeepSeek 返回的 YAML 语法错误，尝试自动修复")
                                new_workflow = yaml.safe_load(yaml_content)
                                fixed_workflow = fix_yaml_nesting(new_workflow)
                                if fixed_workflow:
                                    with open(workflow_file, "w") as f:
                                        yaml.dump(fixed_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                                    print("[DEBUG] 已自动修复 DeepSeek 返回的 YAML 嵌套问题")
                                    if validate_yaml_content(workflow_file, yaml_content):
                                        print("[DEBUG] DeepSeek 修复后的 YAML 语法验证通过")
                                        fix_history["successful_fix"] = "DeepSeek API fix with nesting correction"
                                        fix_history["timestamp"] = datetime.now().isoformat()
                                        for error in cleaned_errors:
                                            history.add_deepseek_attempt(error, yaml_content, "Successful after nesting correction", True)
                                        history.add_to_fix_history(
                                            "DeepSeek API fix with nesting correction",
                                            None,
                                            None,
                                            True,
                                            modified_section=None,
                                            successful_steps=successful_steps
                                        )
                                        fixed_errors.add(cleaned_errors[0] if cleaned_errors else "unknown_error")
                                        for step in fixed_workflow["jobs"]["build"]["steps"]:
                                            step_name = step.get("name", step.get("uses", "unnamed"))
                                            if step_name in current_step_names:
                                                history.update_step_status(step_name, True)
                                        # 验证 YAML 语法后再推送
                                        print("[DEBUG] 修复完成，执行 Git 推送")
                                        success = push_changes_func(f"AutoDebug: Apply DeepSeek fix (iteration {iteration})", None, branch)
                                        if not success:
                                            print("[ERROR] 推送失败，停止后续操作")
                                            fix_history["errors"][cleaned_errors[0] if cleaned_errors else "unknown_error"]["failed_attempts"].append({"fix": "DeepSeek API fix", "reason": "推送失败"})
                                            with open(history_file, "w") as f:
                                                json.dump(fix_history, f, ensure_ascii=False, indent=2)
                                            return False
                                        return True
                                print("[DEBUG] 自动修复失败，回退到原始文件")
                                with open(workflow_file, "w") as f:
                                    yaml.dump(original_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                                for error in cleaned_errors:
                                    history.add_deepseek_attempt(error, yaml_content, "YAML syntax error after DeepSeek fix", False)
                                consecutive_failures += 1
                                time.sleep(5 * (attempt + 1))
                                continue

                            new_workflow = yaml.safe_load(yaml_content)
                            print(f"[DEBUG] DeepSeek 建议的 debug.yml:\n{yaml_content}")

                            if True in new_workflow:
                                print("[ERROR] DeepSeek 返回的 debug.yml 包含已知错误 'true'，尝试修复")
                                new_workflow = fix_yaml_true_field(new_workflow)
                                if new_workflow is None:
                                    print("[DEBUG] 修复 'true' 字段失败，回退到原始文件")
                                    with open(workflow_file, "w") as f:
                                        yaml.dump(original_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                                    for error in cleaned_errors:
                                        history.add_deepseek_attempt(error, yaml_content, "Contains 'true' field error", False)
                                    consecutive_failures += 1
                                    time.sleep(5 * (attempt + 1))
                                    continue

                            required_keys = ["name", "on", "jobs"]
                            missing_keys = [key for key in required_keys if key not in new_workflow]
                            if missing_keys:
                                print(f"[ERROR] DeepSeek 建议的 debug.yml 缺少必要字段: {missing_keys}")
                                for key in missing_keys:
                                    if key == "on":
                                        new_workflow["on"] = {
                                            "push": {"branches": ["main"]},
                                            "pull_request": {"branches": ["main"]}
                                        }
                                        print(f"[DEBUG] 自动补充缺失字段 'on': {new_workflow['on']}")
                                    elif key == "name":
                                        new_workflow["name"] = "WeatherApp CI"
                                        print(f"[DEBUG] 自动补充缺失字段 'name': {new_workflow['name']}")
                                    elif key == "jobs":
                                        new_workflow["jobs"] = {
                                            "build": {
                                                "runs-on": "Ubuntu-latest",
                                                "steps": []
                                            }
                                        }
                                        print(f"[DEBUG] 自动补充缺失字段 'jobs': {new_workflow['jobs']}")

                            if not isinstance(new_workflow.get("jobs", {}), dict) or "build" not in new_workflow["jobs"]:
                                print("[ERROR] DeepSeek 建议的 debug.yml 的 jobs 字段无效或缺少 build 作业")
                                for error in cleaned_errors:
                                    history.add_deepseek_attempt(error, yaml_content, "Invalid or missing 'build' job", False)
                                consecutive_failures += 1
                                time.sleep(5 * (attempt + 1))
                                continue

                            if not new_workflow["jobs"]["build"].get("runs-on"):
                                print("[ERROR] DeepSeek 建议的 debug.yml 的 build 作业缺少 runs-on")
                                new_workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
                                print("[DEBUG] 自动补充缺失字段 'runs-on': Ubuntu-latest")

                            steps = new_workflow["jobs"]["build"].get("steps", [])
                            if not steps:
                                print("[ERROR] DeepSeek 建议的 debug.yml 的 steps 列表为空")
                                for error in cleaned_errors:
                                    history.add_deepseek_attempt(error, yaml_content, "Steps list is empty", False)
                                consecutive_failures += 1
                                time.sleep(5 * (attempt + 1))
                                continue

                            # 移除功能重复的步骤
                            seen_functionalities = set()
                            unique_steps = []
                            for step in steps:
                                step_identifier = step.get("uses", step.get("name", "unnamed"))
                                # 检查功能重复
                                functionality_key = None
                                if "run" in step:
                                    run_content = step["run"].lower()
                                    if "df -h" in run_content and "du -h" in run_content:
                                        functionality_key = "check_disk_space"
                                    elif "ping" in run_content:
                                        functionality_key = "check_network"
                                    elif "rm -rf" in run_content or "apt-get clean" in run_content:
                                        functionality_key = "clean_disk_space"
                                if functionality_key:
                                    # 检查是否已经存在类似功能的步骤
                                    for existing_step in unique_steps:
                                        if check_step_functionality_similarity(step, existing_step):
                                            print(f"[DEBUG] 检测到功能重复步骤: {step_identifier}（功能: {functionality_key}），移除重复项")
                                            for error in cleaned_errors:
                                                history.add_deepseek_attempt(error, yaml_content, f"Duplicate functionality detected: {functionality_key}", False)
                                            break
                                    else:
                                        seen_functionalities.add(functionality_key)
                                        unique_steps.append(step)
                                else:
                                    unique_steps.append(step)

                            # 移除名称重复的步骤
                            seen_steps = set()
                            final_steps = []
                            for step in unique_steps:
                                step_identifier = step.get("uses", step.get("name", "unnamed"))
                                if step_identifier in seen_steps:
                                    print(f"[DEBUG] 检测到名称重复步骤: {step_identifier}，移除重复项")
                                    for error in cleaned_errors:
                                        history.add_deepseek_attempt(error, yaml_content, f"Duplicate step detected: {step_identifier}", False)
                                    continue
                                seen_steps.add(step_identifier)
                                final_steps.append(step)

                            # 重新排序步骤
                            final_steps = reorder_steps(final_steps, correct_steps)

                            # 确保必要步骤存在
                            current_steps = [step.get("name", step.get("uses", "unnamed")) for step in final_steps]
                            missing_required_steps = [step for step in correct_steps if step not in current_steps]
                            if missing_required_steps:
                                print(f"[DEBUG] DeepSeek 建议的 debug.yml 缺少必要步骤: {missing_required_steps}，自动补充")
                                required_steps_definitions = {
                                    "actions/checkout@v4": {"uses": "actions/checkout@v4"},
                                    "Set up JDK 17": {
                                        "name": "Set up JDK 17",
                                        "uses": "actions/setup-java@v3",
                                        "with": {
                                            "distribution": "temurin",
                                            "java-version": "17"
                                        }
                                    },
                                    "Set up Python": {
                                        "name": "Set up Python",
                                        "uses": "actions/setup-python@v5",
                                        "with": {
                                            "python-version": "3.10"
                                        }
                                    },
                                    "Install missing libtinfo package": {
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
                                    "Install system dependencies": {
                                        "name": "Install system dependencies",
                                        "run": """sudo apt-get update -y
sudo apt-get install -y git zip unzip python3-pip autoconf libtool pkg-config
sudo apt-get install -y zlib1g-dev libncurses5-dev libncursesw5-dev
sudo apt-get install -y cmake libffi-dev libssl-dev
sudo apt-get install -y libltdl-dev build-essential python3-dev python3-venv
sudo apt-get install -y libnss3-dev libnss3-tools"""
                                    },
                                    "Configure pip mirror": {
                                        "name": "Configure pip mirror",
                                        "run": """pip config set global.index-url https://pypi.org/simple/
pip config set global.trusted-host pypi.org"""
                                    },
                                    "Install Python dependencies": {
                                        "name": "Install Python dependencies",
                                        "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.0 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
pip install python-for-android"""
                                    },
                                    "Set up Android SDK": {
                                        "name": "Set up Android SDK",
                                        "uses": "android-actions/setup-android@v3",
                                        "with": {
                                            "accept-android-sdk-licenses": True,
                                            "cmdline-tools-version": "latest",
                                            "packages": "build-tools;34.0.0 platform-tools platforms;android-34 ndk;25.2.9519653"
                                        }
                                    },
                                    "Accept Android SDK Licenses": {
                                        "name": "Accept Android SDK Licenses",
                                        "run": """yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"""
                                    },
                                    "Download Android NDK with Retry": {
                                        "name": "Download Android NDK with Retry",
                                        "run": """NDK_URL="https://dl.google.com/android/repository/android-ndk-r25b-linux.zip"
NDK_PATH="$HOME/android-ndk-r25b.zip"
NDK_INSTALL_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
EXPECTED_MD5="e76f7b99f9e73ecee90f32c5e663f4339e0b0a1"
MAX_RETRIES=5
RETRY_DELAY=15
for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试下载 Android NDK (第 $i 次)..."
  curl -L -o "$NDK_PATH" "$NDK_URL" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60
  if [ $? -eq 0 ]; then
    DOWNLOADED_MD5=$(md5sum "$NDK_PATH" | awk '{print $1}')
    if [ "$DOWNLOADED_MD5" = "$EXPECTED_MD5" ]; then
      echo "NDK 下载成功，MD5 校验通过：$DOWNLOADED_MD5"
      break
    else
      echo "NDK 文件 MD5 校验失败，预期：$EXPECTED_MD5，实际：$DOWNLOADED_MD5"
      rm -f "$NDK_PATH"
    fi
  fi
  if [ $i -lt $MAX_RETRIES ]; then
    echo "下载失败，等待 $RETRY_DELAY 秒后重试..."
    sleep $RETRY_DELAY
  else
    echo "下载 Android NDK 失败，退出..."
    exit 1
  fi
done
mkdir -p "$HOME/.buildozer/android/platform"
unzip -q "$NDK_PATH" -d "$HOME/.buildozer/android/platform" || {
  echo "解压 NDK 失败，请检查文件完整性"
  exit 1
}
if [ -d "$NDK_INSTALL_DIR" ]; then
  echo "NDK 解压成功，路径：$NDK_INSTALL_DIR"
else
  echo "NDK 解压失败，未找到预期目录：$NDK_INSTALL_DIR"
  exit 1
fi
export ANDROID_NDK_HOME="$NDK_INSTALL_DIR"
echo "ANDROID_NDK_HOME=$ANDROID_NDK_HOME" >> $GITHUB_ENV"""
                                    },
                                    "Initialize Buildozer": {
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
android.ndk = 25b
android.ndk_path = $ANDROID_NDK_HOME
android.sdk_path = $ANDROID_HOME
android.accept_sdk_license = True
orientation = portrait
fullscreen = 0
log_level = 2
p4a.branch = master
EOF"""
                                    },
                                    "Prepare python-for-android": {
                                        "name": "Prepare python-for-android",
                                        "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                                    },
                                    "Set Custom Temp Directory": {
                                        "name": "Set Custom Temp Directory",
                                        "run": """mkdir -p $HOME/tmp
echo "TMPDIR=$HOME/tmp" >> $GITHUB_ENV
echo "TEMP=$HOME/tmp" >> $GITHUB_ENV
echo "TMP=$HOME/tmp" >> $GITHUB_ENV
export TMPDIR=$HOME/tmp
export TEMP=$HOME/tmp
export TMP=$HOME/tmp"""
                                    },
                                    "Build APK": {
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
buildozer -v android debug deploy 2>&1 | tee build.log || echo "Build failed but log generated" >> build.log
if [ ${PIPESTATUS[0]} -ne 0 ]; then
  cat build.log
  exit 1
fi"""
                                    },
                                    "Verify Build Log": {
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
                                    "Save Build Log": {
                                        "name": "Save Build Log",
                                        "if": "always()",
                                        "uses": "actions/upload-artifact@v4",
                                        "with": {
                                            "name": f"build-log-{run_id}",
                                            "path": "build.log",
                                            "retention-days": 1
                                        }
                                    },
                                    "Upload APK": {
                                        "name": "Upload APK",
                                        "if": "success()",
                                        "uses": "actions/upload-artifact@v4",
                                        "with": {
                                            "if-no-files-found": "error",
                                            "name": f"weatherapp-apk-{run_id}",
                                            "path": "bin/weatherapp-*.apk",
                                            "retention-days": 1
                                        }
                                    }
                                }
                                for missing_step in missing_required_steps:
                                    if missing_step in required_steps_definitions:
                                        final_steps.append(required_steps_definitions[missing_step])
                                        print(f"[DEBUG] 自动补充缺失步骤: {missing_step}")
                                new_workflow["jobs"]["build"]["steps"] = final_steps

                            valid_runners = ["Ubuntu-latest", "Ubuntu-22.04", "Ubuntu-20.04"]
                            runs_on = new_workflow["jobs"]["build"].get("runs-on", "").lower()
                            if runs_on not in [r.lower() for r in valid_runners]:
                                print(f"[WARNING] DeepSeek 建议的 runs-on: {runs_on} 无效，强制设置为 Ubuntu-latest")
                                new_workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"

                            for step in final_steps:
                                if step.get("name") in ["Save Build Log", "Upload APK"]:
                                    artifact_name = step.get("with", {}).get("name", "")
                                    if artifact_name:
                                        step["with"]["name"] = f"{artifact_name}-{run_id}"
                                        print(f"[DEBUG] 修改工件名称以避免冲突: {artifact_name} -> {step['with']['name']}")

                            # 写入文件并规范化格式
                            yaml_content = yaml.dump(new_workflow, sort_keys=False, indent=2, allow_unicode=True).rstrip() + '\n'
                            with open(workflow_file, "w") as f:
                                f.write(yaml_content)
                            print("[DEBUG] DeepSeek 修复已应用到 debug.yml（已保留受保护步骤并补充缺失步骤）")

                            fix_history["successful_fix"] = "DeepSeek API fix with preserved steps"
                            fix_history["timestamp"] = datetime.now().isoformat()
                            for error in cleaned_errors:
                                history.add_deepseek_attempt(error, yaml_content, "Successful DeepSeek fix", True)
                            history.add_to_fix_history(
                                "DeepSeek API fix with preserved steps",
                                None,
                                None,
                                True,
                                modified_section=None,
                                successful_steps=successful_steps
                            )
                            fixed_errors.add(cleaned_errors[0] if cleaned_errors else "unknown_error")
                            for step in new_workflow["jobs"]["build"]["steps"]:
                                step_name = step.get("name", step.get("uses", "unnamed"))
                                if step_name in current_step_names:
                                    history.update_step_status(step_name, True)
                            # 验证 YAML 语法后再推送
                            print("[DEBUG] 修复完成，执行 Git 推送")
                            success = push_changes_func(f"AutoDebug: Apply DeepSeek fix (iteration {iteration})", None, branch)
                            if not success:
                                print("[ERROR] 推送失败，停止后续操作")
                                fix_history["errors"][cleaned_errors[0] if cleaned_errors else "unknown_error"]["failed_attempts"].append({"fix": "DeepSeek API fix", "reason": "推送失败"})
                                with open(history