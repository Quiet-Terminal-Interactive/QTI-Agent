# QTI Agent

Internal studio assistant bot for Quiet Terminal Interactive.

---

## Setup

### 1. Create the sandbox user

```bash
sudo useradd -m -s /bin/bash qtiagent
sudo su - qtiagent
```

All following steps run as `qtiagent`.

---

### 2. Clone the bot

```bash
git clone https://github.com/Quiet-Terminal-Interactive/QTI-Agent ~/temp
mv temp/* ~
```

---

### 3. Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### 4. Download the model

```bash
mkdir -p ~/models
cd ~/models
wget https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf -O qwen3.5-4b-q4_k_m.gguf
```

---

### 5. Configure environment

```bash
cp ~/bot/.env.example ~/.env
nano ~/.env
```

Fill in all values:

```
DISCORD_TOKEN=
ALLOWED_ROLE_ID=
GITEA_URL=
GITEA_TOKEN=
MINIO_ENDPOINT=
MODEL_PATH=/home/qtiagent/models/qwen3.5-4b-q4_k_m.gguf
```

---

### 6. Run

```bash
cd ~/bot
python main.py
```

---

## Running as a service

To keep the bot alive across reboots, create a systemd service as root:

```ini
# /etc/systemd/system/qtiagent.service

[Unit]
Description=QTI Agent
After=network.target

[Service]
User=qtiagent
WorkingDirectory=/home/qtiagent/bot
ExecStart=/home/qtiagent/venv/bin/python3 /home/qtiagent/bot/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable qtiagent
sudo systemctl start qtiagent
sudo journalctl -u qtiagent -f   # tail logs
```

---

## File Structure

```
/home/qtiagent/
├── bot/                  # Bot source
│   ├── main.py           # Entry point
│   ├── agent.py          # LLM loop
│   ├── tools.py          # Tool implementations
│   ├── context_builder.py# System prompt assembly
│   ├── discord_client.py # Discord integration
│   ├── config_store.py   # Repo/bucket/changelog state
│   └── requirements.txt
├── models/               # GGUF model file
├── configs/              # Per-repo JSON configs
├── builds/               # Build workspaces + logs
├── documents/            # Document store
├── downloads/            # Files fetched from MinIO
├── ideas.json            # Idea journal
├── changelog.json        # Build changelog
├── asset_meta.json       # Asset tags/approval state
├── buckets.json          # Registered MinIO buckets
└── .env                  # Secrets
```

---

## Reaction Status

| Emoji     | Meaning                              |
| --------- | ------------------------------------ |
| 👀        | Message received, building context   |
| 🧠        | Agent is thinking / executing tools  |
| *(none)*  | Done                                 |

---

## Adding a Repo

Tell the bot in Discord:

> @QTI's Little Helper add repo qti-auth from https://gitea.internal/org/qti-auth

Or drop a JSON file directly into `~/configs/`:

```json
{
  "name": "qti-auth",
  "gitea_url": "https://gitea.internal/org/qti-auth",
  "default_branch": "main",
  "build_steps": [
    "npm install",
    "npm run build",
    "wrangler deploy"
  ],
  "env_file": ".env.qti-auth",
  "tags": ["cloudflare", "auth"]
}
```