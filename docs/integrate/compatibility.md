# Compatibility between releases

The rules a client can rely on when the server is upgraded. They hold for the Endurain web and mobile apps and for third-party clients, such as an app that signs in through [SSO](oauth-sso-pkce.md), from v0.21.0 on. A change that breaks one of them is announced as a breaking change in the release notes.

## Responses gain members

- A response object may gain new members in any release. Ignore a member you do not know; do not refuse the response because of it.
- A member keeps its name, type and meaning. A new meaning arrives as a new member.
- Send only the request fields the documentation describes. A new optional request field can appear in any release, and an older server may refuse a field it does not know.

## Open sets

These values are open: a release can add one. Handle a value you do not know as described, never as one of the known values.

| Value | Known today | When a value is unknown |
| ----- | ----------- | ----------------------- |
| `next_step` in a sign-in or token answer (`/auth/login`, `/auth/mfa/verify`, `/auth/password-change`, `/auth/refresh`, `/auth/sessions/{session_id}/tokens`) | `mfa`, `password_change`, `exchange`, `tokens` | The client is not signed in. Tell the user that this client cannot finish the sign-in and should be updated. See [Sign-in steps](authentication.md#sign-in-steps). |
| A problem document's `type` | The [error types](errors-and-limits.md#error-types) | Act on the `status`. |
| The `error` query parameter of a failed SSO sign-in (`/login?error=<code>`) | The codes in [SSO failures](oauth-sso-pkce.md#sso-failures) | Show a general sign-in failure. |
| The `X-Client-Type` header | `web`, `mobile` | Send one of the documented values. A value the server does not know is refused with `422`. |

## Refusals

The status code is the stable part of a refusal. A case answered today with a general problem `type` may get a more specific `type` of its own in a later release, with the same status. Branch on the specific types you handle and fall back on the status for everything else. A `type` that exists keeps its URN and its meaning.

## New ways to sign in

A new way to authenticate, such as passkeys, arrives as new optional request fields or new routes. An existing field never changes meaning to carry it. It can make a sign-in answer a `next_step` your client does not know yet, which is why `next_step` is an open set.

## Tokens

Access tokens, refresh tokens, `session_id`, MFA and password-change challenges, tickets and API keys are opaque strings. Do not parse them, read their claims or assume a length or format: they can change in any release. Read lifetimes from the response fields (`expires_in`, `refresh_token_expires_in`), not from the token.

Every response that carries a token or another secret is sent with `Cache-Control: no-store` and `Pragma: no-cache`, so no browser or proxy cache keeps it. The list is in [Responses that carry a secret](account-security.md#responses-that-carry-a-secret).

## Reserved paths

These paths are reserved for planned features, such as third-party OAuth clients and passkeys. Endurain will not use them for anything else, and a client must not expect them to exist yet:

- Under the API root `/api/v1`: `/oauth/`, `/auth/webauthn/`, `/profile/passkeys`, `/profile/grants` and `/oauth-clients`.
- At the server root: `/.well-known/`, as [RFC 8615](https://www.rfc-editor.org/rfc/rfc8615) defines.
