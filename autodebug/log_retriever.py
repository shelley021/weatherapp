import os
import re
import time
import requests
import yaml
import shutil
import subprocess
import zipfile
from io import BytesIO
from datetime import datetime, timezone, timedelta
import json

def get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=None, fallback_to_30_days=False):
    """获取 GitHub Actions 工作流运行记录，整合 og_retriever.py 的逻辑"""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/debug.yml/runs"
    if start_time and not fallback_to_30_days:
        created_filter = f">{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    else:
        current_time = datetime.now(timezone.utc)
        created_filter = f">{(current_time - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    params = {"branch": branch, "per_page": 1, "created": created_filter}
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
    print(f"[DEBUG] 当前真实UTC时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"[DEBUG] 查询时间范围: {created_filter}")
    print(f"[DEBUG] 查询分支: {branch}")
    print(f"[DEBUG] API 请求 URL: {url}")
    print(f"[DEBUG] 请求参数: {params}")

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        runs = response.json().get("workflow_runs", [])
        print(f"[DEBUG] 找到 {len(runs)} 个工作流运行，时间范围: {created_filter}")
        if runs:
            for run in runs:
                print(f"[DEBUG] 运行 ID: {run['id']}, 创建时间: {run['created_at']}, 状态: {run['status']}, 结果: {run['conclusion']}")

        if not runs:
            print("[DEBUG] 未找到工作流运行")
            return None, processed_run_ids

        runs.sort(key=lambda x: x["created_at"], reverse=True)
        for run in runs:
            run_id = str(run["id"])
            if run_id not in processed_run_ids or (run_id in processed_run_ids and not processed_run_ids[run_id].get("success", False)):
                return run, processed_run_ids

        print("[DEBUG] 所有运行均已处理且成功")
        return None, processed_run_ids
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] 获取工作流运行记录失败: {e}")
        return None, processed_run_ids

def get_job_logs(repo, github_token, run_id, job_id, max_retries=3):
    """获取指定 Job 的日志，整合 og_retriever.py 的逻辑"""
    url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_file_path = os.path.join(project_root, "logs", f"run_{run_id}_job_{job_id}.txt")

    # 检查本地日志缓存
    if os.path.exists(log_file_path):
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            print(f"[DEBUG] 从本地文件 {log_file_path} 读取历史日志，长度: {len(log_content)} 字符")
            return log_content
        except Exception as e:
            print(f"[DEBUG] 读取本地日志文件 {log_file_path} 失败: {e}")

    for attempt in range(max_retries):
        try:
            print(f"[DEBUG] 正在获取 Job {job_id} 的日志 (尝试 {attempt + 1}/{max_retries})")
            response = requests.get(url, headers=headers)
            if response.status_code == 404:
                print(f"[DEBUG] 日志尚未生成 (404)，继续等待...")
                return None
            response.raise_for_status()
            log_content = response.text
            os.makedirs(os.path.join(project_root, "logs"), exist_ok=True)
            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(log_content)
            print(f"[DEBUG] 完整日志已保存到 {log_file_path}")
            print(f"[DEBUG] 日志长度: {len(log_content)} 字符")
            print(f"[DEBUG] 日志前1000字符: {log_content[:1000]}...")
            return log_content
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] 获取 Job {job_id} 日志失败: {e}")
            if attempt < max_retries - 1:
                print(f"[DEBUG] 等待 2 秒后重试...")
                time.sleep(2)
            else:
                raise Exception(f"获取 Job {job_id} 日志失败，经过 {max_retries} 次重试")

def get_current_commit_sha():
    """获取当前 commit SHA"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        commit_sha = result.stdout.strip()
        print(f"[DEBUG] 当前 commit SHA: {commit_sha}")
        return commit_sha
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 获取当前 commit SHA 失败: {e}")
        return None

def save_processed_runs(processed_run_ids, processed_runs_file):
    """保存 processed_run_ids 到文件"""
    try:
        with open(processed_runs_file, "w") as f:
            json.dump(processed_run_ids, f, indent=2)
        print(f"[DEBUG] 已保存 processed_run_ids 到 {processed_runs_file}: {processed_run_ids}")
    except Exception as e:
        print(f"[ERROR] 保存 processed_run_ids 失败: {e}")

def load_processed_runs(processed_runs_file):
    """加载 processed_run_ids"""
    try:
        if os.path.exists(processed_runs_file):
            with open(processed_runs_file, "r") as f:
                content = f.read().strip()
                if not content:
                    print(f"[DEBUG] {processed_runs_file} 文件为空，初始化为空字典")
                    return {}
                run_ids = json.loads(content)
                if not isinstance(run_ids, dict):
                    print(f"[ERROR] {processed_runs_file} 格式错误，预期为字典，实际为: {run_ids}")
                    return {}
                processed_run_ids = {str(k): v for k, v in run_ids.items()}
                print(f"[DEBUG] 从 {processed_runs_file} 加载了 {len(processed_run_ids)} 个已处理运行: {processed_run_ids}")
                return processed_run_ids
        print(f"[DEBUG] {processed_runs_file} 文件不存在，初始化为空字典")
        return {}
    except Exception as e:
        print(f"[ERROR] 加载 processed_run_ids 失败: {e}")
        return {}

def get_actions_logs(repo, github_token, branch, backup_dir, iteration, workflow_file, last_commit_sha=None, push_changes_func=None, processed_run_ids=None):
    """获取 GitHub Actions 日志，整合 og_retriever.py 的逻辑"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if repo == "owner/repo":
        print("[ERROR] GITHUB_REPOSITORY 未正确设置，默认值为 'owner/repo'，请设置正确的仓库名称")
        return "", None, None, "Invalid repository configuration", False, [], {}, None, []

    if branch == "main":
        print("[WARNING] GITHUB_BRANCH 未明确设置，使用默认值 'main'，请确认分支名称是否正确")

    if not os.path.exists(workflow_file):
        print("[ERROR] debug.yml 文件不存在，初始化并推送默认工作流")
        default_workflow = {
            "name": "WeatherApp CI",
            "on": {"push": {"branches": ["main"]}, "pull_request": {"branches": ["main"]}},
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

    workflow_check_url = f"https://api.github.com/repos/{repo}/contents/{workflow_file.replace(project_root + '/', '')}?ref={branch}"
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
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

    max_retries = 3
    max_outer_wait_time = 1800
    outer_wait_interval = 30
    elapsed_outer_time = 0
    error_count = 0
    processed_runs_file = os.path.join(project_root, "processed_runs.json")
    processed_run_ids = load_processed_runs(processed_runs_file) if processed_run_ids is None else processed_run_ids
    run_id_counts = {}

    print("[DEBUG] 尝试获取最近的日志...")
    current_time = datetime.now(timezone.utc)
    recent_time = current_time - timedelta(minutes=15)
    run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=recent_time, fallback_to_30_days=False)
    if not run:
        print("[DEBUG] 最近15分钟内未找到运行，回退到前30天...")
        run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=None, fallback_to_30_days=True)

    if run:
        run_id = str(run["id"])
        state = run["status"]
        conclusion = run["conclusion"]
        run_commit_sha = run.get("head_sha")
        run_timestamp = run.get("created_at")
        logs_url = run.get("logs_url")  # 获取 logs_url
        print(f"[DEBUG] 找到现有运行 {run_id} (状态: {state}, 结果: {conclusion}, commit SHA: {run_commit_sha}, 时间戳: {run_timestamp})")
        
        # 初始化 log_content 和 annotations_error
        log_content = ""
        annotations_error = ""

        if run_id in processed_run_ids:
            run_status = processed_run_ids.get(run_id, {})
            processed = run_status.get("processed", False)
            success = run_status.get("success", False)
            push_failed = run_status.get("push_failed", False)
            print(f"[DEBUG] 运行 {run_id} 处理状态: processed={processed}, success={success}, push_failed={push_failed}")
            if push_failed:
                print(f"[DEBUG] 运行 {run_id} 上次推送失败，重新尝试推送...")
                try:
                    push_changes_func(f"AutoDebug: Retry push for run {run_id}", run_id, branch)
                    push_time = datetime.now(timezone.utc)
                    print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                    processed_run_ids.clear()
                    save_processed_runs(processed_run_ids, processed_runs_file)
                    print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                    time.sleep(600)
                    elapsed_outer_time += 600
                except Exception as e:
                    print(f"[ERROR] 推送再次失败: {e}")
                    processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                    save_processed_runs(processed_run_ids, processed_runs_file)
                    print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                    return None, None, None, None, False, [], {}, None, []
                return None, None, None, None, False, [], {}, None, []
            if processed and not success:
                print(f"[DEBUG] 运行 {run_id} 已处理但未成功修复，重新分析日志...")
                del processed_run_ids[run_id]
                save_processed_runs(processed_run_ids, processed_runs_file)
            else:
                print(f"[DEBUG] 运行 {run_id} 已处理且成功，触发强制推送...")
                try:
                    push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
                    push_time = datetime.now(timezone.utc)
                    print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                    processed_run_ids.clear()
                    save_processed_runs(processed_run_ids, processed_runs_file)
                    print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                    time.sleep(600)
                    elapsed_outer_time += 600
                except Exception as e:
                    print(f"[ERROR] 推送失败: {e}")
                    processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                    save_processed_runs(processed_run_ids, processed_runs_file)
                    print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                    return None, None, None, None, False, [], {}, None, []
                return None, None, None, None, False, [], {}, None, []

        processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": False}
        save_processed_runs(processed_run_ids, processed_runs_file)

        if state != "completed":
            print(f"[DEBUG] 检测到未完成的运行 {run_id}，等待其完成...")
            max_wait_time = 1200
            wait_interval_inner = 30
            elapsed_time = 0
            run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"

            while elapsed_time < max_wait_time:
                run_response = requests.get(run_url, headers=headers, timeout=30)
                if run_response.status_code != 200:
                    print(f"[DEBUG] 获取运行 {run_id} 详情失败: {run_response.status_code}")
                    time.sleep(wait_interval_inner)
                    elapsed_time += wait_interval_inner
                    continue

                run_data = run_response.json()
                state = run_data.get("status")
                conclusion = run_data.get("conclusion")
                print(f"[DEBUG] 运行 {run_id} 当前状态: {state}")

                if state == "completed":
                    break

                time.sleep(wait_interval_inner)
                elapsed_time += wait_interval_inner

            if state != "completed":
                print(f"[DEBUG] 运行 {run_id} 在 {max_wait_time} 秒内未完成，继续等待下一轮检查...")
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return None, None, None, None, False, [], {}, None, []

        # 处理 startup_failure 和 404 错误
        if conclusion == "startup_failure":
            try:
                print(f"[DEBUG] 检测到 startup_failure，尝试从 {logs_url} 获取运行日志")
                response = requests.get(logs_url, headers=headers, timeout=30)
                if response.status_code == 404:
                    print("[ERROR] 日志未找到 (404)，可能是权限不足或资源不存在")
                    annotations_error = "Log not found (404)"
                else:
                    response.raise_for_status()
                    # Logs are returned as a zip file; extract the content
                    zip_content = BytesIO(response.content)
                    with zipfile.ZipFile(zip_content, "r") as zip_ref:
                        # Assuming there's a single log file; adjust if multiple files exist
                        log_file_name = zip_ref.namelist()[0]
                        log_content = zip_ref.read(log_file_name).decode("utf-8")
                    print(f"[DEBUG] 成功获取运行 {run_id} 的日志，长度: {len(log_content)} 字符")

                    # Parse log for error messages
                    error_lines = [line for line in log_content.splitlines() if "ERROR" in line.upper() or "FAILED" in line.upper()]
                    if error_lines:
                        annotations_error = "\n".join(error_lines[:5])  # Limit to 5 lines for brevity
                        print(f"[DEBUG] 从日志中提取的错误: {annotations_error}")
                    else:
                        annotations_error = "Startup failure with no specific error message found in logs"
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] 获取运行日志失败: {e}")
                annotations_error = f"Failed to fetch run logs: {str(e)}"
            except Exception as e:
                print(f"[ERROR] 处理运行日志时出错: {e}")
                annotations_error = "Error processing run logs"

            # Append guidance for repair
            annotations_error += "\n[指导 DeepSeek]: 请检查以下问题：1. YAML 语法是否正确；2. 'runs-on' 是否为有效值（如 'Ubuntu-latest'）；3. 'steps' 是否包含有效动作（如 'actions/checkout@v4'）。避免添加重复或无效步骤。"
            return log_content, state, conclusion, annotations_error, False, [], {}, run_timestamp, []

        jobs_url = run["jobs_url"]
        annotations_error = ""
        error_details = {}
        successful_steps = []
        annotations = []

        for attempt in range(max_retries):
            jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
            if jobs_response.status_code == 200:
                break
            print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败: {jobs_response.status_code} (尝试 {attempt+1}/{max_retries})")
            time.sleep(5 * (attempt + 1))
        else:
            print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败，跳过 Annotations 获取...")
            annotations_error = "Invalid workflow file"
            return None, None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

        jobs_data = jobs_response.json()
        jobs = jobs_data.get("jobs", [])
        if not jobs:
            print(f"[ERROR] 运行 {run_id} 未找到 Jobs 信息")
            return None, None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

        job = jobs[0]
        job_id = job["id"]
        log_content = None
        try:
            log_content = get_job_logs(repo, github_token, run_id, job_id)
            if log_content is None:
                print(f"[DEBUG] 运行 {run_id} 的日志尚未生成，继续等待...")
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return None, None, None, None, False, [], {}, None, []
        except Exception as e:
            print(f"[ERROR] 获取运行 {run_id} 的日志失败: {e}")
            print(f"[DEBUG] 运行 {run_id} 失败（无法获取日志），触发强制推送...")
            try:
                push_changes_func(f"AutoDebug: Log fetch failed (run_id {run_id})", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as push_error:
                print(f"[ERROR] 推送失败: {push_error}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []

        if log_content:
            print("[DEBUG] 日志加载成功，跳过 Annotations 获取")
            annotations_error = None
            annotations = []
        else:
            print("[DEBUG] 日志加载失败，尝试获取最新运行的 Annotations")
            annotations_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/annotations"
            for attempt in range(max_retries):
                print(f"[DEBUG] 正在获取运行 {run_id} 的 Annotations (尝试 {attempt + 1}/{max_retries})")
                annotations_response = requests.get(annotations_url, headers=headers, timeout=30)
                if annotations_response.status_code == 200:
                    break
                print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败: {annotations_response.status_code} (尝试 {attempt+1}/{max_retries})")
                time.sleep(5 * (attempt + 1))
            else:
                print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败，使用默认错误信息...")
                annotations_error = "Invalid workflow file"
                time.sleep(outer_wait_interval)
                elapsed_outer_time += outer_wait_interval
                return None, None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

            job_annotations = annotations_response.json()
            annotations.extend(job_annotations)
            print(f"[DEBUG] 运行 {run_id} 的完整 Annotations 数据: {job_annotations}")
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
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval

        if conclusion == "startup_failure" and annotations_error:
            if not annotations_error:
                annotations_error = "Invalid workflow file"
            print(f"[DEBUG] 最终 Annotations 错误: {annotations_error}")
            print(f"运行 {run_id} 失败（startup_failure），尝试修复...")
            annotations_error += "\n[指导 DeepSeek]: 请检查以下问题：1. YAML 语法是否正确；2. 'runs-on' 是否为有效值（如 'Ubuntu-latest'）；3. 'steps' 是否包含有效动作（如 'actions/checkout@v4'）。避免添加重复或无效步骤。"
            return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

        with open(workflow_file, "r") as f:
            workflow = yaml.safe_load(f)
        runs_on = workflow.get("jobs", {}).get("build", {}).get("runs-on", "").lower()
        if runs_on != "Ubuntu-latest".lower():
            print("[DEBUG] debug.yml 中 runs-on 未正确设置为 ubuntu-latest，强制推送...")
            workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
            with open(workflow_file, "w") as f:
                yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
            try:
                push_changes_func(f"AutoDebug: Force fix runs-on (iteration {iteration})", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as e:
                print(f"[ERROR] 推送失败: {e}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []

        print(f"[DEBUG] 运行 {run_id} 状态（conclusion={conclusion}, has_critical_error=False)")
        return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

    print("[DEBUG] 未找到任何运行日志，触发新运行...")
    try:
        push_changes_func(f"AutoDebug: Trigger new run (iteration {iteration})", None, branch)
        push_time = datetime.now(timezone.utc)
        print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
    except Exception as e:
        print(f"[ERROR] 推送失败: {e}")
        processed_run_ids["last_push"] = {"processed": True, "success": False, "push_failed": True}
        save_processed_runs(processed_run_ids, processed_runs_file)
        print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
        return None, None, None, None, False, [], {}, None, []

    max_wait_time = 600
    wait_interval = 30
    elapsed_time = 0
    print(f"[DEBUG] 推送后开始动态检测新运行，最大等待时间 {max_wait_time} 秒，每次检查间隔 {wait_interval} 秒...")

    while elapsed_time < max_wait_time:
        run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=push_time)
        if run:
            print(f"[DEBUG] 检测到新运行 {run['id']}，停止等待...")
            break
        print(f"[DEBUG] 未检测到新运行，等待 {wait_interval} 秒后重试... (已等待 {elapsed_time} 秒)")
        time.sleep(wait_interval)
        elapsed_time += wait_interval

    if not run:
        print(f"[ERROR] 在 {max_wait_time} 秒内未检测到新运行，尝试重新推送...")
        try:
            push_changes_func(f"AutoDebug: Retry trigger new run (iteration {iteration})", None, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
        except Exception as e:
            print(f"[ERROR] 推送再次失败: {e}")
            processed_run_ids["last_push"] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []

        elapsed_time = 0
        while elapsed_time < max_wait_time:
            run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=push_time)
            if run:
                print(f"[DEBUG] 检测到新运行 {run['id']}，停止等待...")
                break
            print(f"[DEBUG] 未检测到新运行，等待 {wait_interval} 秒后重试... (已等待 {elapsed_time} 秒)")
            time.sleep(wait_interval)
            elapsed_time += wait_interval

    if not run:
        print(f"[ERROR] 在 {max_wait_time} 秒内仍未获取到新运行日志，停止尝试")
        return "", None, None, None, False, [], {}, None, []

    run_id = str(run["id"])
    state = run["status"]
    conclusion = run["conclusion"]
    run_commit_sha = run.get("head_sha")
    run_timestamp = run.get("created_at")

    if last_commit_sha and run_commit_sha != last_commit_sha:
        print(f"[DEBUG] 运行 {run_id} 的 commit SHA ({run_commit_sha}) 不匹配目标 commit SHA ({last_commit_sha})，等待匹配的运行...")
        time.sleep(outer_wait_interval)
        elapsed_outer_time += outer_wait_interval
        return None, None, None, None, False, [], {}, None, []

    run_id_counts[run_id] = run_id_counts.get(run_id, 0) + 1
    if run_id_counts[run_id] >= 3:
        print(f"[DEBUG] run_id {run_id} 重复 3 次，触发强制推送")
        try:
            push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as e:
            print(f"[ERROR] 推送失败: {e}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    if run_id in processed_run_ids:
        run_status = processed_run_ids.get(run_id, {})
        processed = run_status.get("processed", False)
        success = run_status.get("success", False)
        push_failed = run_status.get("push_failed", False)
        print(f"[DEBUG] 运行 {run_id} 处理状态: processed={processed}, success={success}, push_failed={push_failed}")
        if push_failed:
            print(f"[DEBUG] 运行 {run_id} 上次推送失败，重新尝试推送...")
            try:
                push_changes_func(f"AutoDebug: Retry push for run {run_id}", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as e:
                print(f"[ERROR] 推送再次失败: {e}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []
        if processed and not success:
            print(f"[DEBUG] 运行 {run_id} 已处理但未成功修复，重新分析日志...")
            del processed_run_ids[run_id]
            save_processed_runs(processed_run_ids, processed_runs_file)
        else:
            print(f"[DEBUG] 运行 {run_id} 已处理且成功，触发强制推送...")
            try:
                push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as e:
                print(f"[ERROR] 推送失败: {e}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []

    print(f"正在检查运行 {run_id} (状态: {state}, 结果: {conclusion}, commit SHA: {run_commit_sha}, 时间戳: {run_timestamp})")
    processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": False}
    save_processed_runs(processed_run_ids, processed_runs_file)

    if state != "completed":
        print(f"[DEBUG] 检测到未完成的运行 {run_id}，等待其完成...")
        max_wait_time = 1200
        wait_interval_inner = 30
        elapsed_time = 0
        run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"

        while elapsed_time < max_wait_time:
            run_response = requests.get(run_url, headers=headers, timeout=30)
            if run_response.status_code != 200:
                print(f"[DEBUG] 获取运行 {run_id} 详情失败: {run_response.status_code}")
                time.sleep(wait_interval_inner)
                elapsed_time += wait_interval_inner
                continue

            run_data = run_response.json()
            state = run_data.get("status")
            conclusion = run_data.get("conclusion")
            print(f"[DEBUG] 运行 {run_id} 当前状态: {state}")

            if state == "completed":
                break

            time.sleep(wait_interval_inner)
            elapsed_time += wait_interval_inner

        if state != "completed":
            print(f"[DEBUG] 运行 {run_id} 在 {max_wait_time} 秒内未完成，继续等待下一轮检查...")
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, None, None, False, [], {}, None, []

    jobs_url = run["jobs_url"]
    annotations_error = ""
    error_details = {}
    successful_steps = []
    annotations = []

    for attempt in range(max_retries):
        jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
        if jobs_response.status_code == 200:
            break
        print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败: {jobs_response.status_code} (尝试 {attempt+1}/{max_retries})")
        time.sleep(5 * (attempt + 1))
    else:
        print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败，跳过 Annotations 获取...")
        annotations_error = "Invalid workflow file"
        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

    jobs_data = jobs_response.json()
    jobs = jobs_data.get("jobs", [])
    if not jobs:
        print(f"[ERROR] 运行 {run_id} 未找到 Jobs 信息")
        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

    job = jobs[0]
    job_id = job["id"]
    log_content = None
    try:
        log_content = get_job_logs(repo, github_token, run_id, job_id)
        if log_content is None:
            print(f"[DEBUG] 运行 {run_id} 的日志尚未生成，继续等待...")
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, None, None, False, [], {}, None, []
    except Exception as e:
        print(f"[ERROR] 获取运行 {run_id} 的日志失败: {e}")
        print(f"[DEBUG] 运行 {run_id} 失败（无法获取日志），触发强制推送...")
        try:
            push_changes_func(f"AutoDebug: Log fetch failed (run_id {run_id})", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as push_error:
            print(f"[ERROR] 推送失败: {push_error}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    if log_content:
        print("[DEBUG] 日志加载成功，跳过 Annotations 获取")
        annotations_error = None
        annotations = []
    else:
        print("[DEBUG] 日志加载失败，尝试获取最新运行的 Annotations")
        annotations_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/annotations"
        for attempt in range(max_retries):
            print(f"[DEBUG] 正在获取运行 {run_id} 的 Annotations (尝试 {attempt + 1}/{max_retries})")
            annotations_response = requests.get(annotations_url, headers=headers, timeout=30)
            if annotations_response.status_code == 200:
                break
            print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败: {annotations_response.status_code} (尝试 {attempt+1}/{max_retries})")
            time.sleep(5 * (attempt + 1))
        else:
            print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败，使用默认错误信息...")
            annotations_error = "Invalid workflow file"
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

        job_annotations = annotations_response.json()
        annotations.extend(job_annotations)
        print(f"[DEBUG] 运行 {run_id} 的完整 Annotations 数据: {job_annotations}")
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
        time.sleep(outer_wait_interval)
        elapsed_outer_time += outer_wait_interval

    if conclusion == "startup_failure" and annotations_error:
        if not annotations_error:
            annotations_error = "Invalid workflow file"
        print(f"[DEBUG] 最终 Annotations 错误: {annotations_error}")
        print(f"运行 {run_id} 失败（startup_failure），尝试修复...")
        annotations_error += "\n[指导 DeepSeek]: 请检查以下问题：1. YAML 语法是否正确；2. 'runs-on' 是否为有效值（如 'ubuntu-latest'）；3. 'steps' 是否包含有效动作（如 'actions/checkout@v4'）。避免添加重复或无效步骤。"
        return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

    with open(workflow_file, "r") as f:
        workflow = yaml.safe_load(f)
    runs_on = workflow.get("jobs", {}).get("build", {}).get("runs-on", "").lower()
    if runs_on != "Ubuntu-latest".lower():
        print("[DEBUG] debug.yml 中 runs-on 未正确设置为 ubuntu-latest，强制推送...")
        workflow["jobs"]["build"]["runs-on"] = "Ubuntu-latest"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        try:
            push_changes_func(f"AutoDebug: Force fix runs-on (iteration {iteration})", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as e:
            print(f"[ERROR] 推送失败: {e}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    print(f"[DEBUG] 运行 {run_id} 状态（conclusion={conclusion}, has_critical_error=False)")
    return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

    print("[DEBUG] 未找到任何运行日志，触发新运行...")
    try:
        push_changes_func(f"AutoDebug: Trigger new run (iteration {iteration})", None, branch)
        push_time = datetime.now(timezone.utc)
        print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
    except Exception as e:
        print(f"[ERROR] 推送失败: {e}")
        processed_run_ids["last_push"] = {"processed": True, "success": False, "push_failed": True}
        save_processed_runs(processed_run_ids, processed_runs_file)
        print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
        return None, None, None, None, False, [], {}, None, []

    max_wait_time = 600
    wait_interval = 30
    elapsed_time = 0
    print(f"[DEBUG] 推送后开始动态检测新运行，最大等待时间 {max_wait_time} 秒，每次检查间隔 {wait_interval} 秒...")

    while elapsed_time < max_wait_time:
        run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=push_time)
        if run:
            print(f"[DEBUG] 检测到新运行 {run['id']}，停止等待...")
            break
        print(f"[DEBUG] 未检测到新运行，等待 {wait_interval} 秒后重试... (已等待 {elapsed_time} 秒)")
        time.sleep(wait_interval)
        elapsed_time += wait_interval

    if not run:
        print(f"[ERROR] 在 {max_wait_time} 秒内未检测到新运行，尝试重新推送...")
        try:
            push_changes_func(f"AutoDebug: Retry trigger new run (iteration {iteration})", None, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
        except Exception as e:
            print(f"[ERROR] 推送再次失败: {e}")
            processed_run_ids["last_push"] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []

        elapsed_time = 0
        while elapsed_time < max_wait_time:
            run, processed_run_ids = get_workflow_runs(repo, github_token, branch, processed_run_ids, start_time=push_time)
            if run:
                print(f"[DEBUG] 检测到新运行 {run['id']}，停止等待...")
                break
            print(f"[DEBUG] 未检测到新运行，等待 {wait_interval} 秒后重试... (已等待 {elapsed_time} 秒)")
            time.sleep(wait_interval)
            elapsed_time += wait_interval

    if not run:
        print(f"[ERROR] 在 {max_wait_time} 秒内仍未获取到新运行日志，停止尝试")
        return "", None, None, None, False, [], {}, None, []

    run_id = str(run["id"])
    state = run["status"]
    conclusion = run["conclusion"]
    run_commit_sha = run.get("head_sha")
    run_timestamp = run.get("created_at")

    if last_commit_sha and run_commit_sha != last_commit_sha:
        print(f"[DEBUG] 运行 {run_id} 的 commit SHA ({run_commit_sha}) 不匹配目标 commit SHA ({last_commit_sha})，等待匹配的运行...")
        time.sleep(outer_wait_interval)
        elapsed_outer_time += outer_wait_interval
        return None, None, None, None, False, [], {}, None, []

    run_id_counts[run_id] = run_id_counts.get(run_id, 0) + 1
    if run_id_counts[run_id] >= 3:
        print(f"[DEBUG] run_id {run_id} 重复 3 次，触发强制推送")
        try:
            push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as e:
            print(f"[ERROR] 推送失败: {e}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    if run_id in processed_run_ids:
        run_status = processed_run_ids.get(run_id, {})
        processed = run_status.get("processed", False)
        success = run_status.get("success", False)
        push_failed = run_status.get("push_failed", False)
        print(f"[DEBUG] 运行 {run_id} 处理状态: processed={processed}, success={success}, push_failed={push_failed}")
        if push_failed:
            print(f"[DEBUG] 运行 {run_id} 上次推送失败，重新尝试推送...")
            try:
                push_changes_func(f"AutoDebug: Retry push for run {run_id}", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as e:
                print(f"[ERROR] 推送再次失败: {e}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []
        if processed and not success:
            print(f"[DEBUG] 运行 {run_id} 已处理但未成功修复，重新分析日志...")
            del processed_run_ids[run_id]
            save_processed_runs(processed_run_ids, processed_runs_file)
        else:
            print(f"[DEBUG] 运行 {run_id} 已处理且成功，触发强制推送...")
            try:
                push_changes_func(f"AutoDebug: Force push for run {run_id}", run_id, branch)
                push_time = datetime.now(timezone.utc)
                print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
                processed_run_ids.clear()
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
                time.sleep(600)
                elapsed_outer_time += 600
            except Exception as e:
                print(f"[ERROR] 推送失败: {e}")
                processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
                save_processed_runs(processed_run_ids, processed_runs_file)
                print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
                return None, None, None, None, False, [], {}, None, []
            return None, None, None, None, False, [], {}, None, []

    print(f"正在检查运行 {run_id} (状态: {state}, 结果: {conclusion}, commit SHA: {run_commit_sha}, 时间戳: {run_timestamp})")
    processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": False}
    save_processed_runs(processed_run_ids, processed_runs_file)

    if state != "completed":
        print(f"[DEBUG] 检测到未完成的运行 {run_id}，等待其完成...")
        max_wait_time = 1200
        wait_interval_inner = 30
        elapsed_time = 0
        run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"

        while elapsed_time < max_wait_time:
            run_response = requests.get(run_url, headers=headers, timeout=30)
            if run_response.status_code != 200:
                print(f"[DEBUG] 获取运行 {run_id} 详情失败: {run_response.status_code}")
                time.sleep(wait_interval_inner)
                elapsed_time += wait_interval_inner
                continue

            run_data = run_response.json()
            state = run_data.get("status")
            conclusion = run_data.get("conclusion")
            print(f"[DEBUG] 运行 {run_id} 当前状态: {state}")

            if state == "completed":
                break

            time.sleep(wait_interval_inner)
            elapsed_time += wait_interval_inner

        if state != "completed":
            print(f"[DEBUG] 运行 {run_id} 在 {max_wait_time} 秒内未完成，继续等待下一轮检查...")
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, None, None, False, [], {}, None, []

    jobs_url = run["jobs_url"]
    annotations_error = ""
    error_details = {}
    successful_steps = []
    annotations = []

    for attempt in range(max_retries):
        jobs_response = requests.get(jobs_url, headers=headers, timeout=30)
        if jobs_response.status_code == 200:
            break
        print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败: {jobs_response.status_code} (尝试 {attempt+1}/{max_retries})")
        time.sleep(5 * (attempt + 1))
    else:
        print(f"[ERROR] 获取运行 {run_id} 的 Jobs 信息失败，跳过 Annotations 获取...")
        annotations_error = "Invalid workflow file"
        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

    jobs_data = jobs_response.json()
    jobs = jobs_data.get("jobs", [])
    if not jobs:
        print(f"[ERROR] 运行 {run_id} 未找到 Jobs 信息")
        return "", None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

    job = jobs[0]
    job_id = job["id"]
    log_content = None
    try:
        log_content = get_job_logs(repo, github_token, run_id, job_id)
        if log_content is None:
            print(f"[DEBUG] 运行 {run_id} 的日志尚未生成，继续等待...")
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, None, None, False, [], {}, None, []
    except Exception as e:
        print(f"[ERROR] 获取运行 {run_id} 的日志失败: {e}")
        print(f"[DEBUG] 运行 {run_id} 失败（无法获取日志），触发强制推送...")
        try:
            push_changes_func(f"AutoDebug: Log fetch failed (run_id {run_id})", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as push_error:
            print(f"[ERROR] 推送失败: {push_error}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    if log_content:
        print("[DEBUG] 日志加载成功，跳过 Annotations 获取")
        annotations_error = None
        annotations = []
    else:
        print("[DEBUG] 日志加载失败，尝试获取最新运行的 Annotations")
        annotations_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/annotations"
        for attempt in range(max_retries):
            print(f"[DEBUG] 正在获取运行 {run_id} 的 Annotations (尝试 {attempt + 1}/{max_retries})")
            annotations_response = requests.get(annotations_url, headers=headers, timeout=30)
            if annotations_response.status_code == 200:
                break
            print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败: {annotations_response.status_code} (尝试 {attempt+1}/{max_retries})")
            time.sleep(5 * (attempt + 1))
        else:
            print(f"[ERROR] 获取运行 {run_id} 的 Annotations 失败，使用默认错误信息...")
            annotations_error = "Invalid workflow file"
            time.sleep(outer_wait_interval)
            elapsed_outer_time += outer_wait_interval
            return None, None, conclusion, annotations_error, False, [], error_details, run_timestamp, annotations

        job_annotations = annotations_response.json()
        annotations.extend(job_annotations)
        print(f"[DEBUG] 运行 {run_id} 的完整 Annotations 数据: {job_annotations}")
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
        time.sleep(outer_wait_interval)
        elapsed_outer_time += outer_wait_interval

    if conclusion == "startup_failure" and annotations_error:
        if not annotations_error:
            annotations_error = "Invalid workflow file"
        print(f"[DEBUG] 最终 Annotations 错误: {annotations_error}")
        print(f"运行 {run_id} 失败（startup_failure），尝试修复...")
        annotations_error += "\n[指导 DeepSeek]: 请检查以下问题：1. YAML 语法是否正确；2. 'runs-on' 是否为有效值（如 'Ubuntu-latest'）；3. 'steps' 是否包含有效动作（如 'actions/checkout@v4'）。避免添加重复或无效步骤。"
        return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations

    with open(workflow_file, "r") as f:
        workflow = yaml.safe_load(f)
    runs_on = workflow.get("jobs", {}).get("build", {}).get("runs-on", "").lower()
    if runs_on != "Ubuntu-latest".lower():
        print("[DEBUG] debug.yml 中 runs-on 未正确设置为 ubuntu-latest，强制推送...")
        workflow["jobs"]["build"]["runs-on"] = "ubuntu-latest"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow, f, sort_keys=False, indent=2, allow_unicode=True)
        try:
            push_changes_func(f"AutoDebug: Force fix runs-on (iteration {iteration})", run_id, branch)
            push_time = datetime.now(timezone.utc)
            print(f"[DEBUG] 更新 push_time: {push_time.isoformat()}")
            processed_run_ids.clear()
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已清理 processed_run_ids，重新开始查询")
            time.sleep(600)
            elapsed_outer_time += 600
        except Exception as e:
            print(f"[ERROR] 推送失败: {e}")
            processed_run_ids[run_id] = {"processed": True, "success": False, "push_failed": True}
            save_processed_runs(processed_run_ids, processed_runs_file)
            print("[DEBUG] 已记录推送失败状态，等待下一次运行...")
            return None, None, None, None, False, [], {}, None, []
        return None, None, None, None, False, [], {}, None, []

    print(f"[DEBUG] 运行 {run_id} 状态（conclusion={conclusion}, has_critical_error=False)")
    return log_content, state, conclusion, annotations_error, False, successful_steps, error_details, run_timestamp, annotations