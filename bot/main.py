import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

log = logging.getLogger("main")

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
    log.error(f"[startup] Missing required environment variables: {', '.join(missing)}")
    log.error(f"[startup] Check {env_path} and try again.")
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
        log.info(f"[startup] Initialised {path.name}")

for d in ["configs", "builds", "documents", "downloads"]:
    (HOME / d).mkdir(exist_ok=True)

log.info("[startup] Environment OK")
log.info("[startup] Starting QTI's Little Helper...")

from discord_client import run
run()