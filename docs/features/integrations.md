# Integrations

Endurain works with other apps and services. For building your own integration, see the [Integrate](../integrate/authentication.md) section.

## RunnerUp

[RunnerUp](https://github.com/jonasoreland/runnerup), an app for tracking your sport activities with your Android phone, can automatically sync your activities recorded with it to your Endurain instance.

RunnerUp currently **does not** support login with MFA.

RunnerUp signs in through the first-party `/auth/login` route, which is meant for Endurain's own apps. A later release may refuse other applications there. [API keys](../integrate/api-keys.md) and the planned `/oauth/*` endpoints are the supported path for other applications; see the [first-party sign-in note](../integrate/authentication.md).

## Gadgetbridge

[Gadgetbridge](https://gadgetbridge.org/) is an Android app for wearables. It signs in to Endurain through the system browser using SSO and a custom redirect scheme. An administrator must allow its redirect address by adding it to `ALLOWED_REDIRECT_URIS` (`nodomain.freeyourgadget.gadgetbridge://endurain/oauth/callback` for the release build; other builds, such as nightly, use their own application ID as the scheme). Keep `com.endurain.endurain:/auth/sso/callback` in the list, and add `endurain://auth/sso/callback` until an Endurain mobile app release uses the new address, so the Endurain mobile app keeps working; see [advanced setup](../getting-started/advanced-setup.md) and [OAuth/SSO and PKCE](../integrate/oauth-sso-pkce.md).

The SSO hand-off through `ALLOWED_REDIRECT_URIS` is a first-party protocol for Endurain's own apps, and a later release may refuse other applications. [API keys](../integrate/api-keys.md) and the planned `/oauth/*` endpoints are the supported path for other applications; see the [first-party sign-in note](../integrate/authentication.md).

## Garmin Connect

Garmin Connect sync imports activities, gear and health data (body composition, daily steps and sleep). Endurain uses the [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) module.

### Connecting

Open **Settings → Integrations → Garmin Connect → Connect** and sign in with your Garmin Connect email or username and password. Tick the China option if your account is on connect.garmin.cn.

```mermaid
sequenceDiagram
    participant You
    participant E as Endurain
    participant G as Garmin Connect
    You->>E: Username and password
    E-->>You: Accepted, the login runs in the background
    E->>G: Sign in
    alt The account has MFA
        G-->>E: Code needed
        E-->>You: Ask for the authentication code
        You->>E: Code from your authenticator app or SMS
        E->>G: Code
    end
    G-->>E: Tokens
    E-->>You: Connected
```

- Endurain signs in through Garmin's unofficial login, because Garmin offers no public sign-in for this. Your password is relayed to Garmin once, for that sign-in, and is **never stored**. Endurain keeps the authentication tokens Garmin returns, encrypted, similar to the Strava integration. The login is sent from the browser to the server as plain text inside the request, so use HTTPS. Because it carries your Garmin password and MFA code, linking is limited to 10 attempts per minute, for the link request and for the MFA code alike.
- The login runs in the background, and the page follows its progress. Only one attempt per user can run at a time. A second one is refused until the first finishes.
- A failed attempt says why: wrong credentials, wrong MFA code, too many requests (wait a while) or an internal error.
- If Garmin later rejects the stored tokens, Endurain unlinks the account, sends you a [notification](notifications.md) and you connect again. Your imported data is kept.

### What syncs and when

| What | Automatically | On request |
| ---- | ------------- | ---------- |
| Activities | On startup and every hour, the last 24 hours | **Retrieve activities**, for the last N days or a date range |
| Health data | On startup and every 4 hours, the last day | **Retrieve health data**, for a range of at most 31 days |
| Gear | Never | **Retrieve gear** |

The buttons start a background job and return at once. A sync of a kind that is already pending is refused, and you can start only a few syncs per minute, because each one makes several calls to Garmin. Health data is imported as it is: Endurain does not calculate [sleep scores](sleep-scoring.md) for sleep that comes from Garmin Connect.

Duplicates are skipped by Garmin's activity id, so retrieving the same range twice is safe. See [Importing data](importing.md#duplicate-detection).

### Disconnecting

**Disconnect** removes the stored tokens and the gear sync setting. Everything already imported is kept.

## Strava

!!! warning
    Due to Strava API changes, expect changes in the Strava integration in a future release.

Strava needs an API application of your own, because Strava limits each application. Every Endurain user connects with their own application's client ID and secret.

### Before you connect

1. Your Endurain must be reachable from the internet over **HTTPS**, and `ENDURAIN_HOST` must be that public address. Strava sends your browser back to `ENDURAIN_HOST/strava/callback`.
2. Create an API application in your Strava settings (see Strava's [getting started guide](https://developers.strava.com/docs/getting-started/)). Set its **Authorization Callback Domain** to the host of your Endurain, for example `endurain.example.com`.
3. Copy the application's **Client ID** and **Client Secret**.

### Connecting

```mermaid
sequenceDiagram
    participant You
    participant E as Endurain
    participant S as Strava
    You->>E: Client ID and secret
    E-->>You: Stored encrypted, plus a one-time state value
    You->>S: Authorize Endurain (read-only scopes)
    S-->>You: Redirect to ENDURAIN_HOST/strava/callback with a code
    You->>E: The code and the state
    E->>S: Exchange the code for tokens
    S-->>E: Access and refresh tokens
    E-->>You: Connected
```

Open **Settings → Integrations → Strava → Connect**, enter the client ID and secret, and authorize on Strava. You return to Endurain, which finishes the connection. Endurain asks only for read access (`read`, `profile:read_all`, `activity:read_all`). Strava's consent screen lets you untick permissions: if you do, Endurain refuses the connection and asks you to connect again and keep every permission ticked. Connections made earlier are not affected. The tokens are stored encrypted, and so are your client ID and secret. If the exchange fails, Endurain keeps your client ID and secret and stores no tokens. Authorize on Strava again to retry: the code from the failed attempt is used up, but you do not need to enter the credentials again.

### What syncs and when

| What | Automatically | On request |
| ---- | ------------- | ---------- |
| Activities | On startup and every hour, the last 24 hours | **Retrieve activities**, for the last N days or a date range |
| Gear | Never | **Retrieve gear** |

Strava's rate limits are per application. When one is hit, Endurain stops calling Strava for every user of the server until it expires, and tells you to try again later. Duplicates are skipped by Strava's activity id. To bring in your whole history, use a [Strava bulk export](importing.md#importing-data-from-a-strava-bulk-export-beta) instead of syncing.

### Disconnecting

**Disconnect** first asks Strava to revoke Endurain's access, and goes ahead even if Strava cannot be reached. It then **deletes the gear and activities that were synced from Strava**, in line with Strava's [API Agreement](https://www.strava.com/legal/api). It also clears the stored tokens, client ID and secret. Activities from other sources, such as an upload, a [Strava bulk export](importing.md#importing-data-from-a-strava-bulk-export-beta) or Garmin Connect, stay.

!!! warning
    Disconnecting Strava cannot be undone. [Export your data](export-import.md) first if you want a copy of what was imported.

### When you revoke access on Strava

If you withdraw Endurain's access in your Strava settings, Endurain notices at the next sync. When Strava refuses the access token, Endurain tries once to refresh it. A token that has merely expired is refreshed and the sync carries on. If Strava refuses the refresh token, or refuses the new access token as well, access counts as revoked. Strava also refuses the refresh if the application's client secret changed, so check that before you reconnect. A refresh that fails for another reason, such as Strava being unreachable, changes nothing and is tried again at the next sync. Endurain then:

1. clears the stored tokens, keeps your client ID and secret and sends you a [notification](notifications.md) that gives the day your Strava-synced activities and gear will be deleted. The Strava card in **Settings → Integrations** shows the same dates;
2. keeps your data for 7 days. Connect Strava again within that time and nothing is deleted;
3. after the 7 days, deletes the activities and gear that were synced from Strava, as **Disconnect** does, and sends you a second notification. Endurain checks for due deletions every hour.

Only what the Strava API synced is deleted. Activities from your own [Strava bulk export](importing.md#importing-data-from-a-strava-bulk-export-beta) and from other sources stay, and so do your client ID and secret.

!!! note "Known gap"
    An activity you delete on Strava is not removed from Endurain. Strava's API Policy (section 6.3) asks for this within 48 hours, so delete the activity in Endurain as well.
