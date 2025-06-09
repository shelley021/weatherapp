import json
import os
from datetime import datetime

class FixHistory:
    def __init__(self, history_file):
        self.history_file = history_file
        self.load_history()

    def load_history(self):
        """加载历史记录文件"""
        if os.path.exists(self.history_file):
            with open(self.history_file, "r") as f:
                self.history = json.load(f)
        else:
            self.history = {
                "history": [],
                "verified_steps": {},  # 记录已验证正确的步骤
                "step_status": {},     # 记录每个步骤的执行状态
                "errors": {},          # 记录错误及其修复尝试
                "untried_errors": [],
                "incorrect_modifications": [],
                "successful_steps": [],
                "correct_steps": [],
                "deepseek_attempts": {}  # 新增：专门存储 DeepSeek 的尝试记录
            }
            self.save_history()

    def save_history(self):
        """保存历史记录文件"""
        with open(self.history_file, "w") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def add_to_fix_history(self, error_message, step_name, fix_result, success, modified_section=None, successful_steps=None):
        """添加修复记录"""
        entry = {
            "error_message": error_message,
            "step_name": step_name,
            "fix_result": fix_result,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "modified_section": modified_section
        }
        self.history["history"].append(entry)
        if successful_steps:
            self.history["successful_steps"] = list(set(self.history["successful_steps"] + successful_steps))
        self.save_history()

    def add_deepseek_attempt(self, error_message, fix_attempt, reason, success):
        """记录 DeepSeek 的修复尝试"""
        if error_message not in self.history["deepseek_attempts"]:
            self.history["deepseek_attempts"][error_message] = []
        self.history["deepseek_attempts"][error_message].append({
            "fix_attempt": fix_attempt,
            "reason": reason,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })
        self.save_history()

    def get_deepseek_attempts(self, error_message):
        """获取 DeepSeek 的修复尝试记录"""
        return self.history["deepseek_attempts"].get(error_message, [])

    def is_section_protected(self, section_name):
        """检查某个步骤是否被保护（已验证正确）"""
        return section_name in self.history["verified_steps"]

    def mark_step_verified(self, step_name):
        """标记某个步骤为已验证正确"""
        self.history["verified_steps"][step_name] = {
            "verified": True,
            "timestamp": datetime.now().isoformat()
        }
        self.save_history()

    def update_step_status(self, step_name, success):
        """更新步骤的执行状态"""
        self.history["step_status"][step_name] = {
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        if success:
            self.mark_step_verified(step_name)
        self.save_history()

    def get_step_status(self, step_name):
        """获取步骤的执行状态"""
        return self.history["step_status"].get(step_name, {}).get("success", None)

    def get_successful_steps(self):
        """获取所有成功执行的步骤"""
        return self.history["successful_steps"]

    def update_successful_steps(self, successful_steps):
        """更新成功执行的步骤列表"""
        self.history["successful_steps"] = list(set(self.history["successful_steps"] + successful_steps))
        self.save_history()

    def get_known_errors(self):
        """获取已知错误"""
        return list(self.history["errors"].keys())

    def add_known_error(self, error, fix_applied, success):
        """添加已知错误"""
        self.history["errors"][error] = {
            "fix_applied": fix_applied,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        self.save_history()

def load_processed_runs(processed_runs_file):
    """加载已处理的运行 ID，增强错误处理和调试日志"""
    if not os.path.exists(processed_runs_file):
        print(f"[DEBUG] processed_runs 文件不存在: {processed_runs_file}，初始化为空集合")
        return {}
    try:
        with open(processed_runs_file, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                print(f"[WARNING] processed_runs 文件格式无效: {processed_runs_file}，初始化为空字典")
                return {}
            processed_runs = data.get("processed_runs", [])
            print(f"[DEBUG] 从 {processed_runs_file} 加载了 {len(processed_runs)} 个已处理运行")
            return {str(run_id): {"processed": True, "success": False} for run_id in processed_runs}
    except Exception as e:
        print(f"[ERROR] 加载已处理的运行 ID 失败: {e}")
        return {}

def save_processed_runs(processed_runs, processed_runs_file):
    """保存已处理的运行 ID，增强错误处理和调试日志"""
    try:
        processed_run_ids = [run_id for run_id, info in processed_runs.items()]
        with open(processed_runs_file, "w") as f:
            json.dump({"processed_runs": processed_run_ids}, f, indent=2)
        print(f"[DEBUG] 已处理的运行 ID 已保存到: {processed_runs_file}，共 {len(processed_run_ids)} 个")
    except Exception as e:
        print(f"[ERROR] 保存已处理的运行 ID 失败: {e}")

def load_fix_history(history_file):
    """加载修复历史，增强错误处理和调试日志"""
    if not os.path.exists(history_file):
        print(f"[DEBUG] 修复历史文件不存在: {history_file}，初始化为空历史")
        return {
            "history": [],
            "protected_sections": [],
            "untried_errors": [],
            "successful_steps": [],
            "known_errors": [],
            "errors": {},
            "step_status": {},
            "deepseek_attempts": {}  # 新增字段
        }
    try:
        with open(history_file, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                print(f"[WARNING] 修复历史文件格式无效: {history_file}，初始化为空历史")
                return {
                    "history": [],
                    "protected_sections": [],
                    "untried_errors": [],
                    "successful_steps": [],
                    "known_errors": [],
                    "errors": {},
                    "step_status": {},
                    "deepseek_attempts": {}
                }
            if "history" not in data:
                data["history"] = []
            if "protected_sections" not in data:
                data["protected_sections"] = []
            if "untried_errors" not in data:
                data["untried_errors"] = []
            if "successful_steps" not in data:
                data["successful_steps"] = []
            if "known_errors" not in data:
                data["known_errors"] = []
            if "errors" not in data:
                data["errors"] = {}
            if "step_status" not in data:
                data["step_status"] = {}
            if "deepseek_attempts" not in data:
                data["deepseek_attempts"] = {}
            print(f"[DEBUG] 从 {history_file} 加载了 {len(data['history'])} 条修复历史")
            return data
    except Exception as e:
        print(f"[ERROR] 加载修复历史失败: {e}")
        return {
            "history": [],
            "protected_sections": [],
            "untried_errors": [],
            "successful_steps": [],
            "known_errors": [],
            "errors": {},
            "step_status": {},
            "deepseek_attempts": {}
        }

def save_fix_history(history, history_file):
    """保存修复历史，增强错误处理和调试日志"""
    try:
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
        print(f"[DEBUG] 修复历史已保存到: {history_file}，共 {len(history.get('history', []))} 条记录")
    except Exception as e:
        print(f"[ERROR] 保存修复历史失败: {e}")