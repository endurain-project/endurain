#!/bin/bash

# This script is used in Endurain's demo instance.

# This script restores the Postgres database from a backup by replacing
# the current postgres data folder with a backup copy. It also stops
# and restarts the Docker containers (deleting current Docker images and
# fetching new ones) to ensure a clean state. Logs are also cleared.

# To schedule this script to run daily at midnight, add the following line
# to your crontab (edit crontab with `crontab -e`):
# 0 0 * * * /opt/containers/endurain/restore_postgres.sh >> /opt/containers/endurain/restore_logfile.log 2>&1

# Exit on any error
set -e

rm -f /opt/containers/endurain/restore_logfile.log

echo "Stopping Docker containers..."
docker compose down

echo "Removing unused Docker images..."
docker image prune -a -f

echo "Removing postgres folder..."
rm -rf postgres

echo "Removing app.log..."
rm logs/app.log

echo "Copying postgres_backup to postgres..."
cp -R postgres_backup postgres

echo "Starting Docker containers..."
docker compose up -d

echo "Done! Containers are now running."