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

If you are not the user 1000, you need to set the `UID` and `GID` to your id in the .env file. But to keep this guide as easy to follow as possible, we will assume that you are user 1000.

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

Lets use `/opt/endurain/` as the root directory for our project.

```bash
sudo mkdir /opt/endurain
sudo chown 1000:1000 /opt/endurain
mkdir -p \
  /opt/endurain/backend/{data,logs} \
  /opt/endurain/postgres
```

## Docker compose Deployment

In this example of setting up Endurain, we will need two files. One `docker-compose.yml` and `.env`.

* docker-compose.yml tells your system how to set up the container, network and storage.
* .env holds our secrets and environment variables.

Splitting up the setup like this make it easy to handle updates to the containers, without touching the secrets and other variables.

### Creating the docker-compose and .env file

To make it as easy as possible for selfhoster to get up and running examples of docker-compose.yml and .env is on the git repo. Here are links to the files on the repo:

* [docker-compose.yml.example](https://raw.githubusercontent.com/endurain-project/endurain/refs/heads/master/docker-compose.yml.example)
* [.env.example](https://raw.githubusercontent.com/endurain-project/endurain/refs/heads/master/.env.example)

```bash
cd /opt/endurain
wget https://raw.githubusercontent.com/endurain-project/endurain/refs/heads/master/docker-compose.yml.example
wget https://raw.githubusercontent.com/endurain-project/endurain/refs/heads/master/.env.example

mv docker-compose.yml.example docker-compose.yml
mv .env.example .env
```

Now we need to make changes to the files to reflect *your* environment. Inside docker-compose.yml there is not much we need to do. If you want to store the files another place then `/opt/endurain` this is the file you need to change.

Here is an explaination on what you can set in the `.env`:

Environment variable  | How to set it |
| --- | --- |
| DB_PASSWORD | Run `openssl rand -hex 32` on a terminal to get a secret |
| POSTGRES_PASSWORD | Set the same value as DB_PASSWORD.|
| SECRET_KEY | Run `openssl rand -hex 32` on a terminal to get a secret |
| FERNET_KEY |Run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` on a terminal to get a secret or go to [https://fernetkeygen.com](https://fernetkeygen.com). Example output is `7NfMMRSCWcoNDSjqBX8WoYH9nTFk1VdQOdZY13po53Y=` |
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
cd /opt/endurain
sudo docker compose up -d
```

Check the log output:

```bash
docker compose logs -f
```

If you do not get any errors, continue to next step.

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

Bellow is an example config file for Endurain:
```conf
------------------------------------------------------------
endurain.yourdomain.com
------------------------------------------------------------

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
    Let's Encrypt SSL

    include conf.d/include/letsencrypt-acme-challenge.conf;
    include conf.d/include/ssl-cache.conf;
    include conf.d/include/ssl-ciphers.conf;
    ssl_certificate /etc/letsencrypt/live/npm-21/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/npm-21/privkey.pem;
    Asset Caching

    include conf.d/include/assets.conf;
    Block Exploits

    include conf.d/include/block-exploits.conf;
    HSTS (ngx_http_headers_module is required) (63072000 seconds = 2 years)

    add_header Strict-Transport-Security $hsts_header always;
    Force SSL

    include conf.d/include/force-ssl.conf;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $http_connection;
    proxy_http_version 1.1;

    access_log /data/logs/proxy-host-18_access.log proxy;
    error_log /data/logs/proxy-host-18_error.log warn;

    location / {
        HSTS (ngx_http_headers_module is required) (63072000 seconds = 2 years)

        add_header Strict-Transport-Security $hsts_header always;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $http_connection;
        proxy_http_version 1.1;
        Proxy!

        include conf.d/include/proxy.conf;
    }
    Custom

    include /data/nginx/custom/server_proxy[.]conf;
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
* Inside `/opt/endurain/docker-compose.yml`, change out the version tag (the version after `:`). If you are running `:latest` tag on the docker image, you do not have to edit anything in the docker-compose.yml file. 


```bash
cd /opt/endurain
sudo docker compose pull
sudo docker compose up -d
```

The same is the case for Postgres. Check for breaking changes in release notes on [Postgres Website](https://www.postgresql.org/docs/release/).

** It is generally pretty safe to upgrade postgres minor version f.eks 17.4 to 17.5, but major is often breaking change (example 17.2 to 18.1 )


## Things to think about

You should implement backup strategy for the following directories:

```bash
/opt/endurain/app/data
/opt/endurain/app/logs
```

You also need to backup your postgres database. It is not good practice to just backup the volume `/opt/endurain/postgres` this might be corrupted if  the database is in the middle of a wright when the database goes down.

## Default Credentials

- **Username:** admin  
- **Password:** admin
