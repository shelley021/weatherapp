import subprocess
import os
import requests

def get_current_commit_sha():
    """获取当前分支的最新提交 SHA"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 获取当前提交 SHA 失败: {e}")
        return None

def push_changes(commit_message, run_id, branch, config):
    """推送更改到 GitHub 仓库"""
    try:
        repo = config['REPO']
        pushed_files = config.get('pushed_files', {})
        push_counts = config.get('push_counts', {})

        pushed_files[commit_message] = pushed_files.get(commit_message, 0) + 1
        push_counts[run_id] = push_counts.get(run_id, 0) + 1
        config['pushed_files'] = pushed_files
        config['push_counts'] = push_counts

        if pushed_files[commit_message] >= 5 or (run_id and push_counts.get(run_id, 0) >= 3):
            print(f"[DEBUG] 提交 '{commit_message}' 或 run_id {run_id} 触发次数过多，跳过推送")
            return False

        print(f"[DEBUG] 执行 Git 推送: {commit_message}")
        subprocess.run(["git", "config", "--global", "user.email", "autodebug@example.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "AutoDebug"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        result = subprocess.run(["git", "commit", "-m", commit_message], capture_output=True, text=True, check=True)
        print(f"[DEBUG] Git 提交输出: {result.stdout} {result.stderr}")
        result = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True, check=True)
        print(f"[DEBUG] Git 推送输出: {result.stdout} {result.stderr}")
        print("[DEBUG] 更改已成功推送到远程仓库")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git 推送失败: {e}")
        print(f"[DEBUG] Git 错误输出: {e.stdout} {e.stderr}")
        return False