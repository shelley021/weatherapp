import subprocess
import os
import requests
import json
from datetime import datetime, timezone
import time
import yaml

def get_current_commit_sha():
    """获取当前分支的最新提交 SHA"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        commit_sha = result.stdout.strip()
        print(f"[DEBUG] 当前 commit SHA: {commit_sha}")
        return commit_sha
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 获取当前提交 SHA 失败: {e}")
        return None

def push_changes(commit_message, run_id, branch, config, max_retries=5):
    """推送更改到 GitHub 仓库，支持 HTTPS 和 SSH 协议并增强重试逻辑"""
    try:
        repo = config['REPO']
        pushed_files = config.get('pushed_files', {})
        push_counts = config.get('push_counts', {})
        workflow_file_path = config['WORKFLOW_FILE']
        push_history_file = config['PUSH_HISTORY_FILE']

        pushed_files[commit_message] = pushed_files.get(commit_message, 0) + 1
        push_counts[run_id] = push_counts.get(run_id, 0) + 1
        config['pushed_files'] = pushed_files
        config['push_counts'] = push_counts

        if pushed_files[commit_message] >= 5 or (run_id and push_counts.get(run_id, 0) >= 3):
            print(f"[DEBUG] 提交 '{commit_message}' 或 run_id {run_id} 触发次数过多，跳过推送")
            return False

        print(f"[DEBUG] 执行 Git 推送: {commit_message}")

        with open(workflow_file_path, "r") as f:
            before_content = yaml.safe_load(f)

        with open(workflow_file_path, "a") as f:
            f.write(f"\n# AutoDebug: Forced change at {datetime.now(timezone.utc).isoformat()}\n")
        print(f"[DEBUG] 已强制修改 {workflow_file_path} 以确保提交")

        subprocess.run(["git", "config", "--global", "user.email", "autodebug@example.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "AutoDebug"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        result = subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, text=True, check=True)
        print(f"[DEBUG] Git 提交输出: {result.stdout} {result.stderr}")

        # 尝试 HTTPS 协议推送
        repo_url = f"https://github.com/{repo}.git"
        print(f"[DEBUG] 使用 HTTPS 协议: {repo_url}")
        subprocess.run(["git", "remote", "set-url", "origin", repo_url], check=True)

        for attempt in range(max_retries):
            try:
                result = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True, check=True)
                print(f"[DEBUG] Git 推送输出: {result.stdout} {result.stderr}")
                break
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] HTTPS 推送失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                print(f"[DEBUG] Git 错误输出: {e.stdout} {e.stderr}")
                if attempt < max_retries - 1:
                    print(f"[DEBUG] 等待 30 秒后重试...")
                    time.sleep(30)
                    # 尝试切换到 SSH 协议
                    ssh_url = f"git@github.com:{repo}.git"
                    print(f"[DEBUG] 切换到 SSH 协议: {ssh_url}")
                    subprocess.run(["git", "remote", "set-url", "origin", ssh_url], check=True)
                else:
                    print("[ERROR] 推送失败，经过多次重试，继续执行后续逻辑...")
                    return True

        with open(workflow_file_path, "r") as f:
            after_content = yaml.safe_load(f)

        push_history = {}
        if os.path.exists(push_history_file):
            with open(push_history_file, "r") as f:
                push_history = json.load(f)
        if not isinstance(push_history, dict):
            push_history = {}
        push_history[commit_message] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": {
                "before": before_content,
                "after": after_content,
                "description": f"Pushed changes for run_id {run_id}" if run_id else "Initial trigger push"
            }
        }
        with open(push_history_file, "w") as f:
            json.dump(push_history, f, ensure_ascii=False, indent=2)
        print(f"[DEBUG] 推送历史已记录到 {push_history_file}")

        print("[DEBUG] 更改已成功推送到远程仓库")
        time.sleep(5)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git 推送失败: {e}")
        print(f"[DEBUG] Git 错误输出: {e.stdout} {e.stderr}")
        return True