# MariaDB to Postgres migration guide

This will guide you on how to migrate from MariaDB to Postgres. Endurain will drop support for MariaDB on v0.16.0, so you'll need to perform this migration prior to upgrade to v0.16.0 or higher.

This guide uses Endurain's built-in export/import functionality to migrate your data.

## Prerequisites

- Endurain instance running with MariaDB
- PostgreSQL database set up and accessible
- Admin access to your Endurain instance

⚠️ **Important Notes:**

- The export/import process will migrate all user data **except user password**. Each user will have to do this process
- You will need to use default credentials (admin/admin) on new setup
- Keep your existing MariaDB database running for rollback if needed
- The import process can take time for large databases with many activities
- Server settings are not migrated

## Migration Steps

### Step 1: Export Data from MariaDB Instance

1. Instruct each user to log in to Endurain instance (currently running with MariaDB)
2. Each user should navigate to **Settings** → **My Profile** → **Export/Import**
3. Each user should lick **Export** to download a `.zip` file containing the user data
4. Each user should save this file in a safe location

⚠️ **Do NOT delete your existing MariaDB database** - keep it for rollback if needed.

### Step 2: Stop Current Endurain Instance

Stop your current Endurain container:

```bash
docker compose down
```

### Step 3: Update Environment Variables

Update your environment variables to point to PostgreSQL (adapt to your environment):

```bash
DB_TYPE=postgres
DB_HOST=postgres
DB_PORT=5432
DB_USER=endurain
DB_PASSWORD=your_postgres_password
DB_NAME=endurain
```

Ensure your PostgreSQL database exists and is accessible with these credentials.

### Step 4: Start Fresh Endurain with PostgreSQL

Start Endurain with the new PostgreSQL configuration:

```bash
docker compose up -d
```

This will start a fresh Endurain instance with:
- Empty PostgreSQL database
- Default admin credentials: **admin/admin**

### Step 5: Import Data

1. Log in with default credentials: **admin/admin**
2. Create a new user for each of your instance users if applicable
3. Each user should navigate to **Settings** → **My Profile** → **Export/Import**
4. Each user should click **Import** and select the `.zip` file exported
5. Wait for the import to complete (this may take several minutes for large databases)

⚠️ **Note:** User passwords are NOT imported for security reasons. All users will need to reset their passwords.

### Step 6: Verify Migration

Verify the migration was successful by checking:

- All activities are present
- Activity streams display correctly
- Activity media files load
- Gear information is correct
- Integrations (Strava, Garmin) are configured
- Health data is present

## Troubleshooting

### If Import Fails

If the import process fails:

1. Check the application logs in the container
2. Check the `app.log` file
3. **Paste both outputs** (container logs and app.log contents) when seeking help

### Rolling Back to MariaDB

If you need to rollback:

1. Stop the PostgreSQL instance:

```bash
docker compose down
```

2. Restore your original environment variables (MariaDB settings)
3. Start your original MariaDB instance:

```bash
docker compose up -d
```