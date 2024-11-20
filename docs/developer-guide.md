# Developer guide

---

## API Integration (v0.3.0+)

Endurain supports integration with other apps:


### API Requirements
- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** Every request must include an `Authorization Bearer: <Access Token>` header with a valid (new or refreshed) Access Token.

### Token Handling
- In general the backend will generate `access_token` valid 15 minutes and `refresh_token` valid 7 days
- The **Access Token** `access_token` is used for authorization; The **Refresh Token** `refresh_token` is used to refresh the `access_token`
- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.


### API Endpoints 
In general the API is reachable under `/api/v1`

| What | Url | Expected Information |
| ---- | --- | ---------------------|
| **Authorize** | `/token` |  `FORM` with the fields `username` and `password` |
| **Refresh Token** | `/refresh` | header `Authorization Bearer: <Refresh Token>`  |
| **Activity Upload** | `/activities/create/upload` | .gpx or .fit file |
| **Set Weight** | `/health/weight` | JSON {'weight': <number>, 'created_at': <date:yyyy-MM-dd>'} |
