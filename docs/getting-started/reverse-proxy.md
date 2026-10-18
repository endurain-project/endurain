# Reverse proxy

A reverse proxy gives Endurain a domain name and an HTTPS certificate. Point your DNS provider at your external IP and open ports 80 and 443 on your firewall first. Then set `ENDURAIN_HOST` (for example `https://endurain.yourdomain.com`) and `BEHIND_PROXY=true` in `.env`, and run `sudo docker compose up -d`.

## Caddy

Caddy runs outside Docker, so your distribution handles its updates.

!!! note
    On older distributions (Ubuntu 22.04 and older) you need to add Caddy's repository first, as described in the [Caddy documentation](https://caddyserver.com/docs/install#debian-ubuntu-raspbian). This is not needed on Debian 13 or Ubuntu 24.04.

```bash
sudo apt update -y
sudo apt install caddy -y
```

Open `/etc/caddy/Caddyfile`, delete the default content and paste:

```conf
endurain.yourdomain.com {
        reverse_proxy localhost:8080
}
```

Restart Caddy and check its output:

```bash
sudo systemctl restart caddy
sudo journalctl -u caddy
```

## Nginx Proxy Manager

Nginx Proxy Manager is a pre-built Docker image. See its [installation guide](https://nginxproxymanager.com/guide/).

Below is an example for the **Advanced** tab of the proxy host. The section labels shown in the NPM UI (`Let's Encrypt SSL`, `Asset Caching`, etc.) are comments and **must** be prefixed with `#`, otherwise Nginx fails to start with an `unknown directive` error.


```conf
# ------------------------------------------------------------
# endurain.yourdomain.com
# ------------------------------------------------------------

map $scheme $hsts_header {
    https "max-age=63072000; preload";
}

server {
    set $forward_scheme http;
    set $server "your_server_ip";
    set $port 8080;

    listen 80;
    listen [::]:80;

    listen 443 ssl;
    listen [::]:443 ssl;

    server_name endurain.yourdomain.com;

    http2 on;
    # Let's Encrypt SSL

    include conf.d/include/letsencrypt-acme-challenge.conf;
    include conf.d/include/ssl-cache.conf;
    include conf.d/include/ssl-ciphers.conf;
    ssl_certificate /etc/letsencrypt/live/npm-21/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/npm-21/privkey.pem;
    # Asset Caching

    include conf.d/include/assets.conf;
    # Block Exploits

    include conf.d/include/block-exploits.conf;
    # HSTS (ngx_http_headers_module is required) (63072000 seconds = 2 years)

    add_header Strict-Transport-Security $hsts_header always;
    # Force SSL

    include conf.d/include/force-ssl.conf;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_http_version 1.1;

    access_log /data/logs/proxy-host-18_access.log proxy;
    error_log /data/logs/proxy-host-18_error.log warn;

    location / {
        # HSTS (ngx_http_headers_module is required) (63072000 seconds = 2 years)

        add_header Strict-Transport-Security $hsts_header always;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $http_connection;
        proxy_http_version 1.1;
        # Proxy!

        include conf.d/include/proxy.conf;
    }
    # Custom

    include /data/nginx/custom/server_proxy.conf;
}
```

## Access your instance

Open `https://endurain.yourdomain.com` and log in with the [default credentials](quick-start.md#default-credentials).
