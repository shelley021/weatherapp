import yaml
import re
import requests
from .workflow_validator import clean_workflow, ensure_on_field, save_workflow

def apply_local_fix(workflow_file, error_message, error_patterns, default_fixes_applied, error_details):
    """应用本地修复到工作流文件"""
    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)

        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            fix = pattern_info["fix"]
            if re.search(pattern, error_message, re.IGNORECASE):
                if fix["step_code"] is None:
                    print(f"[DEBUG] 错误模式 {pattern} 无预定义修复，尝试动态修复...")
                    if pattern == r"Invalid workflow file":
                        clean_workflow(workflow_file, default_fixes_applied)
                        ensure_on_field(workflow_file)
                        return True
                    elif pattern == r"Unexpected value '(\w+)'":
                        invalid_value = error_details.get("invalid_value")
                        if invalid_value:
                            print(f"[DEBUG] 检测到无效值: {invalid_value}，尝试修复...")
                            steps = workflow.get("jobs", {}).get("build", {}).get("steps", [])
                            for step in steps:
                                for key, value in step.items():
                                    if value == invalid_value:
                                        step[key] = "corrected-value"
                            save_workflow(workflow, workflow_file)
                            return True
                    return False

                steps = workflow.get("jobs", {}).get("build", {}).get("steps", [])
                step_names = [step.get("name", "") for step in steps]
                if fix["step_name"] not in step_names:
                    print(f"[DEBUG] 应用修复: {fix['step_name']}")
                    steps.append(yaml.safe_load(fix["step_code"].strip()))
                    workflow["jobs"]["build"]["steps"] = steps
                    save_workflow(workflow, workflow_file)
                    return True
                else:
                    print(f"[DEBUG] 修复 {fix['step_name']} 已存在，跳过")
                    return False

        return False
    except Exception as e:
        print(f"[ERROR] 应用本地修复失败: {e}")
        return False

def analyze_and_fix(log_content, errors, error_contexts, exit_codes, annotations_error, error_details, successful_steps, config, workflow_file, iteration, push_changes_func, headers, error_patterns):
    """分析错误并应用修复"""
    try:
        fixed = False
        for error_message in errors:
            print(f"[DEBUG] 正在处理错误: {error_message}")
            if error_message in config['fixed_errors']:
                print(f"[DEBUG] 错误已修复过: {error_message}")
                continue

            local_fix_applied = apply_local_fix(workflow_file, error_message, error_patterns, config['default_fixes_applied'], error_details)
            if local_fix_applied:
                print(f"[DEBUG] 本地修复已应用于错误: {error_message}")
                config['fixed_errors'].add(error_message)
                push_changes_func(f"AutoDebug: Apply local fix for {error_message} (iteration {iteration})", None, config['BRANCH'])
                fixed = True
                continue

            print(f"[DEBUG] 无本地修复可用，尝试调用 DeepSeek API...")
            deepseek_headers = {
                "Authorization": f"Bearer {config['DEEPSEEK_API_KEY']}",
                "Content-Type": "application/json"
            }
            prompt = f"""
以下是 GitHub Actions 日志中的错误信息和上下文：
错误: {error_message}
上下文: {error_contexts[errors.index(error_message)]['context'] if errors.index(error_message) < len(error_contexts) else '无上下文'}
退出代码: {exit_codes if exit_codes else '无'}
成功步骤: {successful_steps}
请提供一个修复此错误的 GitHub Actions 工作流步骤（YAML 格式）。
"""
            payload = {
                "model": "deepseek-coder",
                "prompt": prompt,
                "max_tokens": 500,
                "temperature": 0.7
            }
            response = requests.post("https://api.deepseek.com/v1/completions", json=payload, headers=deepseek_headers, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] DeepSeek API 请求失败: {response.status_code} {response.text}")
                continue

            deepseek_response = response.json()
            fix_suggestion = deepseek_response.get("choices", [{}])[0].get("text", "").strip()
            if not fix_suggestion:
                print("[DEBUG] DeepSeek 未提供有效修复建议")
                continue

            try:
                fix_yaml = yaml.safe_load(fix_suggestion)
                if not isinstance(fix_yaml, dict) or "name" not in fix_yaml:
                    print("[DEBUG] DeepSeek 提供的修复格式无效")
                    continue

                with open(workflow_file, "r") as f:
                    workflow = yaml.safe_load(f)
                steps = workflow.get("jobs", {}).get("build", {}).get("steps", [])
                step_names = [step.get("name", "") for step in steps]
                if fix_yaml["name"] not in step_names:
                    print(f"[DEBUG] 应用 DeepSeek 修复: {fix_yaml['name']}")
                    steps.append(fix_yaml)
                    workflow["jobs"]["build"]["steps"] = steps
                    save_workflow(workflow, workflow_file)
                    config['fixed_errors'].add(error_message)
                    push_changes_func(f"AutoDebug: Apply DeepSeek fix for {error_message} (iteration {iteration})", None, config['BRANCH'])
                    fixed = True
                else:
                    print(f"[DEBUG] DeepSeek 修复 {fix_yaml['name']} 已存在，跳过")
            except Exception as e:
                print(f"[ERROR] 应用 DeepSeek 修复失败: {e}")

        return fixed
    except Exception as e:
        print(f"[ERROR] 分析和修复失败: {e}")
        return False