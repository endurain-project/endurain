# Server settings

Administrators configure the instance in **Settings → Server settings**. The page is visible only to administrators, and the settings apply to everyone on the server. Changes are saved with one **Save** and take effect without a restart.

If someone else changed the settings while you were editing, your save is refused with a message to reload, so you never overwrite their change by accident.

Saving a change to a setting that decides who can sign up or sign in, whether two-step verification is required, how long a session or token lives, whether public links show who shared them, or where the server sends its own requests (the reverse geocoding service, host and HTTPS switch, and the tile server URL) asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password), so a stolen session cannot weaken them. These are the sign-up and sign-in switches (including **Allow local username and password login**, single sign-on and its auto-redirect), the two-step verification requirement, the password rules and breach check, the session and token lifetimes, the API key lifetime, showing the owner's info on public links, the reverse geocoding service, host and HTTPS switch, and the tile server URL, because the server calls those addresses with the stored API keys. Changing any other setting, such as units, the geocoding rate limit, an API key or notification retention, needs no confirmation.

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
| Allow sign-up | Whether the sign-up form is available. When off, confirming a verification link of a pending sign-up and asking for a new one are refused too, so accounts still unconfirmed stay pending until sign-up is turned on again or you activate them; an account you activated without a password can still choose one from its link |
| Allow new user sign-ups through single sign-on | Whether an identity provider may create an account at the first sign-in of someone no account matches (off by default). The provider must also have **Auto-create users** on. Independent of **Allow sign-up** |
| Require email verification | New users must open an emailed link first |
| Require admin approval | An administrator must approve new users |

How these work together is in [Accounts, sign-up and password reset](accounts-and-sign-in.md#signing-up). Use approval together with email verification: with approval alone the new user's email stays unverified and you must mark it verified yourself before you can approve (see [Approving sign-ups](user-management.md#approving-sign-ups)). Email verification and approval notices need [email](#email) to be configured.

### Authentication

| Setting | Meaning |
| ------- | ------- |
| Enable SSO | Shows the configured identity providers on the login page. Providers are managed under **Settings → Identity providers**; see [Single Sign-On](single-sign-on.md) |
| Allow local username and password login | Turn it off to force SSO. Turning it off locks out password sign-in for everyone, including administrators, so make sure SSO works first |
| Auto-redirect to SSO | Skip the login page when one provider is configured and local login is off |

### Two-step verification

| Setting | Notes |
| --- | --- |
| Require two-step verification | **Not required** by default. **Administrators only** or **Everyone** makes the accounts it covers set up two-step verification (a TOTP authenticator app) before they can do anything else. See [required two-step verification](accounts-and-sign-in.md#required-two-step-verification) |

The requirement is checked on every request, so it applies to a signed-in account at its next request, you included: an account it covers without two-step verification is sent to set it up at once, and an administrator who turns it on without two-step verification of their own is too. Changing it asks for your own password and MFA code, or a fresh identity-provider sign-in if your account has no password, so an administrator without two-step verification can still turn it on. It never signs anyone out, and an account that already has two-step verification is not affected.

### Password policy

A minimum length for regular users and for administrators, from 8 to 128 characters, 15 by default. It applies when a password is set or changed. See [password rules](accounts-and-sign-in.md#password-rules).

| Setting | Notes |
| --- | --- |
| Refuse passwords found in known data breaches | Off by default. When on, each new or changed password is checked against the [Have I Been Pwned](https://haveibeenpwned.com/Passwords) range service. Only the first 5 characters of the password's SHA-1 hash are sent to `api.pwnedpasswords.com`, never the password or the full hash. The check waits at most 2 seconds; if the service cannot be reached or answers with an error, the password is accepted and a warning is logged. The server needs outbound HTTPS access to that host |

### Sessions

| Setting | Range |
| ------- | ----- |
| Access token lifetime | 1 to 1440 minutes |
| Refresh token lifetime | 1 to 365 days |
| API key maximum lifetime | 1 to 3650 days, 365 by default |
| Enforce idle timeout | On or off; on for new installs, an existing install keeps its setting |
| Idle timeout | 1 to 8760 hours of inactivity, 72 for new installs, an existing install keeps its setting |
| Absolute timeout | 1 to 8760 hours, 720 (30 days) by default, not below the idle timeout |

The refresh token lifetime is how long a login on a device stays valid. When the absolute timeout ends a session before its refresh token expires, the client is told the earlier time. The absolute timeout always applies; the idle timeout applies only when enforced. Both are checked on every request, so a change to these settings applies to signed-in sessions at their next request, not only when they are renewed.

The idle timeout runs from the last time the session's tokens were refreshed, not from the last request: a client refreshes only when its access token has expired. So while the idle timeout is enforced, the access token lifetime must be shorter than it, and the settings are refused otherwise (for example, 60 minutes or more with a 1 hour idle timeout). Otherwise a user who is working could be signed out when the access token expires. A stored setting that already breaks this rule still loads; change either value to save. The deprecated `ACCESS_TOKEN_EXPIRE_MINUTES` and `SESSION_IDLE_TIMEOUT_HOURS` variables that would break it stop the start.

A session that is not used also ends when its refresh token expires (7 days by default). The defaults meet the NIST SP 800-63B reauthentication rule for AAL1: sign in again at least every 30 days. They do not meet AAL2, which asks for a new sign-in at least every 24 hours and after 1 hour of inactivity, even for accounts with MFA. To meet AAL2, set the absolute timeout to 24 hours or less and enforce an idle timeout of 1 hour or less. Users then sign in more often.

Every API key expires. A new key lasts the API key maximum lifetime unless its owner picks an earlier date, and a later date is refused. Changing the maximum does not shorten keys that already exist; lower it and review existing keys under each user's **Settings → Security**.

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

The image shown on the login page. Upload an image of up to 5 MB, ideally square. The settings page accepts PNG files; the API also accepts JPEG and WebP. Removing it restores the default. The photo is public because the login page needs it before anyone is signed in. See [Image personalization](../getting-started/advanced-setup.md#image-personalization).

### Email

| Setting | Meaning |
| ------- | ------- |
| Host and port | Your mail server. An empty host turns email off |
| Security | `starttls`, `ssl` or none. No encryption is allowed only for a private or loopback host, and not together with a username and password |
| Username and password | Credentials, if the server needs them. The password is write-only and stored encrypted |
| From address | The sender. If empty, the username is used. Some providers (Brevo, for example) require a verified sender that differs from the login |

Saving the email settings asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password), because a mail server you point Endurain at receives every password-reset link.

Use **Send test email** to check the settings: it sends a message to you straight away and shows the failure reason if it cannot. Email is used for sign-up verification, approval notices, password resets and the invitation an administrator's new account without a password sends. Without it those flows cannot send mail; see [Accounts, sign-up and password reset](accounts-and-sign-in.md).

When several replicas run, the email and geocoding settings are cached for a few seconds in each process, so a change reaches every replica quickly but not instantly.

### Server logs

A viewer of the newest application log records, with a minimum level, text search, download and clear. It is available only when a single process writes the log file, so it is hidden on the public demo and on multi-process deployments, where logs belong in your platform's log collection. See [Monitoring](../getting-started/monitoring.md).
