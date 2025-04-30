import re
import yaml
import os

def parse_log_content(log_content, workflow_file, annotations_error, error_details, successful_steps, config):
    """解析日志内容以提取错误信息和上下文"""
    errors = []
    error_contexts = []
    exit_codes = []
    new_error_patterns = config.get('new_error_patterns', [])
    
    # 定义错误模式（从 log_retriever.py 中提取并统一管理）
    error_patterns = [
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
                "step_code": None  # 占位符，实际修复依赖 clean_workflow 或 ensure_on_field
            }
        },
        {
            "pattern": r"Unexpected value '(\w+)'",
            "fix": {
                "step_name": "Fix unexpected value",
                "step_code": None  # 占位符，动态生成修复
            }
        }
    ]

    # 定义关键错误模式（与 log_retriever.py 中的 critical_errors 一致）
    critical_errors = [
        r"command not found",
        r"failed to execute",
        r"error: ",
        r"No steps executed",
        r"Invalid workflow file",
        r"runs-on.*not supported",
        r"E: Unable to locate package",
    ]

    try:
        lines = log_content.splitlines()
        current_step = None
        error_lines = []

        # 提取错误行，使用更广泛的模式
        for i, line in enumerate(lines):
            step_match = re.match(r"^\d+\s*Run\s+(.+?)$", line)
            if step_match:
                current_step = step_match.group(1).strip()
                continue

            # 使用 critical_errors 中的模式检测错误
            error_detected = False
            for error_pattern in critical_errors:
                if re.search(error_pattern, line, re.IGNORECASE):
                    error_lines.append((i, line, current_step))
                    error_detected = True
                    break

            # 提取退出代码
            exit_code_match = re.search(r"##\[error\]Process completed with exit code (\d+)", line)
            if exit_code_match:
                exit_codes.append(int(exit_code_match.group(1)))

        # 提取错误信息和上下文
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            for i, line, step in error_lines:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    context_lines = lines[max(0, i-5):i+6]
                    error_contexts.append({
                        "error_line": line.strip(),
                        "context": "\n".join(context_lines),
                        "step": step
                    })
                    break

        # 如果有 annotations_error，添加到错误列表
        if annotations_error:
            errors.append(annotations_error)
            error_contexts.append({
                "error_line": annotations_error,
                "context": annotations_error,
                "step": None
            })

        # 检测新错误模式
        for line in lines:
            for pattern_info in error_patterns:
                pattern = pattern_info["pattern"]
                if re.search(pattern, line, re.IGNORECASE):
                    continue
                new_pattern = None
                if "not found" in line.lower():
                    new_pattern = r"not found"
                elif "failed to execute" in line.lower():
                    new_pattern = r"failed to execute"
                if new_pattern and new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                    new_error_patterns.append(new_pattern)
                    print(f"[DEBUG] 检测到新错误模式: {new_pattern}")
                    config['new_error_patterns'] = new_error_patterns

        return errors, error_contexts, exit_codes, new_error_patterns

    except Exception as e:
        print(f"[ERROR] 解析日志内容失败: {e}")
        return errors, error_contexts, exit_codes, new_error_patterns