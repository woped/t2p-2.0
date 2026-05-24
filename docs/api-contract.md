# t2p-2.0 API

## Endpoints

| Method | Path |
|--------|------|
| POST | `/v1/generate/bpmn` |
| POST | `/v1/generate/pnml` |
| GET  | `/v1/models`        |
| GET  | `/v1/health`        |
| GET  | `/example`          |
| GET  | `/api/swagger.yaml` |
| GET  | `/metrics`          |

### Deprecated endpoints

Retained for backward compatibility. They emit `Deprecation`, `Sunset`, and `Link`
response headers and are served by the pipeline behind their replacement.

| Method | Path | Replacement |
|--------|------|-------------|
| GET  | `/test_connection` | `/v1/health` |
| GET  | `/_/_/echo`        | `/v1/health` |
| POST | `/api_call`        | `/v1/generate/bpmn` |
| POST | `/generate_bpmn`   | `/v1/generate/bpmn` |
| POST | `/generate_BPMN`   | `/v1/generate/bpmn` |
| POST | `/generate_pnml`   | `/v1/generate/pnml` |
| POST | `/generate_PNML`   | `/v1/generate/pnml` |

## `POST /v1/generate/bpmn`, `POST /v1/generate/pnml`

```
Header: Authorization: Bearer <api_key>
Body: {
  "text":     string  (required)
  "provider": string  (required) -- a value from GET /v1/models
  "model":    string  (required) -- a value from GET /v1/models
}
Response 200: { "result": string }
Response 400: { "error": { "code": string, "message": string } }
Response 401: { "error": { "code": string, "message": string } }
Response 500: { "error": { "code": string, "message": string } }
```

## `GET /v1/models`

```
Response 200: { "models": [{ "provider": string, "model": string, "default": bool }] }
```

The model registry is owned by the connector. This endpoint proxies the connector's
`GET /models`. The list is cached in memory with a ~10-minute TTL, loaded lazily on first
use, so startup does not depend on connector availability. If the connector is
unreachable, the cached list is returned when available, otherwise `500 upstream_error`.

## `GET /v1/health`

```
Response 200: { "status": "ok" }
```

Shallow liveness check: returns 200 while the process is running. It does not probe the
connector.

## Error codes

`error.code` is a stable identifier; `error.message` is a short human-readable string.

| Status | code | Meaning |
|--------|------|---------|
| 400 | `invalid_request`  | malformed body or missing/empty `text` |
| 400 | `invalid_provider` | `provider`/`model` not in the registry |
| 401 | `unauthorized`     | missing or malformed bearer token |
| 500 | `upstream_error`   | connector call failed (unreachable, timeout, non-200) |
| 500 | `internal_error`   | unexpected error |

## Connector dependency

Each generate request is forwarded to the connector's internal API (documented in the
connector repository's `docs/api-contract.md`):

```
POST <connector>/generate
Header: Authorization: Bearer <api_key>
Body: { "user_text": string, "provider": string, "model": string }
Response 200: { "raw_response": string }
```

The client's `Authorization` header is forwarded unchanged; the request `text` is sent as
`user_text`. The `provider`/`model` of a generate request are validated against the
cached model list when available; otherwise validation is left to the connector.
