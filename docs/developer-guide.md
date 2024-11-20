# Developer guide

---

## API Integration (v0.3.0+)

Endurain supports integration with other apps:

### API Requirements
- **Add a header:** Every request must include an `X-Client-Type` header with either `web` or `mobile` as the value. Requests with other values will receive a `403` error.
- **Authorization:** Every request must include an `Authorization Bearer: <access token>` header with a valid (new or refreshed) access token.

### Token Handling
- The backend will generate an `access_token` valid for 15 minutes and an `refresh_token` valid for 7 days. This follow the logic of short and longed lived tokens for auth session.
- The `access_token` is used for authorization; The `refresh_token` is used to refresh the `access_token`.
- For **web apps**, the backend sends access/refresh tokens as HTTP-only cookies.
- For **mobile apps**, tokens are included in the response body.


### API Endpoints 
The API is reachable under `/api/v1`. Below are some example endpoints. All endpoints information can be checked on the backend docs (`http://localhost:98/docs` or `http://ip_address:98/docs` or `https://domain/docs`):

| What | Url | Expected Information |
| ---- | --- | ---------------------|
| **Authorize** | `/token` |  `FORM` with the fields `username` and `password`. This will be sent in clear text, use of HTTPS is highly recommended |
| **Refresh Token** | `/refresh` | header `Authorization Bearer: <Refresh Token>`  |
| **Activity Upload** | `/activities/create/upload` | .gpx or .fit file |
| **Set Weight** | `/health/weight` | JSON {'weight': <number>, 'created_at': `yyyy-MM-dd`} |
