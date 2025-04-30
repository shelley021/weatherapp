import os
import re
import time
import requests
import yaml
import shutil
import subprocess
import zipfile
from io import BytesIO
from datetime import datetime, timedelta

def get_actions_logs(repo, branch, backup_dir, iteration, headers, workflow_file, last_commit_sha=None, push_changes_func=None, processed_run_ids=None):
    """获取 GitHub Actions 日志"""
    # 获取主目录路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 验证环境变量
    if repo == "owner/repo":
        print("[ERROR] GITHUB_REPOSITORY 未正确设置，默认值为 'owner/repo'，请设置正确的仓库名称")
        return "", None, None, "Invalid repository configuration", False, [], {}, None, []

    if branch == "main":
        print("[WARNING] GITHUB_BRANCH 未明确设置，使用默认值 'main'，请确认分支名称是否正确")

    # 确保工作流文件存在并已推送到远程仓库
    if not os.path.exists(workflow_file):
        print("[ERROR] debug.yml 文件不存在，初始化并推送默认工作流")
        default_workflow = {
            "name": "WeatherApp CI",
            "on": {"push": {"branches": ["main"]}},
            "jobs": {
                "build": {
                    "runs-on": "Ubuntu-latest",
                    "steps": [{"uses": "actions/checkout@v4"}]
                }
            }
        }
        os.makedirs(os.path.join(project_root, ".github", "workflows"), exist_ok=True)
        with open(workflow_file, "w") as f:
            yaml.dump(default_workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        push_changes_func(f"AutoDebug: Initialize debug.yml (iteration {iteration})", None, branch)

    # 检查远程仓库是否存在工作流文件
    workflow_check_url = f"https://api.github.com/repos/{repo}/contents/{workflow_file.replace(project_root + '/', '')}?ref={branch}"
    max_check_retries = 3
    for attempt in range(max_check_retries):
        try:
            response = requests.get(workflow_check_url, headers=headers, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] 远程仓库中未找到 debug.yml 文件: {response.status_code} {response.text}")
                print("[DEBUG] 尝试强制推送 debug.yml 文件")
                push_changes_func(f"AutoDebug: Force push debug.yml (iteration {iteration})", None, branch)
                time.sleep(60)
            else:
                print("[DEBUG] 远程仓库中已找到 debug.yml 文件")
                break
        except Exception as e:
            print(f"[ERROR] 检查远程工作流文件时发生错误: {e}")
            return "", None, None, "Failed to verify workflow file", False, [], {}, None, []
        if attempt == max_check_retries - 1:
            print("[ERROR] 多次尝试后仍未找到 debug.yml 文件，停止重试")
            return "", None, None, "Failed to verify workflow file", False, [], {}, None, []

    workflow_runs_url = f"https://api.github.com/repos/{repo}/actions/workflows/debug.yml/runs"
    current_time_utc = datetime.utcnow()
    created_after = (current_time_utc - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "branch": branch,
        "per_page": 10,
        "created": f">{created_after}"
    }

    print(f"[DEBUG] 当前真实UTC时间: {current_time_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"[DEBUG] 查询时间范围: >{created_after}")
    print(f"[DEBUG] 查询分支: {branch}")
    print(f"[DEBUG] API 请求 URL: {workflow_runs_url}")
    print(f"[DEBUG] 请求参数: {params}")

    max_retries = 3
    max_outer_wait_time = 1800
    outer_wait_interval = 30
    elapsed_outer_time = 0
    error_count = 0

    print(f"[DEBUG] 当前 processed_run_ids: {processed_run_ids}")
    for retry in range(max_retries):
        try:
            response = requests.get(
                workflow_runs_url,
                headers=headers,
                params=params,
                timeout=30
            )
            if response.status_code != 200:
                print(f"GitHub API请求失败: {response.status_code} {response.text}")
                if response.status_code == 404:
                    error_count += 1
                    if error_count >= max_retries:
                        print("[ERROR] 连续 404 错误，可能工作流文件未找到或仓库配置错误，停止重试")
                        print("[DEBUG] 再次尝试强制推送 debug.yml 文件")
                        push_changes_func(f"AutoDebug: Retry push debug.yml due to 404 (iteration {iteration})", None, branch)
                        time.sleep(60)
                        return "", None, None, "Workflow file not found (404)", False, [], {}, None, []
                time.sleep(1)
                continue

            error_count = 0
            debug_runs = response.json().get("workflow_runs", [])
            print(f"[DEBUG] 找到 {len(debug_runs)} 个工作流运行")
            if not debug_runs:
                print("未找到过去 30 天内的运行日志，触发强制推送...")
                push_changes_func(f"AutoDebug: Trigger new run (iteration {iteration})", None, branch)
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return "", None, None, None, False, [], {}, None, []

            run = debug_runs[0]
            run_id = run["id"]
            state = run["status"]
            conclusion = run["conclusion"]
            run_commit_sha = run.get("head_sha")
            run_timestamp = run.get("created_at")

            if last_commit_sha and run_commit_sha != last_commit_sha:
                print(f"[DEBUG] 运行 {run_id} 的 commit SHA ({run_commit_sha}) 不匹配目标 commit SHA ({last_commit_sha})，等待匹配的运行...")
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                continue

            run_id_counts = {}  # 临时存储运行计数
            run_id_counts[run_id] = run_id_counts.get(run_id, 0) + 1
            if run_id_counts[run_id] >= 3:
                print(f"[DEBUG] run_id {run_id} 重复 3 次，触发强制推送")
                push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return "", None, None, None, False, [], {}, None, []

            if run_id in processed_run_ids:
                print(f"运行 {run_id} 已处理过，触发强制推送...")
                push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return "", None, None, None, False, [], {}, None, []

            print(f"正在检查运行 {run_id} (状态: {state}, 结果: {conclusion}, commit SHA: {run_commit_sha}, 时间戳: {run_timestamp})")
            processed_run_ids.add(run_id)

            if state != "completed":
                print(f"检测到未完成的运行 {run_id}，等待其完成...")
                max_wait_time = 1200
                wait_interval_inner = 30
                elapsed_time = 0

                while elapsed_time < max_wait_time:
                    run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
                    run_response = requests.get(run_url, headers=headers, timeout=30)
                    if run_response.status_code != 200:
                        print(f"获取运行 {run_id} 详情失败: {run_response.status_code}")
                        time.sleep(wait_interval_inner)
                        elapsed_time += wait_interval_inner
                        continue

                    run_data = run_response.json()
                    state = run_data.get("status")
                    conclusion = run_data.get("conclusion")
                    print(f"运行 {run_id} 当前状态: {state}, 结果: {conclusion}")

                    if state == "completed":
                        break

                    time.sleep(wait_interval_inner)
                    elapsed_time += wait_interval_inner

                if state != "completed":
                    print(f"运行 {run_id} 在 {max_wait_time} 秒内未完成，继续等待下一轮检查...")
                    time.sleep(outer_wait_interval)
                    elapsed_outer_time += outer_wait_interval
                    continue

            run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
            for attempt in range(max_retries):
                run_response = requests.get(run_url, headers=headers, timeout=30)
                if run_response.status_code == 200:
                    break
                print(f"获取运行 {run_id} 详情失败: {run_response.status_code} (尝试 {attempt+1}/{max_retries})")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"获取运行 {run_id} 详情失败，触发强制推送...")
                push_changes_func(f"AutoDebug: Failed to fetch run {run_id}", run_id, branch)
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return "", None, None, None, False, [], {}, None, []

            run_data = run_response.json()
            error_message = run_data.get("message", "")
            print(f"[DEBUG] 运行 {run_id} 元数据错误信息: {error_message}")

            jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
            annotations_error = ""
            error_details = {}
            successful_steps = []
            annotations = []

            for attempt in range(max_retries):
                jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
                if jobs_response.status_code == 200:
                    break
                print(f"获取运行 {run_id} 的 Jobs 信息失败: {jobs_response.status_code} (尝试 {attempt+1}/{max_retries})")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"获取运行 {run_id} 的 Jobs 信息失败，跳过 Annotations 获取...")
                annotations_error = "Invalid workflow file"

            if jobs_response.status_code == 200:
                jobs_data = jobs_response.json()
                jobs = jobs_data.get("jobs", [])
                if not jobs:
                    print(f"运行 {run_id} 未找到 Jobs 信息，使用默认错误信息...")
                    annotations_error = "Invalid workflow file"
                else:
                    for job in jobs:
                        annotations_url = job.get("annotations_url")
                        if annotations_url:
                            for attempt in range(max_retries):
                                annotations_response = requests.get(annotations_url, headers=headers, timeout=30)
                                if annotations_response.status_code == 200:
                                    break
                                print(f"获取运行 {run_id} 的 Annotations 失败: {annotations_response.status_code} (尝试 {attempt+1}/{max_retries})")
                                time.sleep(5 * (attempt + 1))
                            else:
                                print(f"获取运行 {run_id} 的 Annotations 失败，使用默认错误信息...")
                                annotations_error = "Invalid workflow file"
                                continue

                            job_annotations = annotations_response.json()
                            annotations.extend(job_annotations)
                            print(f"[DEBUG] 运行 {run_id} 的完整 Annotations 数据: {json.dumps(job_annotations, indent=2)}")
                            for annotation in job_annotations:
                                message = annotation.get("message", "")
                                print(f"[DEBUG] 运行 {run_id} Annotations 信息: {message}")
                                if annotation.get("annotation_level") in ["failure", "error"]:
                                    annotations_error += message + "\n"
                                    line_match = re.search(r"Line: (\d+)", message)
                                    value_match = re.search(r"Unexpected value '(\w+)'", message, re.IGNORECASE)
                                    error_details["line"] = int(line_match.group(1)) if line_match else None
                                    error_details["invalid_value"] = value_match.group(1) if value_match else None
                                    print(f"[DEBUG] 提取的错误详情: {error_details}")

            if conclusion == "startup_failure" and annotations_error:
                if not annotations_error:
                    annotations_error = "Invalid workflow file"
                print(f"[DEBUG] 最终 Annotations 错误: {annotations_error}")
                print(f"运行 {run_id} 失败（startup_failure），尝试修复...")
                return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

            logs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
            logs_response = requests.get(logs_url, headers=headers, timeout=30)

            if logs_response.status_code == 404:
                print(f"运行 {run_id} 的日志尚未生成，继续等待...")
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                continue

            if logs_response.status_code != 200:
                print(f"获取运行 {run_id} 的日志失败: {logs_response.status_code}")
                print(f"运行 {run_id} 失败（无法获取日志），触发强制推送...")
                push_changes_func(f"AutoDebug: Log fetch failed (run_id {run_id})", run_id, branch)
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return "", None, None, None, False, [], {}, None, []

            try:
                with zipfile.ZipFile(BytesIO(logs_response.content)) as zip_file:
                    if not zip_file.namelist():
                        print(f"运行 {run_id} 的日志压缩包为空")
                        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

                    log_filename = next((n for n in zip_file.namelist() if n.endswith('.txt')), None)
                    if not log_filename:
                        print(f"运行 {run_id} 的日志格式异常")
                        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

                    print(f"成功获取运行 {run_id} 的日志")
                    with zip_file.open(log_filename) as log_file:
                        log_content = log_file.read().decode('utf-8', errors='ignore')
                        log_content = log_content.lstrip('\ufeff')

                    os.makedirs(os.path.join(project_root, "logs"), exist_ok=True)
                    with open(os.path.join(project_root, "logs", "full_log.txt"), "w", encoding="utf-8") as f:
                        f.write(log_content)
                    print("[DEBUG] 完整日志已保存到 logs/full_log.txt")

                    lines = log_content.splitlines()
                    current_step = None
                    for line in lines:
                        step_match = re.match(r"^\d+\s*Run\s+(.+?)$", line)
                        if step_match:
                            current_step = step_match.group(1).strip()
                        if current_step:
                            successful_steps.append(current_step)

                    print(f"[DEBUG] 成功的步骤: {successful_steps}")

                    with open(workflow_file, "r") as f:
                        workflow = yaml.safe_load(f)
                    runs_on = workflow.get("jobs", {}).get("build", {}).get("runs-on", "").lower()
                    if runs_on != "Ubuntu-latest".lower():
                        print("[DEBUG] debug.yml 中 runs-on 未正确设置为 ubuntu-latest，强制推送...")
                        workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
                        with open(workflow_file, "w") as f:
                            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
                        push_changes_func(f"AutoDebug: Force fix runs-on (iteration {iteration})", run_id, branch)
                        time.sleep(60)
                        elapsed_outer_time += 60
                        return "", None, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

                    print(f"[DEBUG] 日志内容（前500字符）: {log_content[:500]}...")
                    print(f"运行 {run_id} 状态（conclusion={conclusion}, has_critical_error=False)")
                    return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

            except Exception as e:
                print(f"处理运行 {run_id} 的日志时出错: {e}")
                return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

        except Exception as e:
            print(f"GitHub API请求异常: {e}")
            time.sleep(1)

    print(f"在 {max_outer_wait_time} 秒内未找到匹配的运行日志，触发强制推送...")
    push_changes_func(f"AutoDebug: No runs found (iteration {iteration})", None, branch)
    return "", None, None, None, False, [], {}, None, []