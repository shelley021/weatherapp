import json
import os

def load_error_patterns(patterns_file="error_patterns.json"):
    """加载错误模式"""
    default_patterns = [
        {
            "pattern": r"sdkmanager: command not found",
            "fix": {
                "step_name": "Install Android SDK Tools",
                "step_code": """
        - name: Install Android SDK Tools
          run: |
            sdkmanager --install "cmdline-tools;latest"
            sdkmanager --install "build-tools;33.0.0"
            sdkmanager --install "platforms;android-33"
            sdkmanager --install "platform-tools"
            echo "ANDROID_HOME=$ANDROID_HOME" >> $GITHUB_ENV
            echo "PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin" >> $GITHUB_ENV
            echo "PATH=$PATH:$ANDROID_HOME/platform-tools" >> $GITHUB_ENV
"""
            }
        },
        {
            "pattern": r"Could not determine java version|java: command not found",
            "fix": {
                "step_name": "Set up JDK 17",
                "step_code": """
        - name: Set up JDK 17
          uses: actions/setup-java@v4
          with:
            java-version: '17'
            distribution: 'temurin'
"""
            }
        },
        {
            "pattern": r"No such file or directory:.*gradlew",
            "fix": {
                "step_name": "Make gradlew executable",
                "step_code": """
        - name: Make gradlew executable
          run: chmod +x ./gradlew
"""
            }
        },
        {
            "pattern": r"Invalid workflow file",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None
            }
        },
        {
            "pattern": r"Unexpected value '(\w+)'",
            "fix": {
                "step_name": "Fix unexpected value",
                "step_code": None
            }
        }
    ]

    if os.path.exists(patterns_file):
        try:
            with open(patterns_file, "r") as f:
                loaded_patterns = json.load(f)
            return loaded_patterns
        except Exception as e:
            print(f"[ERROR] 加载错误模式失败: {e}")
    return default_patterns

def save_error_patterns(patterns, patterns_file="error_patterns.json"):
    """保存错误模式"""
    try:
        with open(patterns_file, "w") as f:
            json.dump(patterns, f, indent=2)
        print("[DEBUG] 错误模式已保存")
    except Exception as e:
        print(f"[ERROR] 保存错误模式失败: {e}")

def update_error_patterns(new_patterns, patterns_file="error_patterns.json"):
    """更新错误模式"""
    patterns = load_error_patterns(patterns_file)
    for pattern in new_patterns:
        if pattern not in [p["pattern"] for p in patterns]:
            patterns.append({"pattern": pattern, "fix": {"step_name": "Dynamic fix", "step_code": None}})
    save_error_patterns(patterns, patterns_file)
    return patterns