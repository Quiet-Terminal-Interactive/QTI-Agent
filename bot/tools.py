import json
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
BUILDS_DIR = HOME / "builds"
DOCUMENTS_DIR = HOME / "documents"
IDEAS_PATH = HOME / "ideas.json"
ASSET_META_PATH = HOME / "asset_meta.json"

BUILDS_DIR.mkdir(exist_ok=True)
DOCUMENTS_DIR.mkdir(exist_ok=True)

GITEA_URL = os.getenv("GITEA_URL", "").rstrip("/")
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "").rstrip("/")

SHELL_OUTPUT_LIMIT = 8000


def _read_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.suffix == ".json" and "meta" in path.name else []
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data: dict | list) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _truncate(text: str, limit: int = SHELL_OUTPUT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return (
        text[:half]
        + f"\n\n... [truncated {len(text) - limit} characters] ...\n\n"
        + text[-half:]
    )


def tool_shell(command: str) -> dict:
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(HOME),
            capture_output=True,
            text=True,
            timeout=300,
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        log_path = BUILDS_DIR / "last_command.log"
        with open(log_path, "w") as f:
            f.write(f"$ {command}\n\n")
            f.write("--- stdout ---\n")
            f.write(stdout)
            f.write("\n--- stderr ---\n")
            f.write(stderr)

        return {
            "stdout": _truncate(stdout),
            "stderr": _truncate(stderr),
            "exit_code": exit_code,
            "log_path": str(log_path),
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Command timed out after 5 minutes.",
            "exit_code": -1,
            "log_path": None,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "log_path": None,
        }


def tool_gitea_api(endpoint: str, method: str = "GET", body: dict | None = None) -> dict:
    if not GITEA_URL or not GITEA_TOKEN:
        return {"error": "Gitea not configured — check GITEA_URL and GITEA_TOKEN in .env"}

    url = f"{GITEA_URL}/api/v1{endpoint}"
    headers = {
        "Authorization": f"token {GITEA_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode()
            return {
                "status": resp.status,
                "body": json.loads(response_body) if response_body else {},
            }

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}", "status": e.code}
    except Exception as e:
        return {"error": str(e)}


def tool_minio_get(bucket: str, filename: str) -> dict:
    if not MINIO_ENDPOINT:
        return {"error": "MINIO_ENDPOINT not configured in .env"}

    url = f"{MINIO_ENDPOINT}/{bucket}/{filename}"
    dest = HOME / "downloads" / bucket
    dest.mkdir(parents=True, exist_ok=True)
    local_path = dest / Path(filename).name

    try:
        urllib.request.urlretrieve(url, str(local_path))
        return {"path": str(local_path), "url": url}
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason} — {url}"}
    except Exception as e:
        return {"error": str(e)}


def tool_minio_list(bucket: str, prefix: str | None = None) -> dict:
    if not MINIO_ENDPOINT:
        return {"error": "MINIO_ENDPOINT not configured in .env"}

    params = "list-type=2"
    if prefix:
        params += f"&prefix={urllib.parse.quote(prefix)}"

    url = f"{MINIO_ENDPOINT}/{bucket}?{params}"

    try:
        import urllib.parse
        import xml.etree.ElementTree as ET

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()

        root = ET.fromstring(body)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = [el.text for el in root.findall(".//s3:Key", ns)]

        return {"bucket": bucket, "files": keys, "count": len(keys)}

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}

def tool_read_config(name: str) -> dict:
    from config_store import get_repo
    config = get_repo(name)
    if config is None:
        return {"error": f"No config found for '{name}'"}
    return config

def tool_write_config(name: str, content: dict) -> dict:
    from config_store import save_repo
    try:
        save_repo(name, content)
        return {"success": True, "name": name}
    except Exception as e:
        return {"error": str(e)}


def tool_read_json(path: str) -> dict | list:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = HOME / path
    if not resolved.exists():
        return {"error": f"File not found: {resolved}"}
    try:
        return _read_json(resolved)
    except Exception as e:
        return {"error": str(e)}


def tool_write_json(path: str, content: dict | list) -> dict:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = HOME / path
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        _write_json(resolved, content)
        return {"success": True, "path": str(resolved)}
    except Exception as e:
        return {"error": str(e)}

TOOL_MAP = {
    "shell": lambda p: tool_shell(**p),
    "gitea_api": lambda p: tool_gitea_api(**p),
    "minio_get": lambda p: tool_minio_get(**p),
    "minio_list": lambda p: tool_minio_list(**p),
    "read_config": lambda p: tool_read_config(**p),
    "write_config": lambda p: tool_write_config(**p),
    "read_json": lambda p: tool_read_json(**p),
    "write_json": lambda p: tool_write_json(**p),
}


def dispatch(tool_name: str, params: dict) -> dict:
    if tool_name not in TOOL_MAP:
        return {"error": f"Unknown tool: '{tool_name}'"}

    try:
        return TOOL_MAP[tool_name](params)
    except TypeError as e:
        return {"error": f"Bad params for '{tool_name}': {e}"}
    except Exception as e:
        return {"error": f"Tool '{tool_name}' failed: {e}"}