# Server settings

Administrators configure the instance in **Settings → Server settings**. The page is visible only to administrators, and the settings apply to everyone on the server. Changes are saved with one **Save** and take effect without a restart.

If someone else changed the settings while you were editing, your save is refused with a message to reload, so you never overwrite their change by accident.

## Settings that an environment variable controls

Some settings used to be environment variables and were moved into this page. As long as the old variable is still set on the container, the matching field is **read-only** here, and Endurain copies the variable's value into the database at each start. Remove the variable to edit the field in the page. The affected settings are:

- the session and token fields,
- the read notification retention,
- all reverse geocoding fields, as a block,
- the email settings.

The variables are listed, with their removal date, in [Advanced setup](../getting-started/advanced-setup.md#supported-environment-variables).

## Sections

### General

| Setting | Meaning |
| ------- | ------- |
| Units | Metric or imperial |
| Currency | Euro, dollar or pound, used for gear values |
| Records per page | How many rows lists show, from 1 to 100 |

### Registration

| Setting | Meaning |
| ------- | ------- |
| Allow sign-up | Whether the sign-up form is available |
| Require email verification | New users must open an emailed link first |
| Require admin approval | An administrator must approve new users |

How these work together is in [Accounts, sign-up and password reset](accounts-and-sign-in.md#signing-up). Use approval together with email verification: with approval alone the new user's email stays unverified and you must mark it verified yourself before you can approve (see [Approving sign-ups](user-management.md#approving-sign-ups)). Email verification and approval notices need [email](#email) to be configured.

### Authentication

| Setting | Meaning |
| ------- | ------- |
| Enable SSO | Shows the configured identity providers on the login page. Providers are managed under **Settings → Identity providers**; see [Single Sign-On](single-sign-on.md) |
| Allow local username and password login | Turn it off to force SSO. Turning it off locks out password sign-in for everyone, including administrators, so make sure SSO works first |
| Auto-redirect to SSO | Skip the login page when one provider is configured and local login is off |

### Password policy

A policy type (strict, or length only) and a minimum length for regular users and for administrators, from 8 to 128 characters. It applies when a password is set or changed. See [password rules](accounts-and-sign-in.md#password-rules).

### Sessions

| Setting | Range |
| ------- | ----- |
| Access token lifetime | 1 to 1440 minutes |
| Refresh token lifetime | 1 to 365 days |
| Enforce idle and absolute timeouts | On or off |
| Idle timeout | 1 to 8760 hours of inactivity |
| Absolute timeout | 1 to 8760 hours, not below the idle timeout |

The refresh token lifetime is how long a login on a device stays valid. The idle and absolute timeouts are off by default.

### Data retention

How many days **read** notifications are kept before they are deleted, from 0 to 3650. 0 keeps them forever. Unread notifications are never deleted.

### Public sharing

Public links and whether they show the owner. See [Sharing, privacy and followers](sharing-and-privacy.md#public-links).

### Maps

The tile server used for maps in the browser and for map thumbnails, its attribution and the map background colour. Read [Map tile server](../getting-started/advanced-setup.md#map-tile-server) before using a provider that needs an API key, because the URL is public and the key field is write-only.

Changing a tile setting can regenerate every activity thumbnail, and an option next to the tile settings controls whether it does. Regeneration runs in the background and can take a while on a large library. See [Background work and failure handling](../getting-started/background-work-by-module.md#activity-thumbnails).

### Reverse geocoding

Reverse geocoding turns an activity's coordinates into a city and country.

| Setting | Meaning |
| ------- | ------- |
| Service | Nominatim, Photon or Geocode Maps |
| Host | Host and optional port of the service. Empty uses the service's own host. Enter `host[:port]` only, with no scheme or path |
| Use HTTPS | Whether the host is addressed over HTTPS |
| Rate limit | Requests per second, from 0 (no throttling) to 100 |
| API key | Needed for Geocode Maps. Stored encrypted and never shown again |

The public Nominatim and Photon servers expect about one request per second, so keep the rate limit at 1 if you use them. Locations that could not be looked up, for example during a big import, are filled in later by a job that runs every hour.

### Login photo

The image shown on the login page. Upload an image of up to 5 MB, ideally square. The settings page accepts PNG files; the API also accepts JPEG, GIF and WebP. Removing it restores the default. The photo is public because the login page needs it before anyone is signed in. See [Image personalization](../getting-started/advanced-setup.md#image-personalization).

### Email

| Setting | Meaning |
| ------- | ------- |
| Host and port | Your mail server. An empty host turns email off |
| Security | `starttls`, `ssl` or none. No encryption is allowed only for a private or loopback host, and not together with a username and password |
| Username and password | Credentials, if the server needs them. The password is write-only and stored encrypted |
| From address | The sender. If empty, the username is used. Some providers (Brevo, for example) require a verified sender that differs from the login |

Use **Send test email** to check the settings: it sends a message to you straight away and shows the failure reason if it cannot. Email is used for sign-up verification, approval notices and password resets. Without it those flows cannot send mail; see [Accounts, sign-up and password reset](accounts-and-sign-in.md).

When several replicas run, the email and geocoding settings are cached for a few seconds in each process, so a change reaches every replica quickly but not instantly.

### Server logs

A viewer of the newest application log records, with a minimum level, text search, download and clear. It is available only when a single process writes the log file, so it is hidden on the public demo and on multi-process deployments, where logs belong in your platform's log collection. See [Monitoring](../getting-started/monitoring.md).
