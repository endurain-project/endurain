# Bare-Metal Installation Guide

This guide explains how to install **Endurain** bare-metal on Debian without Docker.

## 1. Install Required Dependencies

```bash
apt install -y \
  build-essential \
  git \
  curl \
  python3-dev
```

## 2. Install Required Runtime Tools

Install the required tools from their official sources:

- uv (Python) → https://docs.astral.sh/uv/
- Node.js 22 → https://nodejs.org/en/download
- PostgreSQL 17 → https://www.postgresql.org/download/

## 3. Download Endurain Release

Run the following command to download and unpack the latest release.

```bash
mkdir -p /path/to/endurain
cd /path/to/endurain

TAG=$(curl -s https://api.github.com/repos/endurain-project/endurain/releases | grep -oP '"tag_name": "\K([^"]+)' | head -n 1)
curl -L "https://github.com/endurain-project/endurain/archive/refs/tags/$TAG.tar.gz" \
  | tar xz
EXTRACTED=$(ls -d endurain-*)
shopt -s dotglob
mv "$EXTRACTED"/* .
shopt -u dotglob
rm -rf "$EXTRACTED"
```

## 4. Create Environment Configuration

Prepare data storage.

```bash
mkdir -p /path/to/endurain_data/{data,logs}
```

Copy the provided example.

```bash
cp /path/to/endurain/.env.example /path/to/endurain/.env
```

Generate your `SECRET_KEY` and `FERNET_KEY`. These keys are required for Endurain to work, so be sure to paste them into your `.env` file. You can run the commands below or use the [Secret Generators](../tools.md#secret-generators) tool.

```bash
openssl rand -hex 32 # SECRET_KEY
openssl rand -base64 32 # FERNET_KEY
```

Edit `.env` file.

```bash
nano /path/to/endurain/.env
```

Adjust the environment variables and set keys. You definitely have to adjust `FRONTEND_DIR`, `BACKEND_DIR` and `DB_HOST`.  
Environment variables are explained in the [Environment Variables Guide](advanced-started.md).

```env
DB_HOST=localhost
BACKEND_DIR="/path/to/endurain/backend/app"
FRONTEND_DIR="/path/to/endurain/frontend/dist"
DATA_DIR="/path/to/endurain_data/data"
LOGS_DIR="/path/to/endurain_data/logs"
```

## 5. Build the Frontend

```bash
cd /path/to/endurain/frontend
npm ci
npm run build
```

Create `env.js`. Edit the URL if you use a reverse proxy.

```bash
cat << 'EOF' > /path/to/endurain/frontend/dist/env.js
window.env = {
  ENDURAIN_HOST: "http://YOUR_SERVER_IP:8080",
};
EOF
```

## 6. Set Up the Backend

```bash
cd /path/to/endurain/backend

uv sync --no-dev
```

## 7. Setup Postgres Database

Run the following commands to create a PostgreSQL user and database for Endurain:

```bash
sudo -u postgres createuser -P endurain
sudo -u postgres createdb -O endurain endurain
```

Check that the PostgreSQL client and server encodings are set to UTF-8.

```bash
sudo -u postgres psql -c "SHOW client_encoding;"
sudo -u postgres psql -c "SHOW server_encoding;"
```

If either value is SQL_ASCII, set UTF-8 explicitly for the user and the database.

```bash
sudo -u postgres psql -c "ALTER ROLE endurain SET client_encoding = 'UTF8';"
sudo -u postgres psql -c "ALTER DATABASE endurain SET client_encoding = 'UTF8';"
```

This ensures that all connections to the endurain database default to proper UTF-8 encoding.

## 8. Systemd Service

This is an example how you could set up your systemd service.

```bash
cat << 'EOF' > /etc/systemd/system/endurain.service
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
EOF
```

Enable and start the service.

```bash
systemctl daemon-reload
systemctl enable endurain
systemctl start endurain
```

## 9. (Optional) Reverse Proxy with Nginx

If you want to serve Endurain over HTTPS on a standard domain, you can put Nginx in
front of the service. Endurain serves **both** the frontend and the API from the same
origin (the uvicorn process on port `8080`), so a single `location /` is enough — you
do **not** need a separate `location` block for the backend or for static assets.

```conf
# Redirect plain HTTP to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name endurain.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;

    server_name endurain.yourdomain.com;

    # Adjust to your certificate paths
    ssl_certificate     /etc/letsencrypt/live/endurain.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/endurain.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;

    # Endurain accepts large uploads (activity files, bulk imports, media).
    # Nginx defaults to 1m, which causes 413 errors — raise it generously.
    client_max_body_size 2000m;

    location / {
        include            proxy_params;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_pass         http://127.0.0.1:8080;
    }
}
```

When running behind a reverse proxy, make sure `ENDURAIN_HOST` in `env.js` (step 5) and
in your `.env` match the public URL (e.g. `https://endurain.yourdomain.com`). So that
uvicorn trusts the forwarded protocol headers, add `--proxy-headers` to the `ExecStart`
command in the systemd unit (step 8):

```ini
ExecStart=/path/to/endurain/backend/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --proxy-headers
```

## 10. Update to a new version of Endurain.

Remove old version and get the latest.

```bash
systemctl stop endurain
rm -rf /path/to/endurain/*
cd /path/to/endurain

TAG=$(curl -s https://api.github.com/repos/endurain-project/endurain/releases | grep -oP '"tag_name": "\K([^"]+)' | head -n 1)
curl -L "https://github.com/endurain-project/endurain/archive/refs/tags/$TAG.tar.gz" \
  | tar xz
EXTRACTED=$(ls -d endurain-*)
shopt -s dotglob
mv "$EXTRACTED"/* .
shopt -u dotglob
rm -rf "$EXTRACTED"
```

Build the Frontend.

```bash
cd /path/to/endurain/frontend
npm ci
npm run build
```

Set Up the Backend.

```bash
cd /path/to/endurain/backend
uv sync --no-dev
```

start the service.

```bash
systemctl start endurain
```
