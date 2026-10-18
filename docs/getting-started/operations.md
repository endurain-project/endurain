# Updates and backups

## Updating

1. Back up your files and database (see below).
2. Read the [release notes](https://github.com/endurain-project/endurain/releases) for breaking changes.
3. In `docker-compose.yml`, update the image tag. If you use the `:latest` tag, no change is needed.
4. Pull the new image and restart:

```bash
cd /var/opt/endurain
sudo docker compose pull
sudo docker compose up -d
```

The same applies to Postgres: check the [Postgres release notes](https://www.postgresql.org/docs/release/) for breaking changes. Minor upgrades (for example 18.1 to 18.2) are generally safe. Major upgrades are often breaking and need a dump and restore.

## Backups

Back up these directories:

```bash
/var/opt/endurain/backend/data
/var/opt/endurain/backend/logs
```

Also back up the Postgres database with a database dump. Copying the `/var/opt/endurain/postgres` volume is not reliable: it can be corrupted if the database is writing when the copy runs.
