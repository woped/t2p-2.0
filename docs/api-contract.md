# t2p-2.0 API

The authoritative endpoint contract — paths, request/response schemas, status
codes, and security — is the OpenAPI spec at [`app/api/swagger.yaml`](../app/api/swagger.yaml).
It is served at runtime from `/api/swagger.yaml` and rendered as interactive docs
at `/swagger`. This document is an overview; when it disagrees with the spec, the
spec wins.

## Endpoints

The `/v1` namespace is the current API. See the spec for full schemas.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/generate/bpmn` | Generate a BPMN model from a process description |
| POST | `/v1/generate/pnml` | Generate a PNML model from a process description |
| GET  | `/v1/models`        | List available `provider`/`model` pairs (see below) |
| GET  | `/v1/health`        | Shallow liveness check |

Operational and meta endpoints, outside the `/v1` contract: `GET /example`,
`GET /api/swagger.yaml` (the spec), and `GET /metrics` (Prometheus).

### Deprecated endpoints

The unversioned legacy endpoints are **gone**: they return `410 Gone` with an
`error.code` of `deprecated` and no longer produce results. Each carries
`Deprecation: true` and a `Link` header pointing at the migration guide (no
`Sunset` header — the endpoints are already removed, so a future sunset date
would be contradictory). Clients must migrate to the `/v1` endpoint shown below.

| Method | Path | Migrate to |
|--------|------|------------|
| GET  | `/test_connection` | `GET /v1/health` |
| GET  | `/_/_/echo`        | `GET /v1/health` |
| POST | `/api_call`        | `POST /v1/generate/bpmn` |
| POST | `/generate_bpmn`, `/generate_BPMN` | `POST /v1/generate/bpmn` |
| POST | `/generate_pnml`, `/generate_PNML` | `POST /v1/generate/pnml` |

## `GET /v1/models`

The model registry is owned by the connector; this endpoint proxies the connector's
`GET /models`. The list is cached in memory with a ~10-minute TTL, loaded lazily on
first use, so startup does not depend on connector availability. If the connector is
unreachable, the cached list is returned when available, otherwise `500 upstream_error`.

## Error codes

Error responses share the shape `{ "error": { "code": string, "message": string } }`
(see the `Error` schema in the spec). `error.code` is a stable identifier;
`error.message` is a short human-readable string.

| Status | code | Meaning |
|--------|------|---------|
| 400 | `invalid_request`  | malformed body or missing/empty `text` |
| 400 | `invalid_provider` | `provider`/`model` not in the registry |
| 401 | `unauthorized`     | missing or malformed bearer token |
| 410 | `deprecated`       | a removed legacy endpoint was called |
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
