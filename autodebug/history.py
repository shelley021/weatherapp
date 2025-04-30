import json
import os
from datetime import datetime

def load_fix_history(history_file):
    """加载修复历史"""
    if not os.path.exists(history_file):
        return {"history": [], "protected_sections": {}}
    try:
        with open(history_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 加载修复历史失败: {e}")
        return {"history": [], "protected_sections": {}}

def add_to_fix_history(error_message, fix_applied, commit_sha, success, history_file, modified_section=None):
    """添加修复历史记录，并记录修改位置和成功状态"""
    history_data = load_fix_history(history_file)
    history = history_data.get("history", [])
    protected_sections = history_data.get("protected_sections", {})

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "error_message": error_message,
        "fix_applied": fix_applied,
        "commit_sha": commit_sha,
        "success": success,
        "modified_section": modified_section  # 记录修改的具体位置
    }
    history.append(entry)

    # 如果修复成功，将修改的部分标记为受保护
    if success and modified_section:
        protected_sections[modified_section] = {
            "commit_sha": commit_sha,
            "fix_applied": fix_applied,
            "timestamp": datetime.utcnow().isoformat()
        }

    history_data = {"history": history, "protected_sections": protected_sections}
    try:
        with open(history_file, 'w') as f:
            json.dump(history_data, f, indent=2)
        print(f"[DEBUG] 修复历史已更新: {history_file}")
    except Exception as e:
        print(f"[ERROR] 保存修复历史失败: {e}")

def is_section_protected(section, history_file):
    """检查某个部分是否受保护"""
    history_data = load_fix_history(history_file)
    protected_sections = history_data.get("protected_sections", {})
    return section in protected_sections