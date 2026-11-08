# Accounts, sign-up and password reset

This page describes how an account is created, how a forgotten password is recovered, and how you secure your account. Administrators set the rules in [Server settings](server-settings.md); [user management](user-management.md) covers what they can do to accounts.

## Signing up

Sign-up is available only when an administrator has enabled it. The rules for new accounts are two independent switches:

| Switch | Effect |
| ------ | ------ |
| Require email verification | The new user must click a link sent to their address before they can sign in |
| Require admin approval | An administrator must approve the new user before they can sign in |

With neither switch on, the new account is active at once. With either on, it starts inactive.

```mermaid
flowchart TD
    A[User submits the sign-up form] --> B[Account created, inactive if any switch is on]
    B --> C{Email verification required?}
    C -- no --> F
    C -- yes --> D[Verification email, link valid 24 hours]
    D --> E[User opens the link]
    E --> F{Admin approval required?}
    F -- no --> G[Account active: user can sign in]
    F -- yes --> H[Admins get an email and a notification]
    H --> I[An admin approves the user]
    I --> J[User gets an approved email]
    J --> G
```

Details that matter:

- The form's response never reveals whether an email address is already registered. A sign-up with a registered address looks exactly like a successful one, and the address's owner gets an email saying that someone tried to sign up (when mail is configured, at most once an hour per account) and that nothing changed. A taken username is reported, because usernames are visible to every signed-in user. Changing your email address to one another account uses looks the same too: the address's holder gets an email saying that someone tried to use it, and nothing changes.
- Emails need a working mail server. Without one, verification and approval emails cannot be sent; configure it in [Server settings](server-settings.md#email).
- An administrator can only approve a user whose email is verified. If only admin approval is required, no verification email is sent, so the account stays unverified until an administrator marks the email verified in [user management](user-management.md#approving-sign-ups). Turn email verification on together with approval to avoid this.
- The verification link is valid for 24 hours. Endurain removes a sign-up that has not been verified once its link has expired, checked hourly, so the person signs up again. It keeps an account that has a password or a linked sign-in provider, one an administrator deactivated or queued for deletion, and one that has a valid link from a resend. An account that signed up with a password and awaits approval stays for an administrator to approve.
- A new account starts with default settings: privacy settings, health targets, empty default gear and integration slots.

## Signing in

You sign in with your username (or email) and password. Sign-in uses the address the account currently has, even while a change to a new address is waiting for confirmation. If your account has two-step verification, Endurain asks for a code as a second step. The step must be finished within five minutes, from the same network, and three wrong codes end it, so you sign in again. If an administrator set your password, Endurain then asks you to choose a new one before it signs you in; see [Password set by an administrator](user-management.md#password-set-by-an-administrator). If an administrator has enabled single sign-on, the login page also shows a button per identity provider; see [Single Sign-On](single-sign-on.md).

After repeated wrong passwords the account is locked for a while, with longer locks for more failures. Each client network counts separately (an IPv6 address by its /64), so one client cannot lock you out for everyone. If 100 wrong passwords in a row reach the account from any addresses, the account is locked for 30 days, except for browsers and apps you have signed in from before: they can still sign in with the right password. The count restarts when you sign in, and the lock ends when you sign in from a known device, complete a password reset, change your password from a signed-in device, or an administrator sets your password. You get an email and a notification when the account locks. The limits are in [Account security](../integrate/account-security.md#progressive-account-lockout).

## Forgotten password

On the login page choose the forgotten password link and enter your email.

```mermaid
sequenceDiagram
    participant U as You
    participant S as Server
    participant M as Your mailbox
    U->>S: Request a reset for your email
    S-->>U: Same answer whether or not the address exists
    S-->>M: Email with a reset link, if an active account has that address
    U->>S: Open the link and choose a new password
    S-->>U: Password changed
```

- The reset link is valid for one hour and works once. It is sent to the address the account currently has, not to a new address still waiting for confirmation.
- The answer on the page is always the same. This stops anyone from using the form to find out which emails have accounts.
- Inactive accounts (not yet verified or approved, or deactivated) get no email.
- Accounts without a local password (they sign in through an identity provider) get no email, and an already-issued reset link no longer works for them. An administrator can [set a password](user-management.md#resetting-a-password).
- When an administrator turned off [local username and password login](single-sign-on.md#auto-redirect-to-sso), resets and password sign-in are refused for regular users, answered like a wrong password. Administrators keep both.
- An account is emailed at most once every five minutes, so the form cannot be used to flood an inbox. A second request inside that time gets the same answer and no new email; use the link from the first one, or ask again afterwards.
- If the server has no mail configured, the request is answered with a "service unavailable" error. Ask an administrator to reset the password in [user management](user-management.md#resetting-a-password).
- The new password must satisfy the server's password policy.

## Password rules

Passwords follow [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): length matters, character mixes do not. A new password must:

- be at least as long as the minimum an administrator set for the account type, 15 characters by default (8 to 128). Every character counts, including spaces and non-Latin letters;
- not be a commonly used or breached password. Endurain checks it against a list of about 75,000 such passwords shipped with the server, ignoring case;
- not be the account's username, email address, the part of the email before the `@`, or "endurain".

No upper-case letters, digits or symbols are required. The form shows a strength meter as a guide; only the rules above can refuse a password, and the message says which one. Passwords are compared in Unicode NFC form, so the same text typed on different devices is the same password. Existing passwords keep working when the rules change; the rules apply the next time a password is set.

## Securing your account

Under **Settings → Security** you can:

- change your password and email. Both ask you to confirm with your current password, and with a code if two-step verification is on. A new email takes effect when you follow the link sent to it, valid for 24 hours. Until then your current address stays in place, and Settings shows the pending address with buttons to resend the link or cancel the change. Once the change is confirmed, the previous address gets a notice. If the server has no mail configured, a new email takes effect at once, unverified;
- turn two-step verification (a TOTP authenticator app) on or off, and regenerate its ten one-time backup codes. Each code has the form `XXXX-XXXX` and works once, and generating new ones invalidates the old;
- see your signed-in sessions and sign out of any of them or all the others;
- link or unlink identity providers;
- create and revoke [API keys](../integrate/api-keys.md), which can upload activities and always expire, after at most the lifetime the administrator allows (365 days by default);
- delete your account.

Changing your password, turning two-step verification on or off, regenerating its backup codes or linking an identity provider signs you out of your other devices, and keeps the one you are using. Each of these forms has a switch, **Sign out of all other devices**, which is on by default; turn it off to keep your other sessions. Changing your email has the same switch, off by default.

Accounts that sign in only through single sign-on have no local password. They cannot change a password themselves, and they confirm sensitive changes by signing in again with their identity provider; see [Single Sign-On](single-sign-on.md#confirming-sensitive-changes-without-a-password).

Deleting an account signs you out at once and deletes its data in the background, including activities, photos, thumbnails and stored files. The request answers `202` and there is no progress to follow: the account is already signed out and deactivated, so you cannot check it, and an administrator can follow the job with `GET /users/{user_id}/deletion`. How long it takes depends on how many activities the account has. If it fails, Endurain queues it again every hour, up to five times; see [Background operations](../integrate/background-operations.md#delete-your-account). The only administrator of a server cannot delete or demote themselves; make another user an administrator first.

### Security notifications

Endurain tells you when the way you sign in changes: your password is changed, reset, or set by an administrator; your account is locked by 100 wrong passwords in a row; two-step verification is turned on or off; new backup codes are generated; an API key is created; or an identity provider is linked or unlinked. You get an email at your current address, if the server has mail configured, and a notification in the app. If you did not make the change, reset your password and review **Settings → Security**, or contact your administrator for a change made by one.

The email is the notice that counts: someone who has taken over a session can read and dismiss in-app notifications, but not your mailbox.

Signing in from a new device sends the same pair of notices: when it happened, the browser and operating system, the IP address, and whether you used your password or a sign-in provider. If it was not you, change your password and sign out of your other sessions in **Settings → Security**.

- **Web:** Endurain recognises a browser by a random id it keeps in an `endurain_device` cookie (`__Secure-endurain_device` when the server runs in production or demo; HttpOnly, `SameSite=Strict`, sent only to the API, kept for 400 days from the last sign-in). The server stores only a hash of it. Signing in again from a browser you have used before sends nothing. A browser without the cookie, after clearing cookies or in a private window, counts as new. A device unused for 400 days is forgotten.
- **First device:** the first device of an account created in the last 24 hours gets no notice. Any other first device does: an account that never signed in, or whose devices were all forgotten after 400 days. After upgrading to this version, a user's first sign-in within 24 hours of the upgrade is not announced, so existing users are not all emailed at once; a later one is.
- **Mobile app:** the app keeps a device id the server gave it and sends it as `X-Device-Id`; it behaves like the web cookie. An app that has no id yet, after a reinstall or a cleared storage, counts as new and is given one.
- **Locked account:** a known device can still sign in while the account is locked by 100 wrong passwords in a row; see [Signing in](#signing-in).
