# COROS integration

Endurain connects to COROS through the official [COROS MCP server](https://mcp.coros.com/mcp)
and the standard OAuth 2.0 authorization-code flow. It imports activity FIT
files into the same pipeline used by file uploads, Strava and Garmin Connect.

The integration is read-only: Endurain reads activities and FIT files. It does
not create, change or delete anything in a COROS account.

## What Endurain supports

| Capability | Status |
| --- | --- |
| Connect and disconnect a COROS account | Yes |
| Import activities with a FIT file | Yes |
| GPS, heart rate, cadence, power, elevation and other recorded FIT metrics | Yes, when the device recorded them |
| Initial sync on connection | Yes, last 30 days |
| Incremental automatic sync | Yes, through Endurain's hourly provider refresh |
| Manual sync | Yes, last 7 days by default |
| Import an explicit date range | Yes, from the integration options |
| Deduplicate imported activities | Yes, by COROS activity id |
| Health, sleep, HRV, stress and recovery data | Not imported yet. The MCP server exposes these tools, but this integration only imports activities. |
| Training plans, workouts and schedules | Not imported yet |
| Gear, routes and GPX exchange | Not supported by the COROS MCP server used here |
| Webhooks or bidirectional sync | Not supported by the COROS MCP server |

An activity COROS cannot provide a FIT file for is recorded once and skipped
permanently, so it cannot consume the daily FIT quota on every sync. A file that
is present but fails to parse is retried after seven days.

## Configuration

No COROS-specific environment variable or developer application is required.
COROS registers Endurain as a public OAuth client dynamically (PKCE, no client
secret).

The integration uses these existing settings:

| Variable | Why it is needed |
| --- | --- |
| `ENDURAIN_HOST` | Builds the OAuth callback `{ENDURAIN_HOST}/coros/callback`. It must be the URL users open in their browser. HTTPS is required for COROS OAuth. |
| `FERNET_KEY` | Encrypts the COROS access token, refresh token and PKCE verifier at rest. |
| `SECRET_KEY` | Protects the authenticated session used when the browser returns from COROS. |

The requested scopes are exactly the ones COROS publishes on its authorization
server: `openid`, `offline_access` and `mcp.tools`.

The regional MCP endpoint and the OAuth endpoints are discovered from
`https://mcp.coros.com` at connection time. COROS may route the connection to
its Europe, United States or mainland China service.

## Connect a COROS account

1. Open **Settings → Integrations**.
2. Choose **Connect** on the COROS card.
3. Sign in to COROS and authorize Endurain.
4. COROS returns to `{ENDURAIN_HOST}/coros/callback`; Endurain validates the
   state, exchanges the code and stores the encrypted tokens.
5. An initial sync of the last 30 days is queued.

The COROS card then shows the connection, the last sync time, the last outcome
and a **Sync now** action.

Disconnecting revokes the stored tokens when COROS allows it and deletes them
locally. Activities already imported are kept.

## How synchronization works

- **Automatic:** the existing activity-ingestion scheduler queues one refresh
  per linked user every hour. Each refresh re-reads the last day.
- **Initial:** connecting an account queues a 30-day window.
- **Manual:** **Sync now** re-reads the last seven days to catch late uploads.
- **Backfill:** **Retrieve activities** accepts an explicit date range of up to
  366 days; older history can be imported in successive ranges.
- **Concurrency:** a per-user lock prevents two COROS syncs from running at the
  same time. A second request is skipped, not queued twice.
- **Idempotence:** an activity already stored for the user is skipped before any
  FIT download. The shared ingestion pipeline also enforces a unique dedup key,
  so a retry cannot create a duplicate.
- **Failures:** a transient network or COROS failure is recorded on the card and
  the job retry policy applies. An expired authorization asks you to reconnect.
- **Rate limits:** COROS allows 50 FIT file requests per user in a 24-hour
  window. Endurain counts them and stops cleanly when the limit is reached; the
  remaining activities are picked up on a later sync.

The refresh frequency is the shared hourly provider refresh. Endurain does not
expose a separate COROS interval setting.

## Data and security

- Access and refresh tokens, and the short-lived PKCE verifier, are encrypted
  with `FERNET_KEY`. They are never returned to the frontend and never written
  to logs.
- The OAuth `state` is generated with a cryptographically secure random value,
  stored against the user, expires after ten minutes and is required on the
  callback.
- The browser callback requires an authenticated Endurain session; a state that
  belongs to another user is refused.
- FIT downloads are size-capped, validated by the shared activity-file
  validator, and passed to the existing parser. A failed or corrupt file never
  deletes or replaces an existing activity.
- The fallback FIT download links are only fetched over HTTPS after the shared
  SSRF checks.

## Limitations

- COROS MCP is a single-user, read-oriented MCP surface. It does not provide
  webhooks, bidirectional activity sync or GPX routes.
- Only activities with a FIT file are imported. Health and training data are
  available through MCP but are not mapped into Endurain's health and workout
  models by this integration.
- If COROS revokes or expires the refresh token, the card asks you to reconnect.
- The COROS connection is not copied by the profile export/import feature, so a
  restored account must reconnect COROS.
- Regional routing is handled by COROS. If a server cannot reach the global
  gateway, the connection cannot be established.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| The card stays disconnected after authorizing | `ENDURAIN_HOST` must exactly match the URL used in the browser, including HTTPS and any reverse-proxy path. |
| “Authorization expired” | Reconnect COROS; the refresh token is no longer valid. |
| “The COROS MCP server no longer exposes the required activity tools” | COROS changed or withdrew a tool. Check the COROS MCP changelog before retrying. |
| No new activities after a sync | Confirm the activity exists in the COROS app and has synced to COROS's cloud. |
| Some activities never appear | They may have no FIT file. They are skipped and recorded once. |
| “Daily COROS FIT download limit was reached” | Wait for the next UTC day, then sync again. |
