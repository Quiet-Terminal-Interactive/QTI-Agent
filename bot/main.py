import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

#env_path = Path.home() / ".env"
env_path = "./.env"
load_dotenv(dotenv_path=env_path)

REQUIRED = [
    "DISCORD_TOKEN",
    "GITEA_URL",
    "GITEA_TOKEN",
    "MINIO_ENDPOINT",
    "MODEL_PATH",
]

missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    print(f"[startup] Missing required environment variables: {', '.join(missing)}")
    print(f"[startup] Check {env_path} and try again.")
    sys.exit(1)

from pathlib import Path
import json

HOME = Path.home()

DEFAULTS = {
    HOME / "ideas.json": [],
    HOME / "changelog.json": {"current_version": "0.0.1", "versions": {}},
    HOME / "asset_meta.json": {},
    HOME / "buckets.json": [],
}

for path, default in DEFAULTS.items():
    if not path.exists():
        with open(path, "w") as f:
            json.dump(default, f, indent=2)
        print(f"[startup] Initialised {path.name}")

for d in ["configs", "builds", "documents", "downloads"]:
    (HOME / d).mkdir(exist_ok=True)

print("[startup] Environment OK")
print("[startup] Starting QTI's Little Helper...")

from discord_client import run
run()