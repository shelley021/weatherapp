import yaml
import re

def validate_workflow_file(workflow_file):
    """验证 GitHub Actions 工作流文件的结构和内容"""
    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)
        if not workflow:
            print("[ERROR] debug.yml 为空或无效")
            return False
        required_keys = ["name", "on", "jobs"]
        missing_keys = [key for key in required_keys if key not in workflow]
        if missing_keys:
            print(f"[ERROR] debug.yml 缺少必要字段: {missing_keys}")
            return False
        if not isinstance(workflow["jobs"], dict) or "build" not in workflow["jobs"]:
            print("[ERROR] debug.yml 的 jobs 字段无效或缺少 build 作业")
            return False
        if not workflow["jobs"]["build"].get("runs-on"):
            print("[ERROR] debug.yml 的 build 作业缺少 runs-on")
            return False
        steps = workflow["jobs"]["build"].get("steps", [])
        if not steps:
            print("[ERROR] debug.yml 的 steps 列表为空")
            return False
        valid_runners = ["Ubuntu-latest", "Ubuntu-22.04", "Ubuntu-20.04"]
        runs_on = workflow["jobs"]["build"].get("runs-on")
        if runs_on.lower() not in [r.lower() for r in valid_runners]:
            print(f"[WARNING] runs-on: {runs_on} 可能无效，建议使用 {valid_runners}")
        print("[DEBUG] debug.yml 结构验证通过")
        return True
    except Exception as e:
        print(f"[ERROR] 验证 debug.yml 失败: {e}")
        return False

def clean_workflow(workflow_file, default_fixes_applied):
    """清理工作流文件中的错误字段"""
    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)

        print(f"[DEBUG] clean_workflow 原始 workflow 内容: {workflow}")

        if True in workflow:
            print("⚠️ 检测到错误的 True 键（由 true: 解析而来），清理并替换为 'on'...")
            true_field = workflow.pop(True)
            if isinstance(true_field, list):
                new_on = {}
                for trigger in true_field:
                    new_on[trigger] = {}
                workflow['on'] = new_on
            else:
                workflow['on'] = {
                    "push": {"branches": ["main"]}
                }

        print(f"[DEBUG] clean_workflow 清理后的 workflow 内容: {workflow}")

        runs_on = workflow.get("jobs", {}).get("build", {}).get("runs-on", "").lower()
        if runs_on != "Ubuntu-latest".lower() and "fix_runs_on" not in default_fixes_applied:
            print("⚠️ runs-on 未设置为 ubuntu-latest，替换")
            workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
            default_fixes_applied.add("fix_runs_on")

        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        print("已清理 debug.yml 中的错误字段")
        return True
    except Exception as e:
        print(f"清理 debug.yml 失败: {e}")
        return False

def ensure_on_field(workflow_file):
    """确保工作流文件包含有效的 on 字段"""
    try:
        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)

        print(f"[DEBUG] ensure_on_field 原始 workflow 内容: {workflow}")

        if True in workflow:
            print("⚠️ 检测到错误的 True 键（由 true: 解析而来），清理并替换为 'on'...")
            true_field = workflow.pop(True)
            if isinstance(true_field, list):
                new_on = {}
                for trigger in true_field:
                    new_on[trigger] = {}
                workflow['on'] = new_on
            else:
                workflow['on'] = {
                    "push": {"branches": ["main"]}
                }

        standard_on = {
            "push": {"branches": ["main"]}
        }

        on_field = workflow.get('on', {})

        if isinstance(on_field, list):
            print("检测到 on 字段的简写格式，转换为标准格式...")
            new_on = {}
            for trigger in on_field:
                new_on[trigger] = {}
            on_field = new_on

        is_valid = (
            isinstance(on_field, dict) and
            any(key in on_field for key in ["push"]) and
            all(isinstance(on_field[key], dict) for key in on_field if key in ["push"])
        )

        if not is_valid:
            print("⚠️ debug.yml 缺少或包含无效的 on 字段，自动修复...")
            workflow['on'] = standard_on
        else:
            for trigger in on_field:
                if not isinstance(on_field[trigger], dict):
                    on_field[trigger] = {}
            workflow['on'] = on_field

        if workflow.get('on') is True:
            print("⚠️ on 字段是布尔值 True，替换为标准格式...")
            workflow['on'] = standard_on

        print(f"[DEBUG] ensure_on_field 修复后的 workflow 内容: {workflow}")

        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        print("已确保 on 字段符合标准")
        return True
    except Exception as e:
        print(f"检查 debug.yml 失败: {e}")
        return False

def save_workflow(workflow, workflow_file):
    """保存工作流文件"""
    try:
        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        print("[DEBUG] workflow 已保存到 debug.yml")
        return True
    except Exception as e:
        print(f"[ERROR] 保存 workflow 失败: {e}")
        return False