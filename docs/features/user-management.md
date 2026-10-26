# User management

Administrators manage accounts in **Settings → Users**. The page lists every account on the instance, with badges for administrators, inactive accounts, accounts with an unverified email, accounts waiting for approval and accounts that sign in through an external provider.

## Finding users

Search by username, and filter the list by:

- inactive users,
- users whose email is unverified,
- users pending approval,
- users who sign in through an external provider,
- users who sign in with a local password.

## Adding a user

**Add user** creates an account with a name, username, email, access type (regular user or administrator) and a password. The password must satisfy the [password policy](accounts-and-sign-in.md#password-rules). A new account starts with the default settings every account gets.

## Editing a user

Edit a user's profile fields, access type and whether the account is active. You can also upload or remove their photo.

Some edits end the user's sessions, so a session issued under the old values cannot outlive the change. The user is signed out of every device when you change their:

- email (the new address is also marked unverified),
- access type,
- active flag.

Endurain always keeps at least one active administrator. You cannot delete, deactivate or demote the only active administrator; make someone else an administrator first.

## Approving sign-ups

When [admin approval](server-settings.md#registration) is required, a new user stays inactive and shows the **Pending approval** badge. Every administrator gets a [notification](notifications.md) (and an email, if mail is configured) when a user is waiting.

Approve the user from their row. Endurain activates the account and emails the user. You can approve only a user whose email is verified; a user who has not verified it yet stays pending.

!!! note "Approval without email verification"
    A new account is created with an unverified email whenever any sign-up rule is on. If you require approval but not email verification, nobody sends the user a verification link, so the **Approve** and reject buttons stay disabled. To handle such a user, open **Edit user**, switch on **Email verified** and save, then approve. Turning on **Require email verification** as well avoids this.

## Resetting a password

**Reset password** sets a new password for the user without needing their current one. It must satisfy the password policy. Endurain revokes the user's sessions and other sign-in state, so they must sign in again with the new password. Use this when a user cannot receive the [reset email](accounts-and-sign-in.md#forgotten-password), for example because no mail server is configured.

## Sessions and identity providers

A user's detail page shows their sessions, which you can revoke, and the identity providers linked to the account, which you can unlink. Unlinking an identity provider removes that external sign-in. Check that the user has another way to sign in first.

## Deleting a user

Deleting a user deletes the account and everything it owns: activities, their laps, streams, photos, thumbnails and stored source files, gear, health records, goals, notifications and the profile photo. This is done in one step, so an account is never left half deleted. It cannot be undone, so ask users to [export their data](export-import.md) first if they want a copy.

## For the person editing at the same time

If two administrators edit the same user at once, the second save is refused with a message that the user changed, and nothing is overwritten. Reload and apply the change again. API clients see `412`; see [Errors, concurrency and rate limits](../integrate/errors-and-limits.md#concurrent-edits-with-etag-and-if-match).
