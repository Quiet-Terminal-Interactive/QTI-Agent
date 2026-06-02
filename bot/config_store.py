import json
import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CONFIGS_DIR = HOME / "configs"
CHANGELOG_PATH = HOME / "changelog.json"

CONFIGS_DIR.mkdir(exist_ok=True)

def _read_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data: dict | list) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _changelog() -> dict:
    data = _read_json(CHANGELOG_PATH)
    if not data:
        return {"current_version": "0.0.1", "versions": {}}
    return data


def _save_changelog(data: dict) -> None:
    _write_json(CHANGELOG_PATH, data)


def get_all_repos() -> list[str]:
    return [p.stem for p in CONFIGS_DIR.glob("*.json")]


def get_repo(name: str) -> dict | None:
    path = CONFIGS_DIR / f"{name}.json"
    if not path.exists():
        return None
    return _read_json(path)


def save_repo(name: str, config: dict) -> None:
    _write_json(CONFIGS_DIR / f"{name}.json", config)


def delete_repo(name: str) -> bool:
    path = CONFIGS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


BUCKETS_PATH = HOME / "buckets.json"


def _buckets_data() -> list[str]:
    if not BUCKETS_PATH.exists():
        return []
    return _read_json(BUCKETS_PATH)


def get_all_buckets() -> list[str]:
    return _buckets_data()


def add_bucket(name: str) -> bool:
    buckets = _buckets_data()
    if name in buckets:
        return False
    buckets.append(name)
    _write_json(BUCKETS_PATH, buckets)
    return True


def remove_bucket(name: str) -> bool:
    buckets = _buckets_data()
    if name not in buckets:
        return False
    buckets.remove(name)
    _write_json(BUCKETS_PATH, buckets)
    return True


def get_current_version() -> str:
    return _changelog().get("current_version", "0.0.1")


def set_current_version(version: str) -> None:
    data = _changelog()
    data["current_version"] = version
    if version not in data.setdefault("versions", {}):
        data["versions"][version] = []
    _save_changelog(data)


def get_recent_changelog(limit: int = 5) -> list[str]:
    data = _changelog()
    versions = data.get("versions", {})

    all_entries = []
    for version, entries in versions.items():
        for entry in entries:
            all_entries.append((entry.get("timestamp", ""), version, entry.get("text", "")))

    all_entries.sort(key=lambda x: x[0], reverse=True)

    return [f"[{v}] {text}" for _, v, text in all_entries[:limit]]


def add_changelog_entry(text: str, author: str, version: str | None = None) -> str:
    from datetime import datetime, timezone

    data = _changelog()
    target_version = version or data.get("current_version", "0.0.1")
    data.setdefault("versions", {}).setdefault(target_version, [])

    entry = {
        "text": text,
        "author": author,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    data["versions"][target_version].append(entry)
    _save_changelog(data)
    return target_version


def get_changelog_for_version(version: str) -> list[dict]:
    data = _changelog()
    return data.get("versions", {}).get(version, [])


def get_all_versions() -> list[str]:
    data = _changelog()
    return list(reversed(list(data.get("versions", {}).keys())))