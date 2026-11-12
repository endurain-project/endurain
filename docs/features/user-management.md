# User management

Administrators manage accounts in **Settings → Users**. The page lists every account on the instance, with badges for administrators, inactive accounts, accounts with an unverified email, accounts waiting for approval and accounts that sign in through an external provider.

## Finding users

Search by username, and filter the list by:

- inactive users,
- users whose email is unverified (a sign-up that never verified is removed after its 24-hour link expires; see [Accounts and sign-in](accounts-and-sign-in.md)),
- users pending approval,
- users who sign in through an external provider,
- users who sign in with a local password.

## Adding a user

**Add user** creates an account with a name, username, email and access type (regular user or administrator). When the server has [email configured](server-settings.md), the form defaults to **Email an invitation to choose a password**: the account is created active with no password, and Endurain emails the user, in their language, a message saying an administrator created the account with a link, valid for 24 hours, to choose their own password. Choosing it also marks their email verified, and it works while sign-up is turned off. Until then the account cannot sign in. If the link expires unused, set a password with **Reset password**, which a password reset email cannot do for an account that has none. The invitation needs an active account and mail; without mail, or by choosing **Set a password now**, you set the password instead. It must satisfy the [password policy](accounts-and-sign-in.md#password-rules), and because you know it, the user has to [choose a new one at their next sign-in](#password-set-by-an-administrator). Creating an administrator asks for your own password and MFA code first; creating a regular user does not. A new account starts with the default settings every account gets.

## Editing a user

Edit a user's profile fields, access type and whether the account is active. You can also upload or remove their photo.

Changing a user's email sends a confirmation link to the new address. The user's current address gets a notice at once, without a link, that an administrator asked for the change. The address changes when the user follows the link, which is valid for 24 hours. Until then the user keeps signing in and resetting their password with the current address, and the user's detail page shows the pending address and when its link expires. To apply the new address at once, switch on **Mark the new address as verified** in the edit form. The address is then marked verified and no link is sent, and the previous address gets a notice that the account's email changed. If the server has no mail configured, the address changes at once and stays unverified. A deactivated account stays deactivated when its user follows a confirmation link: the link changes and verifies the address, and only an administrator reactivates the account.

Changing a user's email, access type or active flag asks for your own password (or a fresh identity-provider sign-in if your account has none) and your MFA code when MFA is on, so a stolen session cannot hand an account over. Other edits need no confirmation.

Some edits end the user's sessions, so a session issued under the old values cannot outlive the change. The user is signed out of every device when you save a change to their:

- email, even while the new address waits for confirmation,
- access type,
- active flag.

Endurain always keeps at least one active administrator. You cannot delete, deactivate or demote the only active administrator; make someone else an administrator first.

Changing another user's access type or deactivating their account tells that user, by email and by a notification in the app (see [Security notifications](accounts-and-sign-in.md#security-notifications)). Making a user an administrator also tells every other active administrator, naming the user. Editing your own account sends neither.

## Your own account

The administrative actions that change how an account is secured, resetting the password, requiring a password change, resetting MFA, unlinking an identity provider, deleting the account and changing the email, are refused for your own account (`403`). Use your own account settings instead, which ask for your current password and MFA code first. The same actions on another user's account ask for your own password and MFA code too.

## Approving sign-ups

When [admin approval](server-settings.md#registration) is required, a new user stays inactive and shows the **Pending approval** badge. Every administrator gets a [notification](notifications.md) (and an email, if mail is configured) when a user is waiting.

Approve the user from their row. Endurain activates the account and emails the user. You can approve only a user whose email is verified; a user who has not verified it yet stays pending.

!!! note "Approval without email verification"
    A new account is created with an unverified email whenever any sign-up rule is on. If you require approval but not email verification, nobody sends the user a verification link, so the **Approve** and reject buttons stay disabled. To handle such a user, open **Edit user**, switch on **Email verified** and save, then approve. Turning on **Require email verification** as well avoids this.

## Resetting a password

**Reset password** sets a new password for the user without needing their current one. It must satisfy the password policy. Endurain revokes the user's sessions, unused reset links, pending email change and API keys, so they must sign in again with the new password and create new keys. Use this when a user cannot receive the [reset email](accounts-and-sign-in.md#forgotten-password), for example because no mail server is configured. It is also how an account that has no local password gets one: such an account cannot set its own. It asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password). An administrator cannot reset their own password here.

### Password set by an administrator

A password an administrator sets, whether with **Reset password** or when adding the user, is known to the administrator, so the user must change it at their next sign-in. After the right password (and the MFA code, if the account has MFA), sign-in asks for a new password and its confirmation. The new password must satisfy the [password policy](accounts-and-sign-in.md#password-rules) and differ from the one the administrator set; a rejected password can be replaced without signing in again. No session exists until the new password is saved, and the user is then signed in. The challenge for choosing the password expires after 10 minutes; after that the user signs in again. Single sign-on does not use the password, so signing in through an identity provider is not affected. A password the user chooses themselves, by changing it in **Settings → Security**, through a reset email or when confirming a sign-up, never asks for another change. The first administrator, who chooses a password during setup, is not asked either.

## Requiring a password change

**Require password change** makes the user choose a new password at their next password sign-in, without setting one for them: the current password stays valid until then, and the sign-in step is the one described under [password set by an administrator](#password-set-by-an-administrator). All of the user's sessions end, so they are signed out of every device, and they are notified by email and in the app. It asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password). It is refused for an account that has no local password, and for your own account. Single sign-on does not use the password, so signing in through an identity provider is not affected.

## Resetting MFA

**Reset MFA** turns off two-factor authentication for a user who cannot use their authenticator or backup codes. It removes the user's MFA secret and backup codes, ends all of their sessions and notifies them by email and in the app. The button only shows for a user who has MFA on. The user can set up MFA again from **Settings → Security** after signing in. It asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password), and is refused for your own account.

## Sessions and identity providers

A user's detail page shows their sessions, which you can revoke, and the identity providers linked to the account, which you can unlink. Revoking one session or all of them asks for your own password and MFA code, as ending a session locks the user out. Unlinking an identity provider removes that external sign-in. Unlinking asks for your own password and MFA code. Check that the user has another way to sign in first.

## API keys

A user's detail page lists their [API keys](../integrate/api-keys.md), which you can revoke one at a time or all at once. Revoking asks for your own password and MFA code, as it cuts off the integrations that use the keys. A revoked key stops working at once, and the user gets an email and a notification that an administrator revoked keys of their account. You see the keys' names, prefixes, scopes and dates, never a key itself.

## Deleting a user

Deleting a user asks for your own password and MFA code (or a fresh identity-provider sign-in if your account has no password). It deletes the account and everything it owns: activities, their laps, streams, photos, thumbnails and stored source files, gear, health records, goals, notifications and the profile photo. The user is signed out and deactivated at once, and a background job erases their data, so a large account does not hold up the server; the request answers `202` with the deletion job, which `GET /jobs/{job_id}` reports on for any administrator. If the job fails, the account stays deactivated and signed out, and Endurain queues the deletion again every hour, up to five times. After that, delete the account again yourself. Reactivating the account cancels a deletion that has not finished. There is no grace period, and once the job finishes the data cannot be recovered, so ask users to [export their data](export-import.md) first if they want a copy. When the erasure starts, the job emails the account's owner at the address on the account, if the server has mail configured. It is an email only, with no in-app notification, since the account is erased; it is sent once, not again when Endurain queues the deletion again, and a failure to send it does not stop the deletion.

## For the person editing at the same time

If two administrators edit the same user at once, the second save is refused with a message that the user changed, and nothing is overwritten. Reload and apply the change again. API clients see `412`; see [Errors, concurrency and rate limits](../integrate/errors-and-limits.md#concurrent-edits-with-etag-and-if-match).
