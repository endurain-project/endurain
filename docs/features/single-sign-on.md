# Single Sign-On (SSO) Configuration

Endurain supports Single Sign-On (SSO) integration through OAuth 2.0 and OpenID Connect (OIDC) protocols. This allows users to authenticate using their existing identity provider accounts.

## Important Notes

!!! warning "Email Address Matching"
    A provider signs a user in to an existing Endurain account only through a link. Switch on **Link by email** on the provider and an unlinked sign-in joins the account whose email matches the provider's verified email. With it off (the default for a new provider), that sign-in is refused: the user signs in locally and links the provider from **Settings → Security**. If no account has the provider's email, Endurain creates a new user (when **Auto-create users** is on).

!!! tip "Requirements"
    You'll need:
    
    - The fully qualified domain name (FQDN) of your OIDC provider
    - The FQDN of your Endurain installation
    - Administrator access to both your identity provider and Endurain

## Supported Identity Providers

Endurain provides built-in support for the following identity providers:

- **Authelia**
- **Authentik**
- **Casdoor**
- **Keycloak**
- **Pocket ID**

The system also supports custom OIDC providers including:

- Google
- GitHub
- Microsoft Entra ID
- Any other OIDC-compliant provider

## Configuration Examples

### Pocket ID

Pocket ID is a lightweight, self-hosted identity provider that works seamlessly with Endurain.

#### Step 1: Configure Pocket ID

1. Log into your Pocket ID instance
2. Navigate to **Administration** → **OIDC Clients**
3. Select **Add OIDC client**
4. Configure the following settings:
    - **Name**: `Endurain`
    - **Client Launch URL**: Your Endurain FQDN (e.g., `https://endurain.mydomain.com`)
    - **Callback URLs**: `https://endurain.mydomain.com/api/v1/public/idp/callback/pocket-id`
    - **Logout Callback URLs**: `https://endurain.mydomain.com/login`
5. Click **Save**
6. **Important**: Make a note of your **Client ID** and **Client Secret**

#### Step 2: Configure Endurain

1. Log into your Endurain instance
2. Navigate to **Settings** → **Identity Providers**
3. Select **Add Identity Provider** → **Select Pocket ID**
4. Configure the following settings:
    - **Provider Name**: `Pocket ID`
    - **Slug**: `pocket-id`
    - **Provider Type**: `OIDC`
    - **Issuer URL**: Your Pocket ID FQDN (e.g., `https://pocketid.mydomain.com`) - **no trailing slash**
    - **Client ID**: The Client ID from Step 1
    - **Client Secret**: The Client Secret from Step 1
    - **Scopes**: `openid profile email`
5. Click **Save**

#### Step 3: Test the Integration

1. Log out of Endurain
2. On the login page, you should see a **Sign in with Pocket ID** button
3. Click the button to test the SSO flow

---

### Tailscale TSIDP

Tailscale's identity provider (TSIDP) can be used for secure authentication within your Tailscale network.

#### Step 1: Configure TSIDP

1. Log into your TSIDP instance
2. Select **Add new client**
3. Configure the following settings:
    - **Client Name**: `Endurain`
    - **Redirect URIs**: `https://endurain.mydomain.com/api/v1/public/idp/callback/tsidp`
4. Click **Create client**
5. **Important**: Make a note of your **Client ID** and **Client Secret**

#### Step 2: Configure Endurain

1. Log into your Endurain instance
2. Navigate to **Settings** → **Identity Providers**
3. Select **Add Identity Provider** → **Custom**
4. Configure the following settings:
    - **Provider Name**: `TSIDP`
    - **Slug**: `tsidp`
    - **Provider Type**: `OIDC`
    - **Issuer URL**: Your TSIDP FQDN (e.g., `https://tsidp.mydomain.com`) - **no trailing slash**
    - **Client ID**: The Client ID from Step 1
    - **Client Secret**: The Client Secret from Step 1
    - **Scopes**: `openid profile email`
5. Click **Save**

#### Step 3: Test the Integration

1. Log out of Endurain
2. On the login page, you should see a **Sign in with TSIDP** button
3. Click the button to test the SSO flow

---

## General Configuration Steps

For any OIDC-compliant identity provider, follow these general steps:

### 1. Configure Your Identity Provider

Create an OAuth 2.0/OIDC client application with the following settings:

- **Application Name**: `Endurain`
- **Redirect/Callback URI**: `https://<your-endurain-domain>/api/v1/public/idp/callback/<slug>`
- **Post-logout redirect URI**: `https://<your-endurain-domain>/login` (the value of `ENDURAIN_HOST` followed by `/login`), so the provider can send the browser back to Endurain after it ends its session. Providers that require registered post-logout URIs refuse the sign-out redirect without it.
- **Grant Type**: `Authorization Code`
- **Scopes**: At minimum `openid profile email`

Save the generated **Client ID** and **Client Secret**.

### 2. Configure Endurain

1. Log into Endurain as an administrator
2. Navigate to **Settings** → **Identity Providers**
3. Click **Add Identity Provider**
4. Select your provider type or choose **Custom** for OIDC providers
5. Fill in the required fields (see table below)
6. Click **Save**. Adding or editing a provider asks for your own password and MFA code first (or a fresh sign-in with a provider linked to your account, if you have no password), because a rogue provider can claim accounts.

| Field | Description | Example |
| ----- | ----------- | ------- |
| **Provider Name** | Display name shown on login button | `Google`, `GitHub`, etc. |
| **Slug** | URL-safe identifier (lowercase, hyphens) | `google`, `github` |
| **Provider Type** | Protocol type: `OIDC` (the default) or `OAuth2`. An `OAuth2` provider whose scopes include `openid` issues an ID token, so its sign-in must carry a verified ID token and needs an issuer URL, like an `OIDC` one. Without `openid` the provider is identified by its userinfo endpoint alone | `OIDC` or `OAuth2` |
| **Issuer URL** | Provider's issuer URL, exactly as the `issuer` in its `/.well-known/openid-configuration` document; a trailing slash is ignored. Another provider cannot use the same issuer, and the issuer cannot change while any user is linked to the provider | `https://accounts.google.com` |
| **Client ID** | OAuth client identifier | From Step 1 |
| **Client Secret** | OAuth client secret | From Step 1 |
| **Scopes** | Space-separated OAuth scopes | `openid profile email` |
| **Icon** | Logo on the login button: a built-in logo or an uploaded image | `Keycloak`, `Upload an image` |
| **Auto-create users** | Create an account at the first sign-in of someone no account matches. Off refuses that sign-in | On by default |
| **Link by email** | Join an unlinked sign-in to the existing account whose email equals the provider's verified email. Off refuses that sign-in and the user links the provider from **Settings → Security** | Off for a new provider |
| **Sync user info** | At each sign-in, copy the mapped name from the provider. It does not include the email | On by default |
| **Sync email** | At each sign-in, copy the email the provider verified onto the account | Off for a new provider |

#### Changing a provider's issuer

A user's link names the provider and the user's identifier at it, so the issuer is what keeps a link pointing at the same identity provider. For that reason:

- The issuer URL cannot be changed, set or cleared while any user is linked to the provider. Unlink those users first, or add a new provider for the new issuer. Adding or removing only a trailing slash is not a change.
- Two providers cannot use the same issuer URL (a trailing slash is ignored). A provider with no issuer URL never conflicts.

Both refusals are answered with `409` and nothing is saved.

#### Linking by email and syncing the email

Both switches act on an email address, so both are off for a new provider: turn them on only for a provider whose email addresses you trust.

- **Link by email** needs the provider to assert the email as verified (the standard `email_verified` claim on the `email` claim) and the existing account's email to be verified too. A sign-in refused because the switch is off is recorded in the audit trail and the login page tells the user to sign in locally and link the provider from their settings.
- **Sync email** replaces the account's email with the one the provider verified, unless another account already uses it. The new address counts as verified, unused password-reset links are voided, the change is recorded in the audit trail and the previous address is sent a notice.
- **Upgrading.** A provider that existed before this setting keeps what it did: **Link by email** is on, and **Sync email** is on exactly when **Sync user info** was on.

#### HTTPS and private networks

- Every provider URL must use `https://`: the issuer and any endpoint you enter, and the endpoints the provider's discovery document lists. Endurain checks this when you save the provider and before every call to it.
- A provider on a private network, or one served over plain `http://`, must have its host listed in [`SSRF_ALLOWED_HOSTS`](../getting-started/advanced-setup.md). Plain `http://` is accepted only for a listed host.
- Saving a provider applies the change at once. When the provider rotates its signing keys, Endurain fetches the new keys on the next sign-in.

#### Choosing an icon

- **Built-in logos** exist for Authelia, Authentik, Casdoor, Keycloak and Pocket ID.
- **Upload an image** stores a JPEG, PNG or WebP file of up to 1 MB in Endurain and serves it from your own server. SVG files are not accepted.
- The icon cannot point at an image on another host: the browser's Content-Security-Policy would block it, and every visitor's browser would contact that host.
- The uploaded image is public: the login page shows it to everyone who visits it.

### 3. Verify the Configuration

1. Log out of Endurain
2. Visit the login page
3. Verify that a **Sign in with `Provider Name`** button appears
4. Test the authentication flow

## What Endurain does with the provider's tokens

Each time you sign in through a provider, Endurain keeps the refresh token the provider issued for that sign-in, encrypted, together with the Endurain session it created. A second device signed in through the same provider has its own token. Linking a provider to an existing account does not sign you in, so it stores no token.

- **Refreshing.** The token is renewed in the background as your Endurain session is refreshed, never during a request. If the provider is unreachable or fails, the token is kept and the next refresh tries again.
- **A refused refresh ends that sign-in.** When the provider refuses the refresh token (for example because you were removed from the provider or revoked the application there), Endurain signs out that one session and records it in the audit trail. Your other sessions are not affected. A token that Endurain can no longer decrypt, such as after a lost encryption key, is dropped without ending the session.
- **Signing out revokes the token.** Signing out, revoking a session, changing or resetting the password, deactivating the account and a detected refresh-token reuse all end Endurain sessions. For each one Endurain asks the provider to revoke the session's refresh token ([RFC 7009](https://datatracker.ietf.org/doc/html/rfc7009)), when the provider advertises a `revocation_endpoint` in its discovery document, and then forgets it. A provider without one is not asked. If the provider cannot be reached, Endurain tries again every 15 minutes. Sessions that simply expire are handled by the same job.
- **Signing out at Endurain also signs out at the provider.** When the provider advertises an `end_session_endpoint` ([OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)), signing out in the web app sends the browser to the provider with the ID token Endurain kept for that sign-in, so the provider ends its own session and returns to the Endurain login page. Endurain stores that ID token encrypted with the session's refresh token and deletes it with the sign-in. A provider without an `end_session_endpoint` is not asked, and if the provider cannot be reached for it, signing out at Endurain still succeeds and the provider session stays. A session from before this behaviour has no ID token and signs out of Endurain only.
- **Unlinking a provider signs out its sessions.** Unlinking a provider, yourself or as an administrator, ends every session of that user that signed in through it, including your current one when it did, and revokes their tokens.
- **Sessions from before the upgrade** are ended by it: upgrading to v0.21 signs everyone out once, so every session after it holds its own provider token.

Deleting an account, or an identity provider, removes the stored tokens with it without asking the provider to revoke them.

## Accounts with MFA enabled

Signing in through your identity provider does not replace the multi-factor authentication you set up in Endurain. If your account has MFA enabled, Endurain asks for your authentication code (or a backup code) after the provider signs you in, and only then finishes the login. Wrong codes count toward the same lockout as the password login. Accounts without MFA sign in as before.

## Confirming sensitive changes without a password

An account that signs in only through an identity provider has no local password. To create an API key, link or unlink a provider, change the email, delete the account, export your data, or turn MFA on or off or regenerate its backup codes, Endurain sends you back to your provider to sign in again. The provider must show that you signed in within the last 60 seconds and must be one already linked to your account; if it reuses an existing provider session, Endurain refuses with a "not fresh" error. If MFA is on you also enter your code, and a wrong code does not force a new provider sign-in. MFA alone is not enough.

These accounts cannot change their password themselves. An administrator sets one in [user management](user-management.md#resetting-a-password).

This needs the provider to be configured with an issuer URL, so Endurain can use OIDC discovery and the signing keys. OAuth2-only providers cannot confirm sensitive changes. Native and mobile apps cannot do it either; use the web interface.

| Provider | Notes |
| -------- | ----- |
| Keycloak | Assign the `basic` client scope so `auth_time` is in the ID token |
| authentik | Works with `max_age`; `prompt=login` alone is unreliable |
| Authelia | Supported |
| Pocket ID | Version 2.10.0 or later |
| Casdoor | Version 4.24.0 or later |

If your provider cannot prove a fresh sign-in, an administrator sets a local password for you. Keep at least one administrator account with a local password: an administrator cannot reset their own password through the admin route, so create it before relying only on SSO.

Linking an identity provider asks you to confirm with your password (or a fresh provider sign-in) and MFA code first, then sends you to the provider; the browser that started the link must be the one that finishes it. When the link completes, Endurain signs you out of your other devices and keeps the one that started the link, unless you turned off **Sign out of all other devices** in that form. It sends a notification to the account.

## Usernames of new accounts

When Endurain creates an account at the first sign-in, it never builds the username from the email address, because usernames are visible to other signed-in users. A username claim from the provider (`preferred_username` or `username` by default) is used when it only has letters, digits, dots, hyphens and underscores. A claim that contains `@`, such as an email address or an Entra ID user principal name, is not used. Any other claim has each run of unsupported characters replaced by `_` and leading and trailing `.`, `-` and `_` removed. When nothing usable is left, as with Google, which sends no `preferred_username`, the username is `user_` followed by the first eight characters of the provider's subject identifier. If the name is already taken, Endurain appends `_` and six digits. Users can change their username afterwards, and later sign-ins never change it.

## Auto-redirect to SSO

Under **Settings → Server Settings**, the **Auto-redirect to SSO** option skips the login page's provider picker and immediately sends unauthenticated users to your identity provider. It only takes effect when:

- **SSO** is enabled and one identity provider is configured/enabled
- **Allow local username and password login** is turned **off**

If **Allow local username and password login** is enabled, the auto-redirect is skipped and the login page is shown as usual (with both the local form and SSO buttons available).

!!! tip "Bypassing auto-redirect"
    If you ever need to reach the local username/password form while auto-redirect is enabled (for example, if your identity provider is unreachable), append `?forceLocalLogin=true` to the Endurain URL, e.g. `https://endurain.mydomain.com/?forceLocalLogin=true`. This shows the local login form for that attempt and suppresses the automatic redirect. It does **not** disable the auto-redirect setting itself, it only applies to the current page load.

    With **Allow local username and password login** off, only administrators can sign in with a password, so an administrator is the way back in when the provider is down. Other accounts are refused as if the password were wrong.

## Troubleshooting

### Common Issues

**Problem**: "Invalid redirect URI" error

- **Solution**: Ensure the callback URL in your identity provider matches exactly: `https://<your-domain>/api/v1/public/idp/callback/<slug>`

**Problem**: "Email address mismatch" creates duplicate account

- **Solution**: Update your existing Endurain account email to match your SSO provider email, or link the identity provider to your existing account

**Problem**: A sign-in is refused with "Cannot link this identity provider to an existing account because the provider does not link by email" (HTTP 403, the login page shows a message)

- **Cause**: An account already has the provider's email, and **Link by email** is off for this provider.
- **Solution**: Sign in with your password, link the provider from **Settings → Security**, or ask an administrator to switch on **Link by email** for the provider.

**Problem**: "Cannot link this identity provider to an existing account because the provider did not verify the email address" (HTTP 403)

- **Cause**: For security (account-takeover prevention), Endurain, for a provider with **Link by email** on, auto-links an SSO identity to an **existing** local account by email only when the identity provider asserts the email is verified via the standard OIDC `email_verified` claim. `email_verified` describes only the standard `email` claim, so an address taken from `mail` (the Authentik and Keycloak templates map `email` first and fall back to `mail`, so they link only when the provider sends `email`) or from a custom claim mapping is never treated as verified and is refused too. Providers that omit the flag, or report the email as unverified, are refused.
- **Solution**: Configure the identity provider to verify email addresses and send the address in the `email` claim with `email_verified: true` in the userinfo/ID token (request the `email` scope), or link the provider from **Settings → Security** while signed in to the existing account.

**Problem**: "Cannot link this identity provider to an existing account because the account email is not verified" (HTTP 403)

- **Cause**: Endurain also requires the existing local account's email to be verified before it auto-links an SSO identity by email, because an unverified address can be set by anyone on their own account.
- **Solution**: Verify the email address of the existing account, then sign in with SSO again.

**Problem**: SSO button doesn't appear on login page

- **Solution**: 
    - Verify the identity provider is enabled in Endurain settings
    - Check if external authentication is enabled on server settings
    - Check that the provider configuration is saved correctly
    - Clear your browser cache and refresh the page

**Problem**: Automatically redirected to the identity provider and can't reach the local login form (e.g. the identity provider is down)

- **Cause**: **Auto-redirect to SSO** is enabled and **Allow local username and password login** is disabled.
- **Solution**: Visit the login page with `?forceLocalLogin=true` appended, e.g. `https://endurain.mydomain.com/?forceLocalLogin=true`. See [Auto-redirect to SSO](#auto-redirect-to-sso) above.

**Problem**: "The provider URL was refused" when saving a provider

- **Cause**: A URL uses plain `http://`, does not resolve from the Endurain server, or resolves to a private address, and its host is not in `SSRF_ALLOWED_HOSTS`.
- **Solution**: Use the provider's `https://` URL. For a provider on a private network, add its host or CIDR to `SSRF_ALLOWED_HOSTS`. See [HTTPS and private networks](#https-and-private-networks).

**Problem**: SSO sign-in fails and the log shows "OIDC discovery document for ... names issuer ..., expected ..."

- **Cause**: The provider's discovery document names a different issuer than the configured **Issuer URL**, so Endurain does not trust it.
- **Solution**: Set the **Issuer URL** to the `issuer` value from `https://<your-provider>/.well-known/openid-configuration`.

### Logs

For detailed troubleshooting, check the Endurain backend logs:

```bash
docker logs endurain-app
# and/or
tail -n 100 logs/app.log
```

Look for authentication-related errors that can help identify configuration issues.

## Security Considerations

!!! warning "Security Best Practices"
    - Always use **HTTPS** for Endurain. Endurain requires it for your identity provider unless the provider's host is in `SSRF_ALLOWED_HOSTS`
    - Keep your **Client Secret** confidential and never commit it to version control
    - Regularly rotate client secrets
    - Use strong, randomly generated secrets
    - Limit OAuth scopes to only what's necessary (`openid profile email` is typically sufficient)
    - Monitor authentication logs for suspicious activity

## Additional Resources

- [Authentication Developer Guide](../integrate/authentication.md) - Technical details about Endurain's authentication system
- [Getting Started Guide](../getting-started/quick-start.md) - General setup instructions
- [OAuth 2.0 Specification](https://oauth.net/2/) - Official OAuth 2.0 documentation
- [OpenID Connect Specification](https://openid.net/connect/) - Official OIDC documentation
