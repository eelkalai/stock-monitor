import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYZERS_DIR = os.path.join(BASE_DIR, "analyzers")
TIMEOUT_SECONDS = 30


def list_analyzers():
    if not os.path.isdir(ANALYZERS_DIR):
        return []
    names = [
        fname[:-3]
        for fname in os.listdir(ANALYZERS_DIR)
        if fname.endswith(".py") and not fname.startswith("_")
    ]
    return sorted(names)


def run_analyzer(name, symbol):
    """Run analyzers/<name>.py <symbol> in an isolated subprocess and parse its stdout as JSON.

    Returns (result, error): exactly one is None. Never raises.
    """
    if name not in list_analyzers():
        return None, f"Unknown analyzer '{name}'."

    script_path = os.path.join(ANALYZERS_DIR, f"{name}.py")

    try:
        proc = subprocess.run(
            [sys.executable, script_path, symbol],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"Analyzer '{name}' timed out after {TIMEOUT_SECONDS}s."
    except Exception as e:
        return None, f"Failed to run analyzer '{name}': {e}"

    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "no error output"
        return None, f"Analyzer '{name}' crashed (exit {proc.returncode}): {detail}"

    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return None, f"Analyzer '{name}' did not print valid JSON."

    if not isinstance(data, dict) or not data.get("recommendation"):
        return None, f"Analyzer '{name}' output did not match the expected results format."

    return data, None
