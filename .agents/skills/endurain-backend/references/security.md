# Security

## Uploads
- All `UploadFile` handling goes through `backend/app/core/file_uploads.py`.
- Route handlers are sync, so persist with `save_validated_upload_sync(file, kind=UploadKind.X, upload_dir=..., filename=...)`
  and read into memory with `read_validated_upload_sync(file, kind=...)`. The `async` variants are for code already on the event loop.
- Never instantiate `safeuploads.FileValidator` elsewhere.
- Never join user-supplied filenames into paths; use server-generated names (UUID/hash/fixed).
- Enforce size limits.

## Access control
- Deny by default; check rights explicitly against the resource.
- Multi-activity bulk reads trust pre-scoped ids and stay behind the owner-scoped contributor; a new caller is a latent IDOR.
- Prevent path traversal on any user-influenced path.

## Injection and secrets
- Parameterized queries only; no string-built SQL.
- Shell input via `shlex`; no `shell=True` on user data.
- No hardcoded secrets; read from environment.
- Argon2/bcrypt for passwords; AES-256 for data at rest; JSON, not pickle.

## Outbound requests
- Treat user-provided URLs as untrusted; allow-list host, port, path.
- Egress and SSRF host checks live in `core.network`; add a platform provider, do not call `requests`/`httpx` from `modules.activities`.

## Auth flows
- New session identifier on login; cookies `HttpOnly`, `Secure`, `SameSite=Strict`.
- Rate limit and lock out auth and password-reset flows.

When you add a mitigation, state what it protects against; when you flag a vulnerability, explain the risk.
