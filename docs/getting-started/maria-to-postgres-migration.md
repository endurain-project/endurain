# MariaDB to Postgres migration guide

This will guide you on how to migrate from MariaDB to Postgres. Endurain will drop support for MariaDB on v0.16.0, so you'll need to perform this migration prior to upgrade to v0.16.0
This guide uses [pgloader](https://pgloader.io) to automate the migration.
This guide uses some [helper files](https://github.com/joaovitoriasilva/endurain/tree/master/docs). Refer to them when needed.

# Install pgloader

Refer to [pgloader docs](https://pgloader.readthedocs.io/en/latest/) for installation instructions.

# Migration steps

 1. Stop Endurain container (`docker compose down`);
 2. Backup existent database [MariaDB dump backup options](#mariadb-dump-backup-options))
 3. Run pgloader to do the migration [Do the migration](#do-the-migration);
 4. Verify migration by:
    - Checking pgloader outputs and logs.
 5. Update environment variables (adapt to your environment):
    
```bash
DB_TYPE=postgres
DB_HOST=postgres
DB_PORT=5432
```

 6. Start with PostgreSQL:
    
```bash
docker compose up -d
```

 7. Monitor logs for any issues;
 8. Verify application functionality:
    - Test login;
    - Upload test activity;
    - Check activity streams display;
    - Verify integrations (Strava, Garmin);
    - Others.

# MariaDB dump backup options

## Option 1: Run `mysqldump` / `mariadb-dump` from the host

Run the dump from your host machine (Ubuntu) using the MySQL or MariaDB client tools installed locally. You need to adjust host, port, database and password to match your environment.

```bash
mysqldump -h 127.0.0.1 -P 3306 -u endurain -p'redacted' endurain \
> final_backup_$(date +%Y%m%d_%H%M%S).sql
```

```bash
mariadb-dump -h 127.0.0.1 -P 3306 -u endurain -p'redacted' endurain \
> final_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Pros:**

 - No need to modify the container  
 - Easy to automate in cron or scripts  

**Cons:**

 - Requires MariaDB client installed on the host
 - The container’s database port must be exposed

## Option 2: Use a temporary MariaDB client container

Use a one-time client container that connects to your running MariaDB instance. You need to adjust container name, host, port, database and password to match your environment.

```bash
sudo docker run --rm \
  --network container:mariadb_endurain_prod \
  mariadb:latest \
  mariadb-dump -h127.0.0.1 -u endurain -p'redacted' endurain \
  > final_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Pros:**

- Doesn’t modify your running container
- Uses an official image that already includes `mariadb-dump`

**Cons:**

- Slightly longer to run (needs to pull/start the client container)

## Option 3: Install `mariadb-client` inside the existing container

If you prefer to back up directly from inside the existing MariaDB container, install the client tools and use `mariadb-dump`.

### Installation

Connect to the container shell and do:

- For Debian/Ubuntu-based containers:

```bash
apt-get update && apt-get install -y mariadb-client
```

- For Alpine-based containers:

```bash
apk add --no-cache mariadb-client
```

### Backup Command (Single Database, No GTID)

You need to adjust container name, host, port, database and password to match your environment.

```bash
sudo docker exec mariadb_endurain_prod sh -lc \
"mariadb-dump -u endurain -p'redacted' \
  --databases endurain \
  --single-transaction --routines --triggers --events --hex-blob" \
> final_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Pros:**

- All-in-one (runs inside the existing container)
- Direct socket access to MariaDB

**Cons:**

- You modify the production container
- Must remember to reinstall client tools after container rebuilds

# Postgres preparation for pgloader

Postgres dropped support for MD5 hashed passwords in favor of SHA256, however pgloader [does not support SHA256](https://github.com/dimitri/pgloader/issues/1207). What I did was:

 - Change password to be MD5 hashed:

```sql
set password_encryption to 'md5';
ALTER ROLE endurain password 'JUST_RETYPE_YOUR_EXISTING_PASSWORD';
```

 - Change `pg_hba.conf` file to allow MD5 logins:
    - On my machine using postgres 18 Docker image: `/opt/containers/postgres_endurain_prod/18/docker/pg_hba.conf`

```bash
# replication privilege.
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust

# Allow MD5 just for endurain (IPv4 example). # Add this line
host    all     endurain   0.0.0.0/0     md5  # Add this line

host all all all scram-sha-256
```

# Do the migration

## Prerequisites and Important Notes

⚠️ **Important Notes:**

 - DB passwords with special characters like `@` or `!` can cause issues;
 - Recommendation: Use simple passwords during migration, change them afterward;
 - The migration can be memory-intensive, especially for large `activities_streams` tables;
 - Ensure sufficient RAM (at least 4GB available) on the machine running pgloader.

## Migration Process

Remember: Always keep your MariaDB backup until you're confident the PostgreSQL migration is successful and stable.

After [pgloader](https://pgloader.readthedocs.io/en/latest/) is installed:

1. **Clone Endurain repository:**

```bash
git clone https://github.com/joaovitoriasilva/endurain
cd endurain/mariadb_to_postgres
```

2. **Edit the migration configuration:**

- Edit `mariadb_to_postgres_streams_only.load` and `mariadb_to_postgres_without_streams.load` to match your environment;
- Change DB connections (adjust host, port, database, user and password).

```sql
LOAD DATABASE
    FROM mysql://endurain:password@mariadb-host:3306/endurain
    INTO postgresql://endurain:password@postgres-host:5432/endurain
```

3. **Migration:**

The migration is splitted because activity_streams table has large json data, causing memory issues

**Step 1:** Migrate all tables except activities_streams:

```bash
pgloader --verbose --load-lisp-file transforms.lisp mariadb_to_postgres_without_streams.load > migration_main_$(date +%Y%m%d_%H%M%S).log 2>&1
```

This step may take several minutes to conclude (1h+ in my case. You can try to ajust load file to increase speed)

**Step 2:** Migrate activities_streams separately:

```bash
pgloader --verbose --load-lisp-file transforms.lisp mariadb_to_postgres_streams_only.load > migration_streams_$(date +%Y%m%d_%H%M%S).log 2>&1
```

## Revert Postgres changes

Revert changes made to user endurain:

 - Change password to be SHA256 hashed:

```sql
set password_encryption to 'scram-sha-256';
ALTER ROLE endurain password 'JUST_RETYPE_YOUR_EXISTING_PASSWORD';
```

 - Change `pg_hba.conf` file to allow MD5 logins:
    - On my machine using postgres 18 Docker image: `/opt/containers/postgres_endurain_prod/18/docker/pg_hba.conf`

```bash
# replication privilege.
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust

# Allow MD5 just for endurain (IPv4 example). # Remove this line
host    all     endurain   0.0.0.0/0     md5  # Remove this line

host all all all scram-sha-256
```

## Troubleshooting Common Issues

### Memory Exhaustion Errors

**Symptoms:** "Heap exhausted during allocation" errors, especially when processing `activities_streams` table.

**Solutions:**

1. **Increase system memory** or close other applications
2. **Reduce batch size** in the .load file:

```bash
change bellow to minor, default is 10
rows per range = 10 
```
3. **Reduce workers** in the .load file:

```bash
workers = 1, concurrency = 1,
```

### PostgreSQL Connection Issues

**Symptoms:** Connection refused or authentication errors.

**Solutions:**

1. Verify PostgreSQL is running and accessible
2. Check password authentication method (use MD5, not SCRAM-SHA-256)
3. Verify `pg_hba.conf` allows connections from pgloader host

### Large JSON Data Issues

**Symptoms:** Errors processing `stream_waypoints` column in `activities_streams`.

**Solutions:**

1. The updated `transforms.lisp` includes `stream-waypoints-to-jsonb` function
2. Use split migration approach for better memory management
3. Consider manual cleanup of very large JSON records before migration

### Migration Time Estimates

- **Small databases** (< 1000 activities): 5-15 minutes
- **Medium databases** (1000-5000 activities): 15-60 minutes  
- **Large databases** (> 5000 activities): 1+ hours

**Monitoring Progress:**

- Monitor the log file: `tail -f migration_*.log`
- Check PostgreSQL logs for any issues
- Monitor system memory usage during migration
