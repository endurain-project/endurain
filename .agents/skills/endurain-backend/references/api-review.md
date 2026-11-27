# Reviewing an API change

The shape rules are in `docs/developer-guide/http-api.md`; `tests/architecture/test_api_contract.py` and `test_route_conventions.py` enforce the checkable ones.
This checklist covers what a test cannot judge.
Use it when adding or changing a route, and when reviewing one.

## Checklist

| Look for | Why it breaks | Use instead |
| --- | --- | --- |
| A rule the change needs that the guide does not state | The next route invents a different answer | Add the rule to `http-api.md` in the same change |
| A new entry in a `test_api_contract.py` register | Registers only hold debt that existed before the test | Follow the rule; a new permanent exception needs a reason the reviewer accepts |
| A read or list that returns another user's data | Data reaches someone the owner did not share it with | The owner, visibility and hidden-field checks of the sibling routes; non-owner fields cleared in the serializer |
| A route whose answer differs for "missing" and "not allowed" | Callers can probe which records and accounts exist | The same `404` for both (`AccessConcealedError` when the code knows it is refusing) |
| A default that decides who sees data (visibility, discoverability, public links) | A wrong default exposes every new account | The default stated in `docs/features/`, and a test that pins it |
| A change to a credential, recovery channel or role | Old sessions or emailed links keep the old access | Revoke sessions and void outstanding recovery tokens in the same transaction; audit it |
| An auth decision that depends on a client-declared value (`X-Client-Type`, a redirect scheme) | One unexpected value skips a branch | Validate the value as an enum before branching; fail closed |
| A refusal on an auth or SSO path that only logs | No trace of the attack in the audit trail | `docs/developer-guide/audit-trail.md`: refused sign-ins are audited too |
| A file read, decoded or validated outside `core/file_uploads.py` | Bypasses size, type and metadata handling | `core/file_uploads.py`, ownership checked before the body is read |
| A response that carries a token, key, secret or export | Kept by a cache or a browser | `Cache-Control: no-store` |
| A `202` | The client cannot find the job | `Content-Location` of the status resource and `Retry-After`; a `409` "already running" names the running job |
| A route, status code or body the client docs describe differently | Client authors build against the docs | `docs/integrate/` updated in the same change |
| A new list, enum or table copied into the docs by hand | The copy drifts from the code | A generated table (`docs/developer-guide/writing-docs.md`) |

## Reporting

Review the code or diff against every row and report:

1. Findings: severity (high exposes data or breaks auth, medium breaks a client or the contract, low is hygiene), `file:line`, what happens, which rule it breaks, fix.
2. Rows checked and clear, so coverage is visible.
