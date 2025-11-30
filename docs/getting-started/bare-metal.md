# Bare-Metal Installation Guide

This guide explains how to install **Endurain** bare-metal on Debian without Docker.

---

## 1. Install Required Dependencies

```bash
apt install -y \
  default-libmysqlclient-dev \
  build-essential \
  pkg-config
  git \
  curl
```

---

## 2. Install Required Runtime Tools

Install the required tools from their official sources:

uv (Python) → https://docs.astral.sh/uv/

Node.js 22 → https://nodejs.org/en/download

PostgreSQL 17 → https://www.postgresql.org/download/

---

## 3. Download Endurain Release

```bash
mkdir -p /path/to/endurain
cd /path/to/endurain

curl -L https://github.com/joaovitoriasilva/endurain/archive/refs/tags/latest.tar.gz \
  | tar xz --strip-components=1 -C /path/to/endurain
```

---

## 4. Create Environment Configuration

Copy the provided example:

```bash
cp /path/to/endurain/example.env /path/to/endurain/.env
```

Genrate keys:

```bash
openssl rand -hex 32 # SECRET_KEY
openssl rand -base64 32 # FERNET_KEY
```

Prepare data storage:

```bash
mkdir -p /path/to/endurain_data/{data,logs}
```

Edit `.env`:

```bash
nano /path/to/endurain/.env
```

Adjust the environment variables and set keys. You definitely have to adjust `FRONTEND_DIR` and `BACKEND_DIR`.  
Environment variables are explained in the  
[Environment Variables Guide](advanced-started.md).

```env
BACKEND_DIR="/path/to/endurain/backend/app"
FRONTEND_DIR="/path/to/endurain/frontend/app/dist"
DATA_DIR="/path/to/endurain_data/data"
LOGS_DIR="/path/to/endurain_data/logs"
```

---

## 5. Build the Frontend

```bash
cd /path/to/endurain/frontend/app
npm ci
npm run build
```

Create `env.js`:

```bash
nano /path/to/endurain/frontend/app/dist/env.js
```

Insert:

```javascript
window.env = {
  ENDURAIN_HOST: "http://YOUR_SERVER_IP:8080",
};
```

---

## 6. Set Up the Backend

```bash
cd /path/to/endurain/backend

uv tool install poetry
uv tool update-shell
export PATH="/root/.local/bin:$PATH"

poetry self add poetry-plugin-export
poetry export -f requirements.txt --output requirements.txt --without-hashes

uv venv
uv pip install -r requirements.txt
```

---

## 7. Create systemd Service

```bash
nano /etc/systemd/system/endurain.service
```

Paste:

```ini
[Unit]
Description=Endurain FastAPI Backend
After=network.target postgresql.service

[Service]
WorkingDirectory=/path/to/endurain/backend/app
EnvironmentFile=/path/to/endurain/.env
ExecStart=/path/to/endurain/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable endurain
systemctl start endurain
```

Check status:

```bash
systemctl status endurain
```

---

## ✔️ Installation Complete

Endurain is now installed bare-metal on Debian and runs as a persistent systemd service.
