import yaml
import re
from autodebug.history import load_fix_history

def validate_yaml_syntax(file_path):
    """验证 YAML 文件的语法是否正确"""
    try:
        with open(file_path, "r") as f:
            yaml.safe_load(f)
        print("[DEBUG] YAML 语法验证通过")
        return True
    except yaml.YAMLError as e:
        print(f"[ERROR] YAML 语法错误: {e}")
        return False

def fix_yaml_nesting(steps, history_data):
    """修复 steps 列表中的多余嵌套问题，并移除所有重复步骤，同时保护已验证正确的步骤"""
    def fix_indent_recursive(obj, indent_level=0):
        """递归修复字典或列表中的缩进问题"""
        if isinstance(obj, list):
            fixed_list = []
            for item in obj:
                # 递归解包嵌套列表
                while isinstance(item, list):
                    if not item:  # 空列表
                        break
                    item = item[0] if len(item) == 1 else item
                if isinstance(item, dict):
                    fixed_item = fix_indent_recursive(item, indent_level + 1)
                    fixed_list.append(fixed_item)
                elif isinstance(item, list):
                    # 如果仍然是列表，继续递归处理
                    fixed_list.extend(fix_indent_recursive(item, indent_level + 1))
                elif item is not None:
                    fixed_list.append(item)
            return fixed_list
        elif isinstance(obj, dict):
            fixed_dict = {}
            for key, value in obj.items():
                if key == "with" and isinstance(value, dict):
                    fixed_with = {}
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, str) and sub_value.startswith("'") and sub_value.endswith("'"):
                            fixed_with[sub_key] = sub_value.strip("'")
                        else:
                            fixed_with[sub_key] = sub_value
                    fixed_dict[key] = fixed_with
                elif isinstance(value, (dict, list)):
                    fixed_dict[key] = fix_indent_recursive(value, indent_level + 1)
                else:
                    fixed_dict[key] = value
            return fixed_dict
        return obj

    fixed_steps = []
    seen_steps = set()  # 用于跟踪已添加的步骤名称
    for step in steps:
        # 递归解包嵌套
        step = fix_indent_recursive(step)
        if isinstance(step, list):
            # 如果解包后仍然是列表，可能是多步骤，继续处理
            for sub_step in step:
                if isinstance(sub_step, dict):
                    step_name = sub_step.get("name", sub_step.get("uses", "unnamed"))
                    if step_name in history_data.get("step_status", {}) and history_data["step_status"][step_name]["success"]:
                        print(f"[DEBUG] 步骤 '{step_name}' 已被验证正确，保留")
                        fixed_steps.append(sub_step)
                        seen_steps.add(step_name)
                    elif step_name not in seen_steps:
                        fixed_steps.append(sub_step)
                        seen_steps.add(step_name)
                        print(f"[DEBUG] 保留步骤: {step_name}")
                    else:
                        print(f"[DEBUG] 移除重复步骤: {step_name}")
                else:
                    print(f"[DEBUG] 忽略无效步骤: {sub_step}")
        elif isinstance(step, dict):
            step_name = step.get("name", step.get("uses", "unnamed"))
            if step_name in history_data.get("step_status", {}) and history_data["step_status"][step_name]["success"]:
                print(f"[DEBUG] 步骤 '{step_name}' 已被验证正确，保留")
                fixed_steps.append(step)
                seen_steps.add(step_name)
            elif step_name not in seen_steps:
                fixed_steps.append(step)
                seen_steps.add(step_name)
                print(f"[DEBUG] 保留步骤: {step_name}")
            else:
                print(f"[DEBUG] 移除重复步骤: {step_name}")
        else:
            print(f"[DEBUG] 忽略无效步骤: {step}")
    return fixed_steps

def validate_and_fix_debug_yml(workflow_file, default_fixes_applied=None, history_file=None):
    """验证并修复 debug.yml 的语法错误，确保包含所有必要步骤"""
    default_fixes_applied = default_fixes_applied or set()
    history_data = load_fix_history(history_file) if history_file else {"history": [], "step_status": {}}

    try:
        if not validate_yaml_syntax(workflow_file):
            print("[DEBUG] 检测到 YAML 语法错误，尝试加载并修复...")
            with open(workflow_file, "r") as f:
                content = f.read()
            workflow_content = None
            try:
                workflow_content = yaml.safe_load(content)
            except yaml.YAMLError:
                print("[DEBUG] 无法直接加载 YAML，使用默认结构...")
                workflow_content = {
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
                                    "run": """pip config set global.index-url https://pypi.org/simple/
pip config set global.trusted-host pypi.org"""
                                },
                                {
                                    "name": "Install Python dependencies",
                                    "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.1 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
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
                                    "name": "Accept Android SDK Licenses",
                                    "run": """yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"""
                                },
                                {
                                    "name": "Download Android NDK with Retry",
                                    "run": """NDK_URL="https://dl.google.com/android/repository/android-ndk-r25b-linux.zip"
NDK_PATH="$HOME/android-ndk-r25b.zip"
NDK_INSTALL_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
EXPECTED_MD5="c7e5b3c4b9e7d8f9a1b2c3d4e5f6a7b"  # 替换为实际的 MD5 校验和
MAX_RETRIES=5
RETRY_DELAY=15
for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试下载 Android NDK (第 $i 次)..."
  curl -L -o "$NDK_PATH" "$NDK_URL" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60
  if [ $? -eq 0 ]; then
    # 计算文件的 MD5 校验和
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
                                {
                                    "name": "Prepare python-for-android",
                                    "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                                },
                                {
                                    "name": "Set Custom Temp Directory",
                                    "run": """mkdir -p $HOME/tmp
echo "TMPDIR=$HOME/tmp" >> $GITHUB_ENV
echo "TEMP=$HOME/tmp" >> $GITHUB_ENV
echo "TMP=$HOME/tmp" >> $GITHUB_ENV
export TMPDIR=$HOME/tmp
export TEMP=$HOME/tmp
export TMP=$HOME/tmp"""
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
buildozer -v android debug deploy 2>&1 | tee build.log || echo "Build failed but log generated" >> build.log
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
                                }
                            ]
                        }
                    }
                }
        
        else:
            with open(workflow_file, "r") as f:
                workflow_content = yaml.safe_load(f)

        print(f"[DEBUG] 原始 workflow_content: {workflow_content}")

        if not workflow_content:
            print("[ERROR] debug.yml 为空或无效，初始化默认工作流")
            workflow_content = {
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
                                "run": """pip config set global.index-url https://pypi.org/simple/
pip config set global.trusted-host pypi.org"""
                            },
                            {
                                "name": "Install Python dependencies",
                                "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.1 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
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
                                "name": "Accept Android SDK Licenses",
                                "run": """yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"""
                            },
                            {
                                "name": "Download Android NDK with Retry",
                                "run": """NDK_URL="https://dl.google.com/android/repository/android-ndk-r25b-linux.zip"
NDK_PATH="$HOME/android-ndk-r25b.zip"
NDK_INSTALL_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
EXPECTED_MD5="c7e5b3c4b9e7d8f9a1b2c3d4e5f6a7b"  # 替换为实际的 MD5 校验和
MAX_RETRIES=5
RETRY_DELAY=15
for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试下载 Android NDK (第 $i 次)..."
  curl -L -o "$NDK_PATH" "$NDK_URL" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60
  if [ $? -eq 0 ]; then
    # 计算文件的 MD5 校验和
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
                            {
                                "name": "Prepare python-for-android",
                                "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                            },
                            {
                                "name": "Set Custom Temp Directory",
                                "run": """mkdir -p $HOME/tmp
echo "TMPDIR=$HOME/tmp" >> $GITHUB_ENV
echo "TEMP=$HOME/tmp" >> $GITHUB_ENV
echo "TMP=$HOME/tmp" >> $GITHUB_ENV
export TMPDIR=$HOME/tmp
export TEMP=$HOME/tmp
export TMP=$HOME/tmp"""
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
buildozer -v android debug deploy 2>&1 | tee build.log || echo "Build failed but log generated" >> build.log
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
                            }
                        ]
                    }
                }
            }

        if not workflow_content["jobs"]["build"].get("runs-on"):
            print("[ERROR] debug.yml 的 build 作业缺少 runs-on，设置为默认值")
            workflow_content["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
        valid_runners = ["Ubuntu-latest", "Ubuntu-22.04", "Ubuntu-20.04"]
        runs_on = workflow_content["jobs"]["build"].get("runs-on", "").lower()
        if runs_on not in [r.lower() for r in valid_runners]:
            print(f"[WARNING] runs-on: {runs_on} 可能无效，强制设置为 Ubuntu-latest")
            workflow_content["jobs"]["build"]["runs-on"] = "Ubuntu-latest"

        steps = workflow_content["jobs"]["build"].get("steps", [])
        if not steps:
            print("[ERROR] debug.yml 的 steps 列表为空，添加必要步骤")
            workflow_content["jobs"]["build"]["steps"] = [
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
                    "run": """pip config set global.index-url https://pypi.org/simple/
pip config set global.trusted-host pypi.org"""
                },
                {
                    "name": "Install Python dependencies",
                    "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.1 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
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
                    "name": "Accept Android SDK Licenses",
                    "run": """yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"""
                },
                {
                    "name": "Download Android NDK with Retry",
                    "run": """NDK_URL="https://dl.google.com/android/repository/android-ndk-r25b-linux.zip"
NDK_PATH="$HOME/android-ndk-r25b.zip"
NDK_INSTALL_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
EXPECTED_MD5="c7e5b3c4b9e7d8f9a1b2c3d4e5f6a7b"  # 替换为实际的 MD5 校验和
MAX_RETRIES=5
RETRY_DELAY=15
for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试下载 Android NDK (第 $i 次)..."
  curl -L -o "$NDK_PATH" "$NDK_URL" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60
  if [ $? -eq 0 ]; then
    # 计算文件的 MD5 校验和
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
                {
                    "name": "Prepare python-for-android",
                    "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                },
                {
                    "name": "Set Custom Temp Directory",
                    "run": """mkdir -p $HOME/tmp
echo "TMPDIR=$HOME/tmp" >> $GITHUB_ENV
echo "TEMP=$HOME/tmp" >> $GITHUB_ENV
echo "TMP=$HOME/tmp" >> $GITHUB_ENV
export TMPDIR=$HOME/tmp
export TEMP=$HOME/tmp
export TMP=$HOME/tmp"""
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
buildozer -v android debug deploy 2>&1 | tee build.log || echo "Build failed but log generated" >> build.log
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
                }
            ]

        # 验证每个步骤的格式，允许 'uses' 步骤没有 'name'
        validated_steps = []
        for step in workflow_content["jobs"]["build"]["steps"]:
            if not isinstance(step, dict):
                print(f"[DEBUG] 忽略无效步骤（非字典对象）: {step}")
                continue
            # 修改验证逻辑，允许 'uses' 步骤没有 'name' 字段
            if "run" in step or "uses" in step:
                validated_steps.append(step)
            else:
                print(f"[DEBUG] 忽略无效步骤（缺少 'run' 或 'uses' 字段）：{step}")
                continue

        workflow_content["jobs"]["build"]["steps"] = fix_yaml_nesting(validated_steps, history_data)

        # 确保 steps 包含所有必要步骤
        required_steps = [
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
        ]
        current_steps = [step.get("uses", step.get("name", "unnamed")) for step in workflow_content["jobs"]["build"]["steps"]]
        missing_steps = [step for step in required_steps if step not in current_steps]
        if missing_steps:
            print(f"[DEBUG] 检测到缺少必要步骤: {missing_steps}，自动补充...")
            full_steps = [
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
                    "run": """pip config set global.index-url https://pypi.org/simple/
pip config set global.trusted-host pypi.org"""
                },
                {
                    "name": "Install Python dependencies",
                    "run": """python -m pip install --upgrade pip setuptools
pip install buildozer==1.5.1 kivy==2.3.1 requests==2.25.1 cython==0.29.36 certifi
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
                    "name": "Accept Android SDK Licenses",
                    "run": """yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses || true"""
                },
                {
                    "name": "Download Android NDK with Retry",
                    "run": """NDK_URL="https://dl.google.com/android/repository/android-ndk-r25b-linux.zip"
NDK_PATH="$HOME/android-ndk-r25b.zip"
NDK_INSTALL_DIR="$HOME/.buildozer/android/platform/android-ndk-r25b"
EXPECTED_MD5="c7e5b3c4b9e7d8f9a1b2c3d4e5f6a7b"  # 替换为实际的 MD5 校验和
MAX_RETRIES=5
RETRY_DELAY=15
for i in $(seq 1 $MAX_RETRIES); do
  echo "尝试下载 Android NDK (第 $i 次)..."
  curl -L -o "$NDK_PATH" "$NDK_URL" --retry 5 --retry-delay 5 --retry-max-time 600 --connect-timeout 60
  if [ $? -eq 0 ]; then
    # 计算文件的 MD5 校验和
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
                {
                    "name": "Prepare python-for-android",
                    "run": """mkdir -p .buildozer/android/platform
git clone https://github.com/kivy/python-for-android.git .buildozer/android/platform/python-for-android
cd .buildozer/android/platform/python-for-android
git checkout master"""
                },
                {
                    "name": "Set Custom Temp Directory",
                    "run": """mkdir -p $HOME/tmp
echo "TMPDIR=$HOME/tmp" >> $GITHUB_ENV
echo "TEMP=$HOME/tmp" >> $GITHUB_ENV
echo "TMP=$HOME/tmp" >> $GITHUB_ENV
export TMPDIR=$HOME/tmp
export TEMP=$HOME/tmp
export TMP=$HOME/tmp"""
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
buildozer -v android debug deploy 2>&1 | tee build.log || echo "Build failed but log generated" >> build.log
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
                }
            ]
            # 保留已有的非必要步骤（如 Initial Trigger Step）
            for step in workflow_content["jobs"]["build"]["steps"]:
                step_name = step.get("name", step.get("uses", "unnamed"))
                if step_name not in required_steps:
                    full_steps.append(step)
            workflow_content["jobs"]["build"]["steps"] = fix_yaml_nesting(full_steps, history_data)

        if True in workflow_content or "true" in workflow_content:
            print("[DEBUG] 发现 debug.yml 中存在 'true:' 语法错误，修复为 'on:'")
            true_field = workflow_content.pop(True, None) or workflow_content.pop("true", None)
            if true_field:
                if isinstance(true_field, list):
                    print("[DEBUG] 'true:' 字段为列表形式，转换为标准格式")
                    new_on = {}
                    for trigger in true_field:
                        new_on[trigger] = {"branches": ["main"]}
                    workflow_content["on"] = new_on
                else:
                    workflow_content["on"] = {
                        "push": {"branches": ["main"]},
                        "pull_request": {"branches": ["main"]}
                    }
            else:
                print("[DEBUG] 未成功提取 true 字段，强制添加 on 字段")
                workflow_content["on"] = {
                    "push": {"branches": ["main"]},
                    "pull_request": {"branches": ["main"]}
                }

        if "on" not in workflow_content or not workflow_content["on"]:
            print("[DEBUG] debug.yml 中缺少有效的 'on' 字段，添加默认触发器")
            workflow_content["on"] = {
                "push": {"branches": ["main"]},
                "pull_request": {"branches": ["main"]}
            }
        else:
            on_field = workflow_content["on"]
            if isinstance(on_field, list):
                print("[DEBUG] 检测到 on 字段的简写格式，转换为标准格式")
                new_on = {}
                for trigger in on_field:
                    new_on[trigger] = {"branches": ["main"]}
                on_field = new_on
            if on_field is True:
                print("[DEBUG] on 字段是布尔值 True，替换为标准格式")
                on_field = {
                    "push": {"branches": ["main"]},
                    "pull_request": {"branches": ["main"]}
                }
            if "push" not in on_field:
                print("[DEBUG] debug.yml 的 'on' 字段缺少 'push' 触发器，添加默认值")
                on_field["push"] = {"branches": ["main"]}
            if "pull_request" not in on_field:
                print("[DEBUG] debug.yml 的 'on' 字段缺少 'pull_request' 触发器，添加默认值")
                on_field["pull_request"] = {"branches": ["main"]}
            for trigger in on_field:
                if not isinstance(on_field[trigger], dict):
                    on_field[trigger] = {"branches": ["main"]}
            workflow_content["on"] = on_field

        if "permissions" not in workflow_content or workflow_content["permissions"] != {"contents": "write"}:
            print("[DEBUG] 添加或更新 debug.yml 的 permissions 为 contents: write")
            workflow_content["permissions"] = {"contents": "write"}

        with open(workflow_file, "w") as f:
            yaml.safe_dump(workflow_content, f, sort_keys=False, indent=2, allow_unicode=True)
        print("[DEBUG] 已修复 debug.yml 语法")

        if not validate_yaml_syntax(workflow_file):
            print("[ERROR] 修复后的 debug.yml 仍存在语法错误，停止程序")
            with open(workflow_file, "r") as f:
                content = f.read()
            print(f"[DEBUG] 修复后的 debug.yml 内容:\n{content}")
            raise Exception("修复后的 debug.yml 语法错误")

        print(f"[DEBUG] 修复后的 workflow_content: {workflow_content}")
        return True
    except Exception as e:
        print(f"[ERROR] 验证并修复 debug.yml 失败: {e}")
        return False

def clean_workflow(workflow_file, default_fixes_applied):
    """清理工作流文件中的错误字段（已整合到 validate_and_fix_debug_yml）"""
    return validate_and_fix_debug_yml(workflow_file, default_fixes_applied)

def ensure_on_field(workflow_file):
    """确保工作流文件包含有效的 on 字段（已整合到 validate_and_fix_debug_yml）"""
    return validate_and_fix_debug_yml(workflow_file)

def save_workflow(workflow, workflow_file):
    """保存工作流文件（已整合到 validate_and_fix_debug_yml）"""
    try:
        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        print("[DEBUG] workflow 已保存到 debug.yml")
        return True
    except Exception as e:
        print(f"[ERROR] 保存 workflow 失败: {e}")
        return False