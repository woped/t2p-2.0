# t2p-2.0 API contract (v1 refactor)

Status: **proposed** — interface frozen for the `feature/api-refactor` work. Code does
not implement this yet. This file is the source of truth both sides build against.

## External (client-facing) API

### Endpoint map

| Method | Path | State |
|--------|------|-------|
| GET  | `/example`          | unchanged |
| GET  | `/api/swagger.yaml` | unchanged |
| GET  | `/metrics`          | unchanged |
| GET  | `/test_connection`  | deprecated → `/v1/health` |
| GET  | `/_/_/echo`         | deprecated → `/v1/health` |
| POST | `/api_call`         | deprecated → `/v1/generate/bpmn` |
| POST | `/generate_bpmn`    | deprecated → `/v1/generate/bpmn` |
| POST | `/generate_BPMN`    | deprecated → `/v1/generate/bpmn` |
| POST | `/generate_pnml`    | deprecated → `/v1/generate/pnml` |
| POST | `/generate_PNML`    | deprecated → `/v1/generate/pnml` |
| POST | `/v1/generate/bpmn` | **new** |
| POST | `/v1/generate/pnml` | **new** |
| GET  | `/v1/models`        | **new** |
| GET  | `/v1/health`        | **new** |

Deprecated endpoints stay live; they must keep working for existing clients and signal
deprecation (Deprecation / Sunset / Link headers) while routing through the new pipeline.

### `POST /v1/generate/bpmn`, `POST /v1/generate/pnml`

```
Header: Authorization: Bearer <api_key>
Body: {
  "text":     string  (required)
  "provider": string  (required) -- valid values from GET /v1/models
  "model":    string  (required) -- valid values from GET /v1/models
}
Response 200: { "result": string }
Response 400: { "error": { "code": string, "message": string } }
Response 401: { "error": { "code": string, "message": string } }
Response 500: { "error": { "code": string, "message": string } }
```

### `GET /v1/models`

```
Response 200: { "models": [{ "provider": string, "model": string, "default": bool }] }
```

### `GET /v1/health`

```
Response 200: { "status": "ok" }
```

Shallow liveness only — returns 200 whenever the process is up; does **not** check the
connector (a health check must not cascade downstream failures). A dependency check, if
ever needed, would be a separate `/v1/ready`.

### Error codes

`error.code` is a stable identifier; `message` is short and human. Codes map onto the
frozen status codes:

| Status | code | When |
|--------|------|------|
| 400 | `invalid_request`  | malformed body, missing/empty `text` |
| 400 | `invalid_provider` | `provider`/`model` not in the registry |
| 401 | `unauthorized`     | missing/malformed bearer token |
| 500 | `upstream_error`   | connector call failed (down, timeout, non-200) |
| 500 | `internal_error`   | unexpected catch-all |

### Models (consumption)

The registry lives in the connector; t2p-2.0 does not own it. t2p-2.0 fetches the
connector's `GET /models` and re-exposes it via `GET /v1/models`. Caching: lazy-loaded
in-memory TTL (~10 min), so startup never depends on the connector being up. When the
connector is unreachable: `/v1/models` serves the cached list if warm, else
`500 upstream_error`; generate-path validation uses the cache if warm, otherwise defers
to the connector (the authority — the call then fails as `upstream_error` if it is down).

## Downstream dependency: LLM API connector

t2p-2.0 is the only consumer of the connector. It calls the connector's internal API
(see the connector repo's `docs/api-contract.md`). The internal API has no other
consumers, so it is overwritten outright (no versioning). Summary of what t2p-2.0 sends:

```
POST <connector>/generate
Header: Authorization: Bearer <api_key>   (forwarded verbatim from the client)
Body: { "user_text": string, "provider": string, "model": string }
Response 200: { "raw_response": string }
```
