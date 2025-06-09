import re
import yaml
from datetime import datetime
from autodebug.error_patterns import load_error_patterns

def extract_context(log_content, error_line, context_lines=5):
    """提取错误行的前后上下文，增强特定错误的上下文提取"""
    lines = log_content.splitlines()
    error_index = -1
    for i, line in enumerate(lines):
        if error_line in line:
            error_index = i
            break
    if error_index == -1:
        print(f"[DEBUG] 未找到错误行: {error_line}")
        return "上下文未找到"
    
    # 针对特定错误提取更多上下文（例如 Python 堆栈跟踪）
    if "valueerror: read of closed file" in error_line.lower():
        print(f"[DEBUG] 检测到 ValueError: read of closed file，增强上下文提取")
        context_lines_list = [lines[error_index]]
        j = error_index - 1
        while j >= 0 and j >= error_index - 10:  # 扩展到10行，捕获更多堆栈
            if "File " in lines[j] and ".py" in lines[j]:
                context_lines_list.insert(0, lines[j])
            j -= 1
        j = error_index + 1
        while j < len(lines) and j <= error_index + 10:
            if "File " in lines[j] and ".py" in lines[j]:
                context_lines_list.append(lines[j])
            j += 1
        return "\n".join(context_lines_list)
    
    # 默认上下文提取
    start_index = max(0, error_index - context_lines)
    end_index = min(len(lines), error_index + context_lines + 1)
    context = "\n".join(lines[start_index:end_index])
    print(f"[DEBUG] 默认上下文提取，行 {start_index} 到 {end_index}")
    return context

def parse_log_content(log_content, workflow_file, annotations_error, error_details, successful_steps, config):
    """从日志内容中提取错误信息、上下文、退出码和错误模式"""
    
    # 检查日志内容是否为空
    if not log_content:
        print("[DEBUG] 日志内容为空，无法解析")
        return [], [], [], [], [], []

    # 初始化返回值
    errors = []
    error_contexts = []
    exit_codes = []
    warnings = []
    failed_messages = []  # 新增：存储 failed 相关信息
    new_error_patterns = config.get('new_error_patterns', [])
    
    # 从 error_patterns.py 加载错误模式
    error_patterns = load_error_patterns()
    
    # 处理日志编码，去除 BOM 标记
    try:
        log_content = log_content.encode('utf-8').decode('utf-8-sig')
    except Exception as e:
        print(f"[ERROR] 日志内容编码处理失败: {e}")

    # 分割日志内容为行，确保正确处理编码
    try:
        log_lines = log_content.splitlines()
    except Exception as e:
        print(f"[ERROR] 日志内容分割失败: {e}")
        return [], [], [], [], [], error_patterns

    current_error = []
    current_context = []
    in_traceback = False
    error_start_line = 0
    current_step = None
    warning_lines = []
    successful_steps_list = []
    specific_error_found = False  # 标记是否找到具体错误

    # 打印日志行数以便调试
    print(f"[DEBUG] 日志总行数: {len(log_lines)}")

    # 遍历日志行，提取错误、警告、退出码、失败信息和成功步骤
    for i, line in enumerate(log_lines):
        # 提取当前步骤
        step_match = re.match(r"^\d+\s*Run\s+(.+?)$", line)
        if step_match:
            current_step = step_match.group(1).strip()
            print(f"[DEBUG] 当前步骤: {current_step}")
            continue

        # 优先提取堆栈跟踪（增强：支持更灵活的堆栈格式）
        if "Traceback (most recent call last):" in line or (line.strip().startswith("File ") and ".py" in line and not in_traceback):
            in_traceback = True
            error_start_line = i
            current_error.append(line)
            current_context.append(line)
            print(f"[DEBUG] 检测到堆栈跟踪（{'Traceback' if 'Traceback' in line else 'File 开头'}），起始行: {error_start_line}")
            continue

        # 处理堆栈跟踪内容
        if in_traceback:
            current_error.append(line)
            current_context.append(line)
            # 检查是否到达堆栈跟踪的末尾（以具体的错误类型开头，如 ValueError: 或 Error:）
            if line.strip() and not line.startswith("  File") and (line.strip().startswith("ValueError:") or line.strip().startswith("Error:") or line.strip().startswith("Exception:")):
                # 优先匹配 error_patterns 中的模式
                error_message = "\n".join(current_error)
                for pattern_info in error_patterns:
                    pattern = pattern_info["pattern"]
                    if re.search(pattern, error_message, re.IGNORECASE):
                        errors.append(error_message)
                        context = extract_context(log_content, line)
                        error_contexts.append({
                            "error_line": error_message,
                            "context": context,
                            "step": current_step,
                            "line_number": error_start_line,
                            "type": "error"
                        })
                        print(f"[DEBUG] 匹配 error_patterns 提取堆栈错误: {error_message}")
                        print(f"[DEBUG] 错误上下文: {context}")
                        specific_error_found = True
                        break
                # 如果未匹配到 error_patterns，则使用 specific_error_patterns
                if not specific_error_found:
                    specific_error_patterns = [
                        r"ValueError: read of closed file",  # 优先匹配具体错误
                        r"ValueError:.*",
                        r"Exception:.*",
                        r"FileNotFoundError:.*",
                        r"ModuleNotFoundError:.*",
                        r"TimeoutError:.*",
                        r"Connection refused",
                        r"TypeError:.*",
                        r"ImportError:.*"
                    ]
                    for pattern in specific_error_patterns:
                        if re.search(pattern, error_message, re.IGNORECASE):
                            errors.append(error_message)
                            context = extract_context(log_content, line)
                            error_contexts.append({
                                "error_line": error_message,
                                "context": context,
                                "step": current_step,
                                "line_number": error_start_line,
                                "type": "error"
                            })
                            print(f"[DEBUG] 提取具体堆栈错误: {error_message}")
                            print(f"[DEBUG] 错误上下文: {context}")
                            # 动态添加 ValueError: read of closed file 到 new_error_patterns
                            if "valueerror: read of closed file" in error_message.lower():
                                new_pattern = r"ValueError: read of closed file"
                                if new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                                    new_error_patterns.append(new_pattern)
                                    print(f"[DEBUG] 动态添加错误模式: {new_pattern}")
                                    config['new_error_patterns'] = new_error_patterns
                            specific_error_found = True
                            break
                in_traceback = False
                current_error = []
                current_context = []
            continue

        # 如果未找到堆栈跟踪，检查是否存在任何 ValueError（即使没有 Traceback）
        if not specific_error_found and "valueerror" in line.lower():
            errors.append(line.strip())
            context = extract_context(log_content, line)
            error_contexts.append({
                "error_line": line.strip(),
                "context": context,
                "step": current_step,
                "line_number": i,
                "type": "error"
            })
            print(f"[DEBUG] 检测到 ValueError 行 {i}: {line}")
            print(f"[DEBUG] 错误上下文: {context}")
            # 动态添加 ValueError: read of closed file 到 new_error_patterns
            if "valueerror: read of closed file" in line.lower():
                new_pattern = r"ValueError: read of closed file"
                if new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                    new_error_patterns.append(new_pattern)
                    print(f"[DEBUG] 动态添加错误模式: {new_pattern}")
                    config['new_error_patterns'] = new_error_patterns
            specific_error_found = True
            continue

        # 提取所有错误相关信息（ERROR、WARNING、exit、failed）
        error_detected = False
        # 优先匹配 error_patterns 中的模式
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(line.strip())
                context = extract_context(log_content, line)
                error_contexts.append({
                    "error_line": line.strip(),
                    "context": context,
                    "step": current_step,
                    "line_number": i,
                    "type": "error"
                })
                print(f"[DEBUG] 匹配 error_patterns 检测到错误行 {i}: {line}")
                print(f"[DEBUG] 错误上下文: {context}")
                specific_error_found = True
                error_detected = True
                break

        # 如果未匹配到 error_patterns，则使用 specific_error_patterns
        if not error_detected:
            specific_error_patterns = [
                r"ValueError: read of closed file",  # 优先匹配具体错误
                r"ValueError:.*",
                r"Exception:.*",
                r"FileNotFoundError:.*",
                r"ModuleNotFoundError:.*",
                r"TimeoutError:.*",
                r"Connection refused",
                r"TypeError:.*",
                r"ImportError:.*",
                r"ERROR:|CRITICAL:|Failed to CreateArtifact|Conflict:",
                r"ERROR|FAILED|CRITICAL|Exception"
            ]
            for pattern in specific_error_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    errors.append(line.strip())
                    context = extract_context(log_content, line)
                    error_contexts.append({
                        "error_line": line.strip(),
                        "context": context,
                        "step": current_step,
                        "line_number": i,
                        "type": "error"
                    })
                    print(f"[DEBUG] 检测到具体错误行 {i}: {line}")
                    print(f"[DEBUG] 错误上下文: {context}")
                    # 动态添加 ValueError: read of closed file 到 new_error_patterns
                    if "valueerror: read of closed file" in line.lower():
                        new_pattern = r"ValueError: read of closed file"
                        if new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                            new_error_patterns.append(new_pattern)
                            print(f"[DEBUG] 动态添加错误模式: {new_pattern}")
                            config['new_error_patterns'] = new_error_patterns
                    specific_error_found = True
                    error_detected = True
                    break

        # 提取 WARNING 信息
        warning_match = re.search(r"(WARNING:|Warning:)\s*(.+)", line, re.IGNORECASE)
        if warning_match:
            warnings.append(line.strip())
            context = extract_context(log_content, line)
            error_contexts.append({
                "error_line": line.strip(),
                "context": context,
                "step": current_step,
                "line_number": i,
                "type": "warning"
            })
            print(f"[DEBUG] 检测到警告行 {i}: {line}")
            print(f"[DEBUG] 警告上下文: {context}")

        # 提取退出代码（放在最后，避免覆盖具体错误）
        exit_code_match = re.search(r"##\[error\]Process completed with exit code (\d+)", line)
        if exit_code_match:
            exit_codes.append(int(exit_code_match.group(1)))
            context = extract_context(log_content, line)
            error_contexts.append({
                "error_line": line.strip(),
                "context": context,
                "step": current_step,
                "line_number": i,
                "type": "exit_code"
            })
            print(f"[DEBUG] 检测到退出代码: {exit_codes[-1]}")
            print(f"[DEBUG] 退出代码上下文: {context}")
            # 仅在未找到具体错误时记录退出码相关错误
            if not specific_error_found:
                errors.append(f"Process failed with exit code {exit_codes[-1]}")
                error_contexts.append({
                    "error_line": f"Process failed with exit code {exit_codes[-1]}",
                    "context": context,
                    "step": current_step,
                    "line_number": i,
                    "type": "exit_code"
                })
                print(f"[DEBUG] 未找到具体错误，记录退出码错误: Process failed with exit code {exit_codes[-1]}")

        # 提取成功步骤
        if current_step and not re.search(r"error|failed|exception", line, re.IGNORECASE):
            if current_step not in successful_steps_list:
                successful_steps_list.append(current_step)
                print(f"[DEBUG] 检测到成功步骤: {current_step}")

        # 如果未匹配到具体错误，最后检查 "Failed to generate APK"（仅在未找到其他错误时）
        if not specific_error_found and "failed to generate apk" in line.lower():
            context_lines = 10  # 扩展上下文行数
            start_index = max(0, i - context_lines)
            end_index = min(len(log_lines), i + context_lines + 1)
            context = "\n".join(log_lines[start_index:end_index])
            # 在整个日志中查找具体错误（如 ValueError）
            specific_error = None
            for j in range(len(log_lines)):
                for pattern_info in error_patterns:
                    pattern = pattern_info["pattern"]
                    if re.search(pattern, log_lines[j], re.IGNORECASE):
                        specific_error = log_lines[j].strip()
                        errors.append(specific_error)
                        error_contexts.append({
                            "error_line": specific_error,
                            "context": extract_context(log_content, specific_error),
                            "step": current_step,
                            "line_number": j,
                            "type": "error"
                        })
                        print(f"[DEBUG] 在 'Failed to generate APK' 上下文中检测到具体错误: {specific_error}，行 {j}")
                        specific_error_found = True
                        break
                if specific_error_found:
                    break
            if not specific_error_found:
                # 二次扫描，查找任何堆栈跟踪
                traceback_found = False
                for j in range(len(log_lines)):
                    if "Traceback (most recent call last):" in log_lines[j] or (log_lines[j].strip().startswith("File ") and ".py" in log_lines[j]):
                        traceback_lines = []
                        k = j
                        while k < len(log_lines) and not log_lines[k].startswith("Exception:") and not log_lines[k].startswith("ValueError:") and not log_lines[k].startswith("Error:"):
                            traceback_lines.append(log_lines[k])
                            k += 1
                        if k < len(log_lines):
                            traceback_lines.append(log_lines[k])
                            error_message = "\n".join(traceback_lines)
                            errors.append(error_message)
                            error_contexts.append({
                                "error_line": error_message,
                                "context": extract_context(log_content, error_message),
                                "step": current_step,
                                "line_number": j,
                                "type": "error"
                            })
                            print(f"[DEBUG] 二次扫描检测到堆栈错误: {error_message}，行 {j}")
                            # 动态添加 ValueError: read of closed file 到 new_error_patterns
                            if "valueerror: read of closed file" in error_message.lower():
                                new_pattern = r"ValueError: read of closed file"
                                if new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                                    new_error_patterns.append(new_pattern)
                                    print(f"[DEBUG] 动态添加错误模式: {new_pattern}")
                                    config['new_error_patterns'] = new_error_patterns
                            specific_error_found = True
                            traceback_found = True
                            break
            if not specific_error_found:
                failed_messages.append(line.strip())
                error_contexts.append({
                    "error_line": line.strip(),
                    "context": context,
                    "step": current_step,
                    "line_number": i,
                    "type": "failed"
                })
                print(f"[DEBUG] 未找到具体错误，记录失败信息: {line}，行 {i}")

    # 合并成功步骤
    successful_steps.extend(successful_steps_list)
    print(f"[DEBUG] 成功的步骤: {successful_steps}")

    # 提取警告信息和上下文
    for i, line, step in warning_lines:
        context = extract_context(log_content, line)
        error_contexts.append({
            "error_line": line.strip(),
            "context": context,
            "step": step,
            "line_number": i,
            "type": "warning"
        })

    # 处理 annotations_error
    if annotations_error:
        errors.append(annotations_error)
        error_contexts.append({
            "error_line": annotations_error,
            "context": annotations_error,
            "step": None,
            "line_number": None,
            "type": "annotation_error"
        })
        print(f"[DEBUG] 处理 annotations_error: {annotations_error}")

    # 检测新错误模式并更新 config
    for line in log_lines:
        matched = False
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            if re.search(pattern, line, re.IGNORECASE):
                matched = True
                break
        if not matched:
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
            # 添加对 ValueError: read of closed file 的动态检测
            elif "valueerror: read of closed file" in line.lower():
                new_pattern = r"ValueError: read of closed file"
            if new_pattern and new_pattern not in [p["pattern"] for p in error_patterns] and new_pattern not in new_error_patterns:
                new_error_patterns.append(new_pattern)
                print(f"[DEBUG] 检测到新错误模式: {new_pattern}")
                config['new_error_patterns'] = new_error_patterns

    # 提取隐式错误（例如未生成 APK），仅在未找到其他错误时添加
    if not specific_error_found:  # 只有在未提取到具体错误时才执行 inverse_check
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            inverse_check = pattern_info.get("inverse_check", False)
            if inverse_check:
                matched = False
                for i, line in enumerate(log_lines):
                    if re.search(pattern, line, re.IGNORECASE):
                        matched = True
                        print(f"[DEBUG] 匹配到隐式错误模式: {pattern}")
                        break
                if not matched:
                    # 再次尝试提取具体错误，避免默认生成 "Failed to generate APK"
                    for j in range(len(log_lines)):
                        if "Traceback (most recent call last):" in log_lines[j] or (log_lines[j].strip().startswith("File ") and ".py" in log_lines[j]):
                            traceback_lines = []
                            k = j
                            while k < len(log_lines) and not log_lines[k].startswith("Exception:") and not log_lines[k].startswith("ValueError:") and not log_lines[k].startswith("Error:"):
                                traceback_lines.append(log_lines[k])
                                k += 1
                            if k < len(log_lines):
                                traceback_lines.append(log_lines[k])
                                error_message = "\n".join(traceback_lines)
                                errors.append(error_message)
                                error_contexts.append({
                                    "error_line": error_message,
                                    "context": extract_context(log_content, error_message),
                                    "step": None,
                                    "line_number": j,
                                    "type": "error"
                                })
                                print(f"[DEBUG] 在 inverse_check 中提取到堆栈错误: {error_message}，行 {j}")
                                specific_error_found = True
                                break
                    if not specific_error_found:
                        errors.append(f"Pattern not matched: {pattern}")
                        error_contexts.append({
                            "error_line": f"Pattern not matched: {pattern}",
                            "context": "No matching log entry found",
                            "step": None,
                            "line_number": -1,
                            "type": "inverse_error"
                        })
                        print(f"[DEBUG] 检测到隐式错误: Pattern not matched: {pattern}")

    # 打印提取的所有信息
    print(f"[DEBUG] 提取的错误信息: {errors}")
    print(f"[DEBUG] 提取的警告信息: {warnings}")
    print(f"[DEBUG] 提取的失败信息: {failed_messages}")
    print(f"[DEBUG] 提取的退出代码: {exit_codes}")
    print(f"[DEBUG] 错误上下文: {error_contexts}")

    # 如果没有提取到错误，检查是否存在未定义的错误模式
    if not errors:
        print("[DEBUG] 未从日志中提取到错误，检查是否存在未定义的错误模式")
        for line in log_lines:
            if "error" in line.lower() or "failed" in line.lower() or "exception" in line.lower():
                new_pattern = {"pattern": re.escape(line), "fix": []}
                if new_pattern not in new_error_patterns:
                    new_error_patterns.append(new_pattern)
                    print(f"[DEBUG] 检测到未定义错误模式: {new_pattern}")

    return errors, error_contexts, exit_codes, new_error_patterns, warnings, error_patterns

def extract_successful_steps(log_content, workflow_file):
    """从日志中提取成功执行的步骤"""
    successful_steps = []
    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)

        steps = workflow.get("jobs", {}).get("build", {}).get("steps", [])
        log_lines = log_content.splitlines() if log_content else []

        print(f"[DEBUG] 开始提取成功步骤，工作流步骤总数: {len(steps)}")
        for step in steps:
            step_name = step.get("name", step.get("uses", "unnamed"))
            if not step_name or step_name == "unnamed":
                print(f"[DEBUG] 跳过无名步骤: {step}")
                continue

            step_failed = False
            for line in log_lines:
                if step_name in line and ("ERROR" in line or "FAILED" in line or "failed" in line.lower()):
                    step_failed = True
                    print(f"[DEBUG] 步骤 {step_name} 失败，日志行: {line}")
                    break

            if not step_failed:
                successful_steps.append(step_name)

        print(f"[DEBUG] 提取的成功步骤: {successful_steps}")
        return successful_steps
    except Exception as e:
        print(f"[ERROR] 提取成功步骤失败: {e}")
        return []

def extract_error_details(log_content, annotations_error):
    """从日志中提取错误详情"""
    error_details = []
    if not log_content:
        print("[DEBUG] 日志内容为空，无法提取错误详情")
        return error_details

    log_lines = log_content.splitlines()
    for i, line in enumerate(log_lines):
        if "ERROR" in line or "FAILED" in line or "Traceback" in line:
            context_start = max(0, i - 5)
            context_end = min(len(log_lines), i + 5)
            context = log_lines[context_start:context_end]
            error_details.append({
                "line": i + 1,
                "error": line,
                "context": "\n".join(context)
            })
            print(f"[DEBUG] 提取错误详情，行 {i + 1}: {line}")

    if annotations_error:
        error_details.append({
            "line": -1,
            "error": annotations_error,
            "context": "Annotations Error"
        })
        print(f"[DEBUG] 添加 annotations_error 到错误详情: {annotations_error}")

    print(f"[DEBUG] 提取的错误详情: {error_details}")
    return error_details