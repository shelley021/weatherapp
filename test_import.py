import sys
import os

# Dynamically add project root to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)
print(f"[DEBUG] Added root to sys.path: {project_root}")

# Test imports
try:
    from autodebug.config import load_config
    print("[SUCCESS] Imported load_config from autodebug.config")
except ImportError as e:
    print(f"[ERROR] Failed to import load_config: {e}")

try:
    from autodebug.log_retriever import get_actions_logs
    print("[SUCCESS] Imported get_actions_logs from autodebug.log_retriever")
except ImportError as e:
    print(f"[ERROR] Failed to import get_actions_logs: {e}")

try:
    from autodebug.log_parser import parse_log_content
    print("[SUCCESS] Imported parse_log_content from autodebug.log_parser")
except ImportError as e:
    print(f"[ERROR] Failed to import parse_log_content: {e}")

try:
    from autodebug.fix_applier import analyze_and_fix
    print("[SUCCESS] Imported analyze_and_fix from autodebug.fix_applier")
except ImportError as e:
    print(f"[ERROR] Failed to import analyze_and_fix: {e}")

try:
    from autodebug.history import load_processed_runs, save_processed_runs, load_fix_history, save_fix_history
    print("[SUCCESS] Imported history functions from autodebug.history")
except ImportError as e:
    print(f"[ERROR] Failed to import history functions: {e}")

try:
    from autodebug.workflow_validator import validate_and_fix_debug_yml
    print("[SUCCESS] Imported validate_and_fix_debug_yml from autodebug.workflow_validator")
except ImportError as e:
    print(f"[ERROR] Failed to import validate_and_fix_debug_yml: {e}")

try:
    from autodebug.git_utils import push_changes
    print("[SUCCESS] Imported push_changes from autodebug.git_utils")
except ImportError as e:
    print(f"[ERROR] Failed to import push_changes: {e}")