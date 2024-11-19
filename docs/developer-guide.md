# Developer guide

---

## API Integration (v0.3.0+)

Endurain supports integration with other apps:

- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.

### API Requirements

- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** After requesting or refreshing the Access Token use Header `Authorization Bearer: <Access Token>`

### API Endpoints 
In general the API is reachable under `/api/v1`

| What | Url | Expected Information |
| ---- | --- | ---------------------|
| **Authorize** | `/token` |  use `FORM` with the fields `username` and `password` |
| **Refresh Token** | `/refresh` | use Header `Authorization Bearer: <Refresh Token>`  |
| **Activity Upload** | `/activities/create/upload` | .gpx or .fit file |
| **Set Weight** | `/health/weight` | expects JSON {'weight': <number>, 'created_at': <date:yyyy-MM-dd>'} |
