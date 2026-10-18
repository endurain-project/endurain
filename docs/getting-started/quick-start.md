# Quick start

This guide covers hosting your own production instance of Endurain with Docker Compose. You can run Endurain without a domain and reverse proxy, but this guide assumes you will add both afterwards (see [Reverse proxy](reverse-proxy.md)). Endurain runs on any machine that supports OCI containers. The examples use Debian 13 (Debian 12 should also work).

## Prerequisites

* A domain name pointing to your external IP address.
* Firewall rules (and NAT, if you are on IPv4) that allow ports 80 and 443 to your server.
* A server with enough disk space for your activity files.
* A Linux distribution that provides the `docker compose` CLI.

## Installing Docker

!!! note
    On older distributions (Ubuntu 22.04 and older) you need to add Docker's repository first, as described in the [Docker documentation](https://docs.docker.com/compose/install/linux/). This is not needed on Debian 13 or Ubuntu 24.04.

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

* Open `http://<IP-OF-YOUR-SERVER>:8080` (unencrypted).
* You cannot log in yet, because `ENDURAIN_HOST` does not match this URL. Set up a [reverse proxy](reverse-proxy.md) next.

## Default credentials

After setup, log in with the credentials below and change the password right away.

- **Username:** admin
- **Password:** admin

## Next steps

* [Reverse proxy](reverse-proxy.md): Caddy or Nginx Proxy Manager with a Let's Encrypt certificate.
* [Updates and backups](operations.md)
* [Advanced setup](advanced-setup.md): all environment variables.
* [Scaling and background jobs](scaling-and-background-jobs.md)
