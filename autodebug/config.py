import os
from dotenv import load_dotenv

def load_config():
    """加载环境变量并初始化全局配置"""
    # 获取主目录路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_path = os.path.join(project_root, '.env')
    load_dotenv(dotenv_path=dotenv_path)

    # 调试环境变量加载状态
    print(f"[DEBUG] GITHUB_TOKEN 加载状态: {'成功' if os.getenv('GITHUB_TOKEN') else '失败'}")
    print(f"[DEBUG] DEEPSEEK_API_KEY 加载状态: {'成功' if os.getenv('DEEPSEEK_API_KEY') else '失败'}")

    # 获取环境变量
    config = {
        'DEEPSEEK_API_KEY': os.getenv("DEEPSEEK_API_KEY"),
        'GITHUB_TOKEN': os.getenv("GITHUB_TOKEN"),
        'REPO': "shelley021/weatherapp",
        'BRANCH': "main",
        'FIX_HISTORY_FILE': os.path.join(project_root, "fix_history.json"),
        'WORKFLOW_FILE': os.path.join(project_root, ".github", "workflows", "debug.yml"),
        'BACKUP_DIR': os.path.join(project_root, "backup")
    }

    # 初始化全局状态
    config['fixed_errors'] = set()
    config['default_fixes_applied'] = set()
    config['push_counts'] = {}
    config['pushed_files'] = {}
    config['run_id_counts'] = {}
    config['runs_on_fix_attempts'] = 0
    config['new_error_patterns'] = []

    return config