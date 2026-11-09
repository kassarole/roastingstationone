# Roasting Station: One
## Purpose
Roasting Station: One is a django based web server for viewing, analyzing, reviewing and discussing Artisan Scope coffee roasting logs. It was created for use at [Pumping Station: One](https://pumpingstationone.org).
## Setup
1. Copy .env.example to .env
2. Set the relevent values. You can ignore the OIDC settings if you don't want to use it but OIDC is the primary auth method
3. run `docker compose up --build -d`
4. Profit I guess?
## Contributing
1. Open up an issue. Try to be detailed. It's not that deep.
## Roast API

Token auth via `ROAST_API_TOKEN` (set in env). Send as `Authorization: Bearer <token>`
or `X-API-Token: <token>`.

### `POST /api/upload/`
Multipart upload of one or more `.alog` files.

| Field | Notes |
|---|---|
| `alog_files` or `file` | Repeatable. At least one required. |
| `is_public` | Optional. `1`/`true`/`yes` → public. Default private. |

Returns `{created: [...], failed: [...], count: n}`.

```bash
curl -X POST https://roast.pumpingstationone.org/api/upload/ \
  -H "Authorization: Bearer $ROAST_API_TOKEN" \
  -F "alog_files=@roast.alog" \
  -F "is_public=1"
```
### `GET /api/roasts/<alog_uuid>/`
Look up a roast by its Artisan alog UUID (32-char hex, e.g.
`c44b9e1ee7e24cfda0bf2ea7cc2b0265`). Same object shape as `created`
entries above, plus `alog_uuid`. Returns private roasts too — any

```bash
curl https://example.com/api/roasts/c44b9e1ee7e24cfda0bf2ea7cc2b0265/ \
  -H "Authorization: Bearer $ROAST_API_TOKEN"
```