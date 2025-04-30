import json
import os
from datetime import datetime

def load_fix_history(fix_history_file):
    """加载修复历史记录"""
    try:
        if os.path.exists(fix_history_file):
            with open(fix_history_file, "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"[ERROR] 加载修复历史失败: {e}")
        return []

def save_fix_history(history, fix_history_file):
    """保存修复历史记录"""
    try:
        with open(fix_history_file, "w") as f:
            json.dump(history, f, indent=2)
        print("[DEBUG] 修复历史已保存")
    except Exception as e:
        print(f"[ERROR] 保存修复历史失败: {e}")

def add_to_fix_history(error_message, fix_applied, commit_sha, success, fix_history_file):
    """添加新的修复记录到历史"""
    history = load_fix_history(fix_history_file)
    history.append({
        "error_message": error_message,
        "fix_applied": fix_applied,
        "commit_sha": commit_sha,
        "success": success,
        "timestamp": datetime.now().isoformat()
    })
    save_fix_history(history, fix_history_file)