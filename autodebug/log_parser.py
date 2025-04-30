import re
import yaml
import os

def parse_log_content(log_content, workflow_file, annotations_error, error_details, successful_steps, config):
    """解析日志内容以提取错误信息和上下文"""
    errors = []
    error_contexts = []
    exit_codes = []
    new_error_patterns = config.get('new_error_patterns', [])
    
    # 定义错误模式，扩展到 40+ 种，覆盖更多 GitHub Actions 错误场景
    error_patterns = [
        # 环境和依赖问题
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
            "pattern": r"command not found",
            "fix": {
                "step_name": "Install Missing Command",
                "step_code": None  # 需要动态确定缺少的命令
            }
        },
        {
            "pattern": r"Unable to locate package",
            "fix": {
                "step_name": "Update Package Lists",
                "step_code": """
        - name: Update Package Lists
          run: |
            sudo apt-get update
"""
            }
        },
        {
            "pattern": r"permission denied",
            "fix": {
                "step_name": "Fix Permissions",
                "step_code": """
        - name: Fix Permissions
          run: |
            chmod +x ./script.sh  # 根据具体文件调整
"""
            }
        },
        # 文件和路径问题
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
            "pattern": r"No such file or directory",
            "fix": {
                "step_name": "Check File Path",
                "step_code": None  # 需要动态检查文件路径
            }
        },
        {
            "pattern": r"Input string was not in a correct format",
            "fix": {
                "step_name": "Validate File Format",
                "step_code": None  # 需要检查文件格式
            }
        },
        {
            "pattern": r"The process cannot access the file",
            "fix": {
                "step_name": "Close File Handles",
                "step_code": """
        - name: Close File Handles
          run: |
            echo "Ensure no other process is using the file"
"""
            }
        },
        # 网络和 API 问题
        {
            "pattern": r"Failed to connect|Connection timed out",
            "fix": {
                "step_name": "Check Network Connection",
                "step_code": """
        - name: Check Network Connection
          run: |
            ping -c 4 google.com || echo "Network connection failed, please check network"
"""
            }
        },
        {
            "pattern": r"HTTP 404: Not Found|Unable to locate build via Github Actions API",
            "fix": {
                "step_name": "Verify API Token",
                "step_code": """
        - name: Verify API Token
          run: |
            echo "Ensure GITHUB_TOKEN or repository token is correctly set"
"""
            }
        },
        # 构建和测试问题
        {
            "pattern": r"FAILED \(failures=\d+\)",
            "fix": {
                "step_name": "Review Test Failures",
                "step_code": None  # 需要查看测试日志
            }
        },
        {
            "pattern": r"Test Run Failed",
            "fix": {
                "step_name": "Review Test Failures",
                "step_code": None  # 需要查看测试日志
            }
        },
        {
            "pattern": r"Coverage below threshold|Unable to publish code coverage",
            "fix": {
                "step_name": "Adjust Coverage Settings",
                "step_code": """
        - name: Adjust Coverage Settings
          run: |
            echo "Review coverage threshold settings in your test configuration"
"""
            }
        },
        {
            "pattern": r"ValueError: read of closed file",
            "fix": {
                "step_name": "Retry Android NDK Download",
                "step_code": """
        - name: Retry Android NDK Download
          run: |
            ping -c 4 google.com || echo "网络连接失败，请检查网络"
            for i in {1..3}; do
              echo "尝试下载 Android NDK，第 $i 次"
              buildozer android debug && break
              echo "下载失败，等待 10 秒后重试..."
              sleep 10
            done
"""
            }
        },
        # 工作流配置问题
        {
            "pattern": r"Invalid workflow file",
            "fix": {
                "step_name": "Fix workflow file",
                "step_code": None  # 占位符，实际修复依赖 clean_workflow 或 ensure_on_field
            }
        },
        {
            "pattern": r"runs-on.*not supported",
            "fix": {
                "step_name": "Fix runs-on",
                "step_code": """
        - name: Fix runs-on
          run: |
            echo "Change runs-on to 'Ubuntu-latest'"
"""
            }
        },
        {
            "pattern": r"Unexpected value '(\w+)'",
            "fix": {
                "step_name": "Fix unexpected value",
                "step_code": None  # 占位符，动态生成修复
            }
        },
        {
            "pattern": r"Syntax error",
            "fix": {
                "step_name": "Fix Syntax Error",
                "step_code": None  # 需要检查工作流语法
            }
        },
        # 资源和超时问题
        {
            "pattern": r"Timed out after \d+ seconds",
            "fix": {
                "step_name": "Increase Timeout",
                "step_code": """
        - name: Increase Timeout
          run: |
            echo "Increase timeout in workflow configuration"
"""
            }
        },
        {
            "pattern": r"Resource contention|Out of memory",
            "fix": {
                "step_name": "Optimize Resource Usage",
                "step_code": """
        - name: Optimize Resource Usage
          run: |
            echo "Reduce resource usage or upgrade runner"
"""
            }
        },
        # 其他通用错误
        {
            "pattern": r"Exception: ",
            "fix": {
                "step_name": "Handle Exception",
                "step_code": None  # 需要查看具体异常
            }
        },
        {
            "pattern": r"Error: ",
            "fix": {
                "step_name": "Handle Generic Error",
                "step_code": None  # 需要查看具体错误
            }
        },
        {
            "pattern": r"failed to execute|cannot execute",
            "fix": {
                "step_name": "Check Execution Command",
                "step_code": None  # 需要检查命令
            }
        },
        {
            "pattern": r"Requested resource not found",
            "fix": {
                "step_name": "Verify Resource",
                "step_code": """
        - name: Verify Resource
          run: |
            echo "Ensure the requested resource exists"
"""
            }
        },
        # 新增错误模式：语言/工具特定错误
        {
            "pattern": r"ModuleNotFoundError: No module named",
            "fix": {
                "step_name": "Install Python Dependencies",
                "step_code": """
        - name: Install Python Dependencies
          run: |
            pip install -r requirements.txt
"""
            }
        },
        {
            "pattern": r"npm ERR!|Cannot find module",
            "fix": {
                "step_name": "Install Node.js Dependencies",
                "step_code": """
        - name: Install Node.js Dependencies
          run: |
            npm install
"""
            }
        },
        {
            "pattern": r"Maven dependency resolution failed",
            "fix": {
                "step_name": "Retry Maven Dependency Download",
                "step_code": """
        - name: Retry Maven Dependency Download
          run: |
            mvn dependency:resolve -U
"""
            }
        },
        {
            "pattern": r"Docker: Cannot connect to the Docker daemon",
            "fix": {
                "step_name": "Setup Docker",
                "step_code": """
        - name: Setup Docker
          run: |
            sudo systemctl start docker
"""
            }
        },
        {
            "pattern": r"CMake Error",
            "fix": {
                "step_name": "Install CMake",
                "step_code": """
        - name: Install CMake
          run: |
            sudo apt-get install cmake
"""
            }
        },
        # 新增错误模式：权限和认证问题
        {
            "pattern": r"remote: Permission to.*denied",
            "fix": {
                "step_name": "Setup GitHub Token",
                "step_code": """
        - name: Setup GitHub Token
          run: |
            echo "Ensure GITHUB_TOKEN is set with proper permissions"
"""
            }
        },
        {
            "pattern": r"SSH: Could not resolve hostname",
            "fix": {
                "step_name": "Setup SSH Key",
                "step_code": """
        - name: Setup SSH Key
          uses: webfactory/ssh-agent@v0.5.4
          with:
            ssh-private-key: ${{ secrets.SSH_PRIVATE_KEY }}
"""
            }
        },
        {
            "pattern": r"Authentication failed",
            "fix": {
                "step_name": "Verify Credentials",
                "step_code": """
        - name: Verify Credentials
          run: |
            echo "Check credentials or tokens used in the workflow"
"""
            }
        },
        # 新增错误模式：缓存和依赖解析问题
        {
            "pattern": r"Failed to restore cache",
            "fix": {
                "step_name": "Clear Cache",
                "step_code": """
        - name: Clear Cache
          run: |
            echo "Cache may be corrupted, consider clearing it manually"
"""
            }
        },
        {
            "pattern": r"Could not resolve dependencies",
            "fix": {
                "step_name": "Retry Dependency Resolution",
                "step_code": """
        - name: Retry Dependency Resolution
          run: |
            npm install --force || yarn install --force
"""
            }
        },
        # 新增错误模式：构建工具特定错误
        {
            "pattern": r"Gradle build failed",
            "fix": {
                "step_name": "Run Gradle with Stacktrace",
                "step_code": """
        - name: Run Gradle with Stacktrace
          run: |
            ./gradlew build --stacktrace
"""
            }
        },
        {
            "pattern": r"make:.*Error",
            "fix": {
                "step_name": "Install Make",
                "step_code": """
        - name: Install Make
          run: |
            sudo apt-get install make
"""
            }
        },
        {
            "pattern": r"MSBuild.*failed",
            "fix": {
                "step_name": "Setup MSBuild",
                "step_code": """
        - name: Setup MSBuild
          uses: microsoft/setup-msbuild@v1
"""
            }
        },
        # 新增错误模式：操作系统/环境特定问题
        {
            "pattern": r"ld: library not found",
            "fix": {
                "step_name": "Install Missing Libraries (macOS)",
                "step_code": """
        - name: Install Missing Libraries (macOS)
          run: |
            brew install <library-name>  # 根据具体库调整
"""
            }
        },
        {
            "pattern": r"dpkg: error processing",
            "fix": {
                "step_name": "Fix Dpkg Issues",
                "step_code": """
        - name: Fix Dpkg Issues
          run: |
            sudo dpkg --configure -a
            sudo apt-get install -f
"""
            }
        },
        # 新增错误模式：其他边缘错误
        {
            "pattern": r"Disk space is low|No space left on device",
            "fix": {
                "step_name": "Clean Disk Space",
                "step_code": """
        - name: Clean Disk Space
          run: |
            df -h
            sudo apt-get clean
            docker system prune -a -f
"""
            }
        },
        {
            "pattern": r"Symbolic link loop detected",
            "fix": {
                "step_name": "Fix Symbolic Links",
                "step_code": """
        - name: Fix Symbolic Links
          run: |
            echo "Remove or fix broken symbolic links"
"""
            }
        },
        {
            "pattern": r"UnicodeDecodeError|Invalid byte sequence",
            "fix": {
                "step_name": "Fix Encoding Issues",
                "step_code": """
        - name: Fix Encoding Issues
          run: |
            export LANG=C.UTF-8
            export LC_ALL=C.UTF-8
"""
            }
        },
        {
            "pattern": r"Segmentation fault",
            "fix": {
                "step_name": "Debug Segmentation Fault",
                "step_code": """
        - name: Debug Segmentation Fault
          run: |
            echo "Run with a debugger to identify the issue (e.g., gdb)"
"""
            }
        },
        {
            "pattern": r"Invalid credentials for",
            "fix": {
                "step_name": "Update Credentials",
                "step_code": """
        - name: Update Credentials
          run: |
            echo "Update credentials in secrets or configuration"
"""
            }
        }
    ]

    # 定义关键错误模式，扩展以捕获更多错误
    critical_errors = [
        r"command not found",
        r"failed to execute",
        r"error: ",
        r"No steps executed",
        r"Invalid workflow file",
        r"runs-on.*not supported",
        r"E: Unable to locate package",
        r"failed with exit code",
        r"permission denied",
        r"not found",
        r"##\[error\]",
        r"failed: ",
        r"exception: ",
        r"cannot ",
        r"unable to ",
        r"ValueError: ",
        r"Timed out after",
        r"Out of memory",
        r"Connection timed out",
        r"Syntax error",
        r"ModuleNotFoundError: ",
        r"npm ERR!",
        r"Maven dependency resolution failed",
        r"Docker: Cannot connect",
        r"CMake Error",
        r"remote: Permission to",
        r"SSH: Could not resolve",
        r"Authentication failed",
        r"Failed to restore cache",
        r"Could not resolve dependencies",
        r"Gradle build failed",
        r"make:.*Error",
        r"MSBuild.*failed",
        r"ld: library not found",
        r"dpkg: error processing",
        r"No space left on device",
        r"Symbolic link loop detected",
        r"UnicodeDecodeError",
        r"Segmentation fault",
        r"Invalid credentials for"
    ]

    try:
        lines = log_content.splitlines()
        current_step = None
        error_lines = []

        # 打印日志行数以便调试
        print(f"[DEBUG] 日志总行数: {len(lines)}")

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
                    print(f"[DEBUG] 检测到错误行 {i}: {line}")
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
                    context_start = max(0, i - 10)
                    context_end = min(len(lines), i + 11)
                    context_lines = lines[context_start:context_end]
                    error_contexts.append({
                        "error_line": line.strip(),
                        "context": "\n".join(context_lines),
                        "step": step,
                        "line_number": i
                    })
                    break

        # 如果有 annotations_error，添加到错误列表
        if annotations_error:
            errors.append(annotations_error)
            error_contexts.append({
                "error_line": annotations_error,
                "context": annotations_error,
                "step": None,
                "line_number": None
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
                elif "permission denied" in line.lower():
                    new_pattern = r"permission denied"
                elif "failed: " in line.lower():
                    new_pattern = r"failed: "
                elif "cannot " in line.lower():
                    new_pattern = r"cannot "
                if new_pattern and new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                    new_error_patterns.append(new_pattern)
                    print(f"[DEBUG] 检测到新错误模式: {new_pattern}")
                    config['new_error_patterns'] = new_error_patterns

        # 打印提取的错误信息
        print(f"[DEBUG] 提取的错误信息: {errors}")
        print(f"[DEBUG] 错误上下文: {error_contexts}")
        print(f"[DEBUG] 退出代码: {exit_codes}")

        # 如果没有提取到错误，但有退出代码，记录通用错误
        if not errors and exit_codes:
            errors.append(f"Process failed with exit code {exit_codes[0]}")
            error_contexts.append({
                "error_line": f"Process failed with exit code {exit_codes[0]}",
                "context": "No specific error message found in logs",
                "step": None,
                "line_number": None
            })
            print(f"[DEBUG] 未找到具体错误，但检测到退出代码: {exit_codes}")

        return errors, error_contexts, exit_codes, new_error_patterns

    except Exception as e:
        print(f"[ERROR] 解析日志内容失败: {e}")
        return errors, error_contexts, exit_codes, new_error_patterns