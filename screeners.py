import ast
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
TIMEOUT_SECONDS = 30


def _prettify(name):
    return name.replace("_", " ").replace("-", " ").title()


def _describe_script(path, name):
    """Statically read a script's display name and declared PARAMS, without executing it."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (SyntaxError, OSError):
        return {"display_name": _prettify(name), "params": []}

    docstring = ast.get_docstring(tree)
    display_name = docstring.strip().splitlines()[0] if docstring else _prettify(name)

    params = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                break
            if isinstance(value, list) and all(isinstance(p, dict) and p.get("name") for p in value):
                params = value
            break

    return {"display_name": display_name, "params": params}


def list_screeners():
    """List discovered screeners as [{"name", "display_name", "params"}, ...], sorted by name."""
    if not os.path.isdir(SCRIPTS_DIR):
        return []
    names = sorted(
        fname[:-3]
        for fname in os.listdir(SCRIPTS_DIR)
        if fname.endswith(".py") and not fname.startswith("_")
    )
    return [
        {"name": name, **_describe_script(os.path.join(SCRIPTS_DIR, f"{name}.py"), name)}
        for name in names
    ]


def run_screener(name, params=None):
    """Run scripts/<name>.py in an isolated subprocess and parse its stdout as JSON.

    params (a dict, possibly empty) is passed to the script JSON-encoded as argv[1].
    Returns (results, error): exactly one is None. Never raises.
    """
    if name not in {s["name"] for s in list_screeners()}:
        return None, f"Unknown screener '{name}'."

    script_path = os.path.join(SCRIPTS_DIR, f"{name}.py")

    try:
        proc = subprocess.run(
            [sys.executable, script_path, json.dumps(params or {})],
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
