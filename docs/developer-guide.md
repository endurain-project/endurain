# Developer guide

---

## API Integration (v0.3.0+)

Endurain supports integration with other apps:

- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.

### API Requirements

- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Login and refresh endpoint**: `/api/v1/token` and `/api/v1/refresh`.
- **Activity Upload:** Use the `/api/v1/activities/create/upload` endpoint (expects a .gpx or .fit file).