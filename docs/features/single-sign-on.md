# Single Sign-On (SSO) Configuration

Endurain supports Single Sign-On (SSO) integration through OAuth 2.0 and OpenID Connect (OIDC) protocols. This allows users to authenticate using their existing identity provider accounts.

## Important Notes

!!! warning "Email Address Matching"
    If you already have an existing Endurain account, the email address in your SSO provider **must match** your Endurain account email. If the email addresses don't match, Endurain will create a new user account with the SSO email address.

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
- **Grant Type**: `Authorization Code`
- **Scopes**: At minimum `openid profile email`

Save the generated **Client ID** and **Client Secret**.

### 2. Configure Endurain

1. Log into Endurain as an administrator
2. Navigate to **Settings** → **Identity Providers**
3. Click **Add Identity Provider**
4. Select your provider type or choose **Custom** for OIDC providers
5. Fill in the required fields (see table below)
6. Click **Save**

| Field | Description | Example |
| ----- | ----------- | ------- |
| **Provider Name** | Display name shown on login button | `Google`, `GitHub`, etc. |
| **Slug** | URL-safe identifier (lowercase, hyphens) | `google`, `github` |
| **Provider Type** | Protocol type | `OIDC` or `OAuth2` |
| **Issuer URL** | Provider's base URL (no trailing slash) | `https://accounts.google.com` |
| **Client ID** | OAuth client identifier | From Step 1 |
| **Client Secret** | OAuth client secret | From Step 1 |
| **Scopes** | Space-separated OAuth scopes | `openid profile email` |

### 3. Verify the Configuration

1. Log out of Endurain
2. Visit the login page
3. Verify that a **Sign in with `Provider Name`** button appears
4. Test the authentication flow

## Troubleshooting

### Common Issues

**Problem**: "Invalid redirect URI" error

- **Solution**: Ensure the callback URL in your identity provider matches exactly: `https://<your-domain>/api/v1/public/idp/callback/<slug>`

**Problem**: "Email address mismatch" creates duplicate account

- **Solution**: Update your existing Endurain account email to match your SSO provider email, or link the identity provider to your existing account

**Problem**: SSO button doesn't appear on login page

- **Solution**: 
    - Verify the identity provider is enabled in Endurain settings
    - Check if external authentication is enabled on server settings
    - Check that the provider configuration is saved correctly
    - Clear your browser cache and refresh the page

**Problem**: "Invalid issuer URL" error

- **Solution**: Ensure the Issuer URL does not have a trailing slash and is the correct base URL for your identity provider

### Logs

For detailed troubleshooting, check the Endurain backend logs:

```bash
docker logs endurain-backend
# and/or
tail -n 100 logs/app.log
```

Look for authentication-related errors that can help identify configuration issues.

## Security Considerations

!!! warning "Security Best Practices"
    - Always use **HTTPS** for both Endurain and your identity provider
    - Keep your **Client Secret** confidential and never commit it to version control
    - Regularly rotate client secrets
    - Use strong, randomly generated secrets
    - Limit OAuth scopes to only what's necessary (`openid profile email` is typically sufficient)
    - Monitor authentication logs for suspicious activity

## Additional Resources

- [Authentication Developer Guide](../developer-guide/authentication.md) - Technical details about Endurain's authentication system
- [Getting Started Guide](../getting-started/getting-started.md) - General setup instructions
- [OAuth 2.0 Specification](https://oauth.net/2/) - Official OAuth 2.0 documentation
- [OpenID Connect Specification](https://openid.net/connect/) - Official OIDC documentation
