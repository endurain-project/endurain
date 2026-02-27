# TrueNAS Deployment

Endurain can be deployed on TrueNAS using the TrueNAS App Catalog for a simplified setup experience.

## TrueNAS App Catalog

The TrueNAS App Catalog provides a one-click deployment option for Endurain on TrueNAS systems. The app definition files are located in the [`truenas/`](https://github.com/endurain-project/endurain/tree/master/truenas) directory of the repository and are designed to be submitted to the [TrueNAS Apps Catalog](https://github.com/truenas/apps).

### What's Included

The TrueNAS app definition includes:

- **Endurain container** — the main application (frontend + backend)
- **PostgreSQL database** — with configurable version (17 or 18)
- **Persistent storage** — for app data, logs, and database
- **Health checks** — automatic monitoring of app health
- **Web portal** — direct link from TrueNAS UI to Endurain

### Configuration Options

When deploying via TrueNAS, you can configure:

| Setting | Description |
| --- | --- |
| Database Password | Password for the PostgreSQL database |
| Secret Key | JWT authentication secret (generate with `openssl rand -hex 32`) |
| Fernet Key | Encryption key for sensitive data |
| Endurain Host | Your Endurain URL (e.g., `https://endurain.example.com`) |
| Behind Proxy | Enable if using a reverse proxy |
| Timezone | Your local timezone |
| WebUI Port | Port for accessing the web interface (default: 30200) |
| Additional Environment Variables | Any extra configuration from the [supported variables](advanced-started.md#supported-environment-variables) |

### Default Credentials

- **Username:** admin
- **Password:** admin

!!! alert "Change your password"
    Remember to change the default password after your first login.

## Custom App Deployment

If Endurain is not yet available in the TrueNAS App Catalog, you can deploy it as a custom app using Docker Compose. Refer to the [Getting Started](getting-started.md) guide for Docker Compose instructions, which can be adapted for TrueNAS custom app deployment.

## Contributing to the TrueNAS Catalog

To submit Endurain to the TrueNAS App Catalog:

1. Fork the [TrueNAS Apps repository](https://github.com/truenas/apps)
2. Copy the contents of the `truenas/` directory to `ix-dev/community/endurain/`
3. Follow the [TrueNAS contribution guidelines](https://github.com/truenas/apps/blob/master/CONTRIBUTIONS.md)
4. Submit a pull request
