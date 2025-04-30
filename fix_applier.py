import re
import yaml
import os
from autodebug.history import add_to_fix_history, is_section_protected

def apply_fix(workflow_file, step_name, step_code, error_message, push_changes_func, iteration, branch, history_file):
    """应用修复到工作流文件"""
    try:
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

        # 检查是否已存在相同的步骤
        for step in steps:
            if step.get("name") == step_name:
                print(f"[DEBUG] 步骤 '{step_name}' 已存在，跳过修复")
                return False

        # 解析 step_code 为 YAML 格式
        step_yaml = yaml.safe_load(step_code)
        if isinstance(step_yaml, list):
            steps.extend(step_yaml)
        else:
            steps.append(step_yaml)

        build_job["steps"] = steps
        jobs["build"] = build_job
        workflow["jobs"] = jobs

        # 保存修改后的工作流文件
        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)

        print(f"[DEBUG] 已将修复步骤 '{step_name}' 添加到工作流文件")
        push_changes_func(f"AutoDebug: Apply fix '{step_name}' (iteration {iteration})", None, branch)

        # 记录修复历史
        add_to_fix_history(error_message, step_name, None, False, history_file, modified_section=step_name)
        return True

    except Exception as e:
        print(f"[ERROR] 应用修复失败: {e}")
        return False

def fix_workflow(workflow_file, errors, error_patterns, push_changes_func, iteration, branch, history_file):
    """尝试修复工作流中的错误"""
    try:
        # 清理错误信息中的时间戳
        cleaned_errors = []
        for error in errors:
            # 移除时间戳（格式如 2025-04-30T06:24:08.4264786Z）
            cleaned_error = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", error)
            cleaned_errors.append(cleaned_error)
            print(f"[DEBUG] 清理后的错误信息: {cleaned_error}")

        # 遍历错误模式，寻找匹配的修复
        for pattern_info in error_patterns:
            pattern = pattern_info["pattern"]
            for error in cleaned_errors:
                if re.search(pattern, error, re.IGNORECASE):
                    print(f"[DEBUG] 错误 '{error}' 匹配模式 '{pattern}'")
                    fix = pattern_info.get("fix")
                    if fix:
                        step_name = fix.get("step_name")
                        step_code = fix.get("step_code")
                        if step_code:
                            print(f"[DEBUG] 找到匹配的修复: {step_name}")
                            # 检查是否受保护
                            if is_section_protected(step_name, history_file):
                                print(f"[DEBUG] 步骤 '{step_name}' 受保护，跳过修复")
                                continue
                            return apply_fix(workflow_file, step_name, step_code, error, push_changes_func, iteration, branch, history_file)
                    print(f"[DEBUG] 未找到修复方案: {error}")
                    return False

        print("[DEBUG] 未找到匹配的错误模式")
        return False

    except Exception as e:
        print(f"[ERROR] 修复工作流失败: {e}")
        return False

def analyze_and_fix(workflow_file, errors, error_patterns, push_changes_func, iteration, branch, history_file):
    """分析日志并应用修复（包装 fix_workflow）"""
    print("[DEBUG] 开始分析并修复...")
    return fix_workflow(workflow_file, errors, error_patterns, push_changes_func, iteration, branch, history_file)