# Compatibility between releases

The rules a client can rely on when the server is upgraded. They hold for the Endurain web and mobile apps and for other clients that use [API keys](api-keys.md). A change that breaks one of them is announced as a breaking change in the release notes.

!!! warning "First-party sign-in"
    The `/auth` sign-in routes (login, MFA verification, password change, token exchange and refresh) and the SSO hand-off through `ALLOWED_REDIRECT_URIS` are first-party protocols for Endurain's own web and mobile apps. Other applications use API keys today and the OAuth endpoints, reserved under `/oauth/*`, when they exist, and may be refused on the first-party routes then.

## Responses gain members

- A response object may gain new members in any release. Ignore a member you do not know; do not refuse the response because of it.
- A member keeps its name, type and meaning. A new meaning arrives as a new member.
- Send only the request fields the documentation describes. A new optional request field can appear in any release, and an older server may refuse a field it does not know.

## Open sets

These values are open: a release can add one. Handle a value you do not know as described, never as one of the known values.

| Value | Known today | When a value is unknown |
| ----- | ----------- | ----------------------- |
| `next_step` in a sign-in or token answer (`/auth/login`, `/auth/mfa/verify`, `/auth/password-change`, `/auth/refresh`, `/auth/sessions/{session_id}/tokens`) | `mfa`, `password_change`, `exchange`, `tokens` | The client is not signed in. Tell the user that this client cannot finish the sign-in and should be updated. See [Sign-in steps](authentication.md#sign-in-steps). |
| `next_step` in a sign-up answer (`/public/sign-up/request`, `/confirm`, `/resend`) | `sign_in`, `check_email`, `await_approval` | The client cannot tell what comes next. Show a general message and send the user to sign in or to check their email. |
| `methods` of an MFA-required sign-in answer, and `type` of a factor in the MFA status | `totp`, `backup_code` for `methods`; `totp` for `type` | Offer only the methods you know. If you know none, tell the user to finish the sign-in in the web app. |
| `scope` of a `429` problem document | `requests`, `sign-in`, `mfa`, `step-up`, `provider`, `follow-request` | Wait for `Retry-After` and try again, whatever the scope. |
| A problem document's `type` | The [error types](errors-and-limits.md#error-types) | Act on the `status`. |
| The `error` query parameter of a failed SSO sign-in (`/login?error=<code>`) | The codes in [SSO failures](oauth-sso-pkce.md#sso-failures) | Show a general sign-in failure. |
| The `type` of a step-up challenge (a `401` with `WWW-Authenticate: Bearer error="insufficient_user_authentication"`) | `urn:endurain:error:idp-reauth-required`. See [Step-up Refusal](account-security.md#step-up-refusal) | The client does not support that method. Stop, keep no partial state and tell the user to make the change in a client that does. |
| `provider_type` of an identity provider | `oidc`, `oauth2` | Show the provider as it is named and do not assume the protocol it speaks. |
| `require_mfa` of the server settings | `off`, `administrators`, `everyone` | Treat the account as one that may be required to have MFA, and send the user to the web app to set it up. |
| `access_type` of a user | `regular`, `admin` | Treat the user as a regular user and rely on the scopes of the token for what it may do. |
| `security` of the mail settings | `starttls`, `ssl`, `none` | Show the value as it is and do not assume how the connection is secured. |
| The `X-Client-Type` header | `web`, `mobile` | Send one of the documented values. A value the server does not know is refused with `422`. |

The `action` a step-up request body names is a request value, and a release can add an operation to it.

## Refusals

The status code is the stable part of a refusal. A case answered today with a general problem `type` may get a more specific `type` of its own in a later release, with the same status. Branch on the specific types you handle and fall back on the status for everything else. A `type` that exists keeps its URN and its meaning.

## New ways to sign in

A new way to authenticate, such as passkeys, arrives as new optional request fields or new routes. An existing field never changes meaning to carry it. It can make a sign-in answer a `next_step` your client does not know yet, which is why `next_step` is an open set.

## Tokens

Access tokens, refresh tokens, MFA and password-change challenges, tickets and API keys are opaque strings. Do not parse them, read their claims or assume a length or format: they can change in any release. Read lifetimes from the response fields (`expires_in`, `refresh_token_expires_in`), not from the token.

The access and refresh tokens are JWTs, but a client must not depend on that. The claim that names the kind of client is `client_type` (`web` or `mobile`). The tokens carry no `client_id`: that name is reserved for the registered application of a future OAuth client, and the values `endurain-web` and `endurain-mobile` are reserved for Endurain's own apps. An application that uses the first-party sign-in routes is a `mobile` or `web` client; it has no application id of its own.

Every response that carries a token or another secret is sent with `Cache-Control: no-store` and `Pragma: no-cache`, so no browser or proxy cache keeps it. The list is in [Responses that carry a secret](account-security.md#responses-that-carry-a-secret).

## Reserved paths

These paths are reserved for planned features, such as third-party OAuth clients and passkeys. Endurain will not use them for anything else, and a client must not expect them to exist yet:

- Under the API root `/api/v1`: `/oauth/`, `/auth/webauthn/`, `/profile/passkeys`, `/profile/grants` and `/oauth-clients`.
- At the server root: `/.well-known/`, as [RFC 8615](https://www.rfc-editor.org/rfc/rfc8615) defines.

## Stability promises for the OAuth server

- `/api/v1` stays served. It appears in the callback and back-channel URLs registered at identity providers, in the cookie names and in the refresh token audience, so a new API version keeps answering these paths.
- A future `/oauth/token` will answer errors in the JSON format of [RFC 6749 section 5.2](https://www.rfc-editor.org/rfc/rfc6749#section-5.2) (`error`, `error_description`) on that path only, as an exception to the problem documents every other route returns.
- The administrator scopes (`users:write`, `server-settings:*`, `identity-providers:*`, `sessions:*` and the like) will never be offered to a third-party application for consent. An application gets narrower scopes of its own, which arrive as new names.
- `client_id` is the identifier of a registered OAuth client. The values `endurain-web` and `endurain-mobile` are reserved for Endurain's own applications.
