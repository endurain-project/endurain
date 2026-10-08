# Getting started

Welcome to the guide for getting started on hosting your own production instance of Endurain. Like many other services, Endurain is easiest to get up and running trough Docker compose. It is possible to get Endurain up and running without a domain and reverse proxy, but this guide assumes you want to use a reverse proxy and your domain. Endurain can run on any computer that support OCI containers, but in this guide we are using Debian 13 (should also work with 12).

## Prerequisites
* Domain name pointed to your external IP address.
* Open FW rules to your server on port 443 and 80. (trough NAT if you are running ipv4)
* A computer/server with enough disk space for your activity files.
* A Linux distro that has `docker compose` cli, and `caddy` in the repositories.


## Installing Docker and Caddy reverse proxy

Note:
If you have a old-ish distro (Ubuntu 22.04 and older) you need to add the repo for Docker. Read how to do it on [Docker](https://docs.docker.com/compose/install/linux/) documentation. For newer distroes (Debian 13 and Ubuntu 24.04 it is not expected for you to have to do this step).

Install Docker:

```bash
sudo apt update -y
sudo apt install docker.io docker-compose -y
```

Confirm your user has the id 1000:

```bash
id
```

The container runs as a non-root user. The default container UID is 1000, matching the most common host user. If your host user has a different UID, use `user: '<UID>:<GID>'` in `docker-compose.yml` and ensure your bind-mounted directories are writable by that user.

## Installing Caddy reverse proxy

Note:
If you have a old-ish distro (Ubuntu 22.04 and older) you need to add the repo for Caddy. Read how to do it on [Caddy](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) documentation. For newer distroes (Debian 13 and Ubuntu 24.04 it is not expected for you to have to do this step).

```bash
sudo apt update -y
sudo apt install caddy -y
```

## Installing Nginx Proxy Manager reverse proxy

Nginx Proxy Manager comes as a pre-built Docker image. Please refer to the [docs](https://nginxproxymanager.com/guide/) for details on how to install it.

## Create directory structure

Data is stored on the host under `/var/opt/endurain/` by default. This location is controlled by the `LOCAL_PATH` variable in `.env` — uncomment it and set your own path if needed.

Create the required directories:

```bash
sudo mkdir -p /var/opt/endurain/backend/{data,logs}
sudo chown -R 1000:1000 /var/opt/endurain/backend
```

> **Note:** The `chown` above assumes your container UID is 1000 (default). If you use a different UID via `user:` in docker-compose, change the `chown` to match. For bind mounts, Docker auto-creates only the mount root (`backend`) as root — the `data` and `logs` subdirectories must be created in advance on the host so they inherit the parent's ownership.

## Docker compose Deployment

In this example of setting up Endurain, we will need two files. One `docker-compose.yml` and `.env`.

* docker-compose.yml tells your system how to set up the container, network and storage.
* .env holds our secrets and environment variables.

Splitting up the setup like this make it easy to handle updates to the containers, without touching the secrets and other variables.

### Creating the docker-compose and .env file

To make it as easy as possible for selfhoster to get up and running examples of docker-compose.yml and .env is on the git repo. Here are links to the files on the repo:

* [docker-compose.yml.example](https://raw.githubusercontent.com/endurain-project/endurain/master/docker-compose.yml.example)
* [.env.example](https://raw.githubusercontent.com/endurain-project/endurain/master/.env.example)

```bash
cd /var/opt/endurain
wget https://raw.githubusercontent.com/endurain-project/endurain/master/docker-compose.yml.example
wget https://raw.githubusercontent.com/endurain-project/endurain/master/.env.example

mv docker-compose.yml.example docker-compose.yml
mv .env.example .env
```

Now set the values in `.env` to match your environment. The data storage location is controlled by `LOCAL_PATH` — it is commented out by default and defaults to `/var/opt/endurain`. Uncomment and change it if you need a different path.

Here is an explanation of what you can set in the `.env`:

Environment variable  | How to set it |
| --- | --- |
| LOCAL_PATH | Root directory for Docker volume mounts (activity files, images, logs, database data). Defaults to `/var/opt/endurain`. Set to any absolute path. |
| DB_PASSWORD | Run `openssl rand -hex 32` on a terminal to get a secret, or use the [Secret Generators](../tools.md#secret-generators) tool |
| POSTGRES_PASSWORD | Set the same value as DB_PASSWORD.|
| SECRET_KEY | Run `openssl rand -hex 32` on a terminal to get a secret, or use the [Secret Generators](../tools.md#secret-generators) tool. Example output is `69b85208190c96821050d4ba980a8a95d928ab7e0ebf1a40b8ef6d09fd8367d3`. |
| FERNET_KEY | Run `openssl rand -base64 32` on a terminal to get a secret, or use the base64 tool in the [Secret Generators](../tools.md#secret-generators). Example output is `7NfMMRSCWcoNDSjqBX8WoYH9nTFk1VdQOdZY13po53Y=`. |
| TZ | Timezone definition. Insert your timezone. List of available time zones [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). Format `Europe/Lisbon` expected |
| ENDURAIN_HOST | https://endurain.yourdomain.com |
| BEHIND_PROXY | Change to true if behind reverse proxy |
| POSTGRES_DB | Postgres name for the database. |
| POSTGRES_USER | Postgres user for the database. |

**Please note:**

`POSTGRES_DB` and `POSTGRES_USER` are values for the database. If you change it from endurain, you also need to set the environment variables for the app image. Please leave them as `endurain` if you are unsure.

### Start the stack

It is finally time to start the stack!

```bash
cd /var/opt/endurain
sudo docker compose up -d
```

Check the log output:

```bash
docker compose logs -f
```

If you do not get any errors, continue to next step.

#### SELinux on Fedora, RHEL, CentOS, and other enforcing distributions

On distributions with SELinux enforcing (check with `getenforce`), Docker bind-mounted directories inherit the host's SELinux context instead of the `container_file_t` context that containers require. This can cause permission errors like:

```
redis  | find: .: Permission denied
endurain-postgres | mkdir: cannot create directory '/var/lib/postgresql/data/pgdata': Permission denied
```

The example docker-compose files include `:Z` and `:z` flags on all bind-mounted volumes to handle this automatically:

- **`:Z`** (private) — labels the volume so only the mounting container can access it. Used for postgres, redis, backend data, and logs where a single container owns the volume.
- **`:z`** (shared) — labels the volume so multiple containers can share it. Used in the multiple-backends example for shared data and logs.

> **Note for Debian, Ubuntu, and other non-SELinux distributions:** These flags are silently ignored by Docker and have no effect. No action is required on your part.

If you are using the provided docker-compose files as-is, these flags should resolve SELinux permission errors automatically. If you have customized your volume structure or added new bind-mounted volumes, you may need to apply the `container_file_t` context manually:

```bash
sudo chcon -Rt container_file_t <host_path>/postgres
sudo chcon -Rt container_file_t <host_path>/redis
```

Replace `<host_path>` with the actual path on your host machine (e.g., `/opt/endurain`, `/var/opt/endurain`, or a custom location you chose). The same principle applies to any bind-mounted volume that a container needs to write to.

After applying the context, restart the stack:

```bash
sudo docker compose up -d
```

> **Note:** The SELinux context persists across container restarts and updates. If you recreate or move the directories, you will need to reapply the context.

### Visit the site

* Visit the site insecurly on `http://<IP-OF-YOUR-SERVER>:8080`
* We still can not login to the site, because the `ENDURAIN_HOST` doesn't match our local URL.

## Configure a reverse proxy

* Before we configure a reverse proxy you need to set your DNS provider to point your domain to your external IP.
* You also need to open your firewall on port 443 and 80 to the server.

###  Configure Caddy as reverse proxy and get SSL cert from letsencrypt

We use Caddy outside docker. This way Debian handles the updates (you just need to run `sudo apt update -y` and `sudo apt upgrade -y`)

Caddy is configured in the file `/etc/caddy/Caddyfile`

Open the file in your favourite editor, delete the default text, and paste in this:

```conf
endurain.yourdomain.com {
        reverse_proxy localhost:8080
}
```

Restart Caddy

```bash
sudo systemctl restart caddy
```

Check the ouput of Caddy with:

```bash
sudo journalctl -u caddy
```

###  Configure Nginx Proxy Manager as reverse proxy and get SSL cert from letsencrypt

Below is an example config file for Endurain. This is the content of the **Advanced**
tab of the proxy host in Nginx Proxy Manager. The section labels shown in the NPM UI
(`Let's Encrypt SSL`, `Asset Caching`, etc.) are comments and **must** be prefixed with
`#`, otherwise Nginx will fail to start with an `unknown directive` error.

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
    set $port 8884;

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

## Access your Endurain instance

You should now be able to access your site on endurain.yourdomain.com

**Log in with username: admin password: admin, and remember to change the password**

🎉 **Weee** 🎉 You now have your own instance of Endurain up and running!

## How to update

* Take a backup of your files and db.
* Check for new releases of the container image [here](https://github.com/endurain-project/endurain). Read release notes carefully for breaking changes.
* Log on your server and run:
* In docker-compose.yml, update the image tag. If you are running the `:latest` tag, no changes are needed.


```bash
cd /var/opt/endurain
sudo docker compose pull
sudo docker compose up -d
```

The same is the case for Postgres. Check for breaking changes in release notes on [Postgres Website](https://www.postgresql.org/docs/release/).

** It is generally pretty safe to upgrade postgres minor version f.eks 17.4 to 17.5, but major is often breaking change (example 17.2 to 18.1 )


## Things to think about

You should implement backup strategy for the following directories:

```bash
/var/opt/endurain/backend/data
/var/opt/endurain/backend/logs
```

You also need to backup your postgres database. It is not good practice to just backup the volume `/var/opt/endurain/postgres` — this might be corrupted if the database is in the middle of a write when it goes down.

## Default Credentials

- **Username:** admin  
- **Password:** admin
