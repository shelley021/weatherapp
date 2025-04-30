import yaml
import os
import re
import requests
from .error_patterns import load_error_patterns
from .workflow_validator import clean_workflow, ensure_on_field
from .history import is_section_protected

def analyze_and_fix(log_content, errors, error_contexts, exit_codes, annotations_error, error_details, successful_steps, config, workflow_file, iteration, push_changes_func, headers, error_patterns):
    """分析日志并应用修复"""
    fixed = False
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fix_history_file = config['FIX_HISTORY_FILE']

    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)
    except Exception as e:
        print(f"[ERROR] 无法加载工作流文件: {e}")
        return False

    for error, context in zip(errors, error_contexts):
        print(f"[DEBUG] 分析错误: {error}")
        print(f"[DEBUG] 错误上下文: {context}")

        for pattern in error_patterns:
            if re.search(pattern["pattern"], error, re.IGNORECASE):
                fix = pattern.get("fix")
                if not fix or not fix.get("step_code"):
                    print(f"[DEBUG] 未找到针对错误 '{error}' 的修复方法")
                    continue

                step_name = fix["step_name"]
                step_code = fix["step_code"]

                # 检查是否为受保护的部分
                if is_section_protected(step_name, fix_history_file):
                    print(f"[DEBUG] 步骤 '{step_name}' 是受保护的部分，跳过修改")
                    continue

                print(f"[DEBUG] 针对错误 '{error}' 应用修复: {step_name}")
                try:
                    new_step = yaml.safe_load(step_code)
                    jobs = workflow.get("jobs", {})
                    build_job = jobs.get("build", {})
                    steps = build_job.get("steps", [])

                    step_exists = False
                    for i, step in enumerate(steps):
                        if step.get("name") == step_name:
                            steps[i] = new_step
                            step_exists = True
                            break

                    if not step_exists:
                        steps.append(new_step)

                    build_job["steps"] = steps
                    jobs["build"] = build_job
                    workflow["jobs"] = jobs

                    with open(workflow_file, "w") as f:
                        yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)

                    print(f"[DEBUG] 工作流文件已更新: {workflow_file}")
                    push_changes_func(f"AutoDebug: Apply fix for '{error}' (iteration {iteration})", None, config['BRANCH'], config)
                    fixed = True
                    break
                except Exception as e:
                    print(f"[ERROR] 应用修复失败: {e}")
                    continue

        if annotations_error and "Invalid workflow file" in annotations_error:
            print("[DEBUG] 检测到无效工作流文件，尝试清理和修复...")
            if not is_section_protected("workflow_structure", fix_history_file):
                clean_workflow(workflow_file, config['default_fixes_applied'])
                push_changes_func(f"AutoDebug: Clean workflow file (iteration {iteration})", None, config['BRANCH'], config)
                fixed = True
            else:
                print("[DEBUG] 工作流结构是受保护的部分，跳过清理")

        if error_details.get("invalid_value"):
            print("[DEBUG] 检测到意外值，尝试修复...")
            if not is_section_protected("on_field", fix_history_file):
                ensure_on_field(workflow_file)
                push_changes_func(f"AutoDebug: Fix on field (iteration {iteration})", None, config['BRANCH'], config)
                fixed = True
            else:
                print("[DEBUG] on 字段是受保护的部分，跳过修复")

    return fixed