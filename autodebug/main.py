import time
import os
from .config import load_config
from .history import load_fix_history, add_to_fix_history
from .workflow_validator import validate_workflow_file, clean_workflow, ensure_on_field
from .log_retriever import get_actions_logs
from .log_parser import parse_log_content
from .error_patterns import load_error_patterns, update_error_patterns
from .fix_applier import analyze_and_fix
from .git_utils import get_current_commit_sha, push_changes

def main():
    """主执行逻辑，协调调试和修复流程"""
    # 获取主目录路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 加载配置，确保路径基于主目录
    config = load_config()
    config['WORKFLOW_FILE'] = os.path.join(project_root, '.github', 'workflows', 'debug.yml')
    config['FIX_HISTORY_FILE'] = os.path.join(project_root, 'fix_history.json')
    config['BACKUP_DIR'] = os.path.join(project_root, 'backup')
    
    headers = {
        "Authorization": f"Bearer {config['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.v3+json"
    }
    max_iterations = 10
    iteration = 0
    error_patterns = load_error_patterns(os.path.join(project_root, 'error_patterns.json'))
    processed_run_ids = set()  # 记录已处理的运行 ID

    while iteration < max_iterations:
        iteration += 1
        print(f"\n[DEBUG] 开始第 {iteration} 次迭代")

        if not validate_workflow_file(config['WORKFLOW_FILE']):
            print("[DEBUG] 工作流文件验证失败，尝试清理和修复...")
            clean_workflow(config['WORKFLOW_FILE'], config['default_fixes_applied'])
            ensure_on_field(config['WORKFLOW_FILE'])
            push_changes(f"AutoDebug: Fix workflow file (iteration {iteration})", None, config['BRANCH'], config)
            time.sleep(60)
            continue

        last_commit_sha = get_current_commit_sha()
        log_content, state, conclusion, annotations_error, has_critical_error, successful_steps, error_details, run_timestamp, annotations = get_actions_logs(
            config['REPO'], config['BRANCH'], config['BACKUP_DIR'], iteration, headers, config['WORKFLOW_FILE'], 
            last_commit_sha, lambda msg, rid, br: push_changes(msg, rid, br, config), processed_run_ids
        )

        if not log_content and not annotations_error:
            print("[DEBUG] 未获取到日志或错误，继续下一轮迭代...")
            time.sleep(30)
            continue

        errors, error_contexts, exit_codes, new_error_patterns = parse_log_content(
            log_content, config['WORKFLOW_FILE'], annotations_error, error_details, successful_steps, config
        )
        if new_error_patterns:
            update_error_patterns(new_error_patterns, os.path.join(project_root, 'error_patterns.json'))
            error_patterns = load_error_patterns(os.path.join(project_root, 'error_patterns.json'))

        if not errors and not has_critical_error and conclusion == "success":
            print("[DEBUG] 工作流运行成功，无需进一步修复")
            break

        fixed = analyze_and_fix(
            log_content, errors, error_contexts, exit_codes, annotations_error, error_details, successful_steps, config,
            config['WORKFLOW_FILE'], iteration, lambda msg, rid, br: push_changes(msg, rid, br, config), headers, error_patterns
        )

        history = load_fix_history(config['FIX_HISTORY_FILE'])
        for error_message in errors:
            add_to_fix_history(
                error_message, "Applied fix" if fixed else "No fix applied", last_commit_sha, fixed, config['FIX_HISTORY_FILE']
            )

        if fixed:
            print("[DEBUG] 修复已应用，等待下一轮日志...")
            time.sleep(60)
        else:
            print("[DEBUG] 未找到有效修复，继续下一轮迭代...")
            time.sleep(30)

    if iteration >= max_iterations:
        print("[ERROR] 达到最大迭代次数，停止调试")

if __name__ == "__main__":
    main()