import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
TIMEOUT_SECONDS = 30


def list_screeners():
    if not os.path.isdir(SCRIPTS_DIR):
        return []
    names = [
        fname[:-3]
        for fname in os.listdir(SCRIPTS_DIR)
        if fname.endswith(".py") and not fname.startswith("_")
    ]
    return sorted(names)


def run_screener(name):
    """Run scripts/<name>.py in an isolated subprocess and parse its stdout as JSON.

    Returns (results, error): exactly one is None. Never raises.
    """
    if name not in list_screeners():
        return None, f"Unknown screener '{name}'."

    script_path = os.path.join(SCRIPTS_DIR, f"{name}.py")

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"Screener '{name}' timed out after {TIMEOUT_SECONDS}s."
    except Exception as e:
        return None, f"Failed to run screener '{name}': {e}"

    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no error output"
        return None, f"Screener '{name}' crashed (exit {proc.returncode}): {detail}"

    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, f"Screener '{name}' did not print valid JSON."

    if not isinstance(data, list) or not all(isinstance(r, dict) and "symbol" in r for r in data):
        return None, f"Screener '{name}' output did not match the expected results format."

    return data, None
