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

Operational and meta endpoints, outside the `/v1` contract: `GET /_/_/echo`,
`GET /example`, `GET /api/swagger.yaml` (the spec), and `GET /metrics`
(Prometheus).

### Deprecated endpoints

`POST /api_call` was already deprecated before `/v1` was introduced and its
announced sunset date, 31 December 2025, has elapsed. It returns `410 Gone`.

The unversioned generation endpoints remain functional for compatibility until
1 December 2026. They accept their existing request contract, including
`api_key` in the JSON body, and internally use the new connector flow with the
legacy defaults `provider=openai` and `model=gpt-4o`. `GET /test_connection`
also remains functional until that date. Their responses include:

```
Deprecation: @1780272000
Sunset: Tue, 01 Dec 2026 00:00:00 GMT
Link: <https://woped.dhbw-karlsruhe.de/docs/migration>; rel="deprecation"
```

| Method | Path | Migrate to |
|--------|------|------------|
| GET  | `/test_connection` | `GET /v1/health` |
| POST | `/api_call`        | `POST /v1/generate/bpmn` (removed; returns `410`) |
| POST | `/generate_bpmn`, `/generate_BPMN` | `POST /v1/generate/bpmn` |
| POST | `/generate_pnml`, `/generate_PNML` | `POST /v1/generate/pnml` |

## `GET /v1/models`

The model registry is owned by the connector; this endpoint proxies the connector's
`GET /models`. If the connector is unreachable, this endpoint returns
`500 upstream_error`.

## Error codes

Error responses share the shape `{ "error": { "code": string, "message": string } }`
(see the `Error` schema in the spec). `error.code` is a stable identifier;
`error.message` is a short human-readable string.

| Status | code | Meaning |
|--------|------|---------|
| 400 | `invalid_request`  | malformed body or missing/empty `text` |
| 400 | `invalid_provider` | `provider`/`model` not in the registry |
| 401 | `unauthorized`     | missing or malformed bearer token |
| 410 | `deprecated`       | the already-sunset `/api_call` endpoint was called |
| 500 | `upstream_error`   | connector call failed (unreachable, timeout, non-200) |
| 500 | `transform_error`  | the BPMN→PNML transformation service failed (`/v1/generate/pnml` only) |
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
`user_text`. Provider and model validation is owned by the connector.

### Internal model representation

The value of `raw_response` is a serialized JSON process model containing logical model
elements such as `events`, `tasks`, `gateways`, and `flows`; it is not BPMN XML.
The connector-to-T2P boundary deliberately uses this structured JSON representation so
future world-model processing can consume or enrich the logical model without carrying
XML markup in the LLM exchange. This is intended to reduce markup-related token
overhead; the actual token reduction must be measured once that workflow is implemented.

T2P owns conversion from the structured JSON process model to BPMN XML.
`POST /v1/generate/bpmn` converts the JSON to BPMN XML and returns that BPMN.
`POST /v1/generate/pnml` first converts the JSON to BPMN XML, then sends the XML
to the model-transformer service (`POST <transformer>/transform`,
`direction=bpmntopnml`) and returns the resulting PNML; a transformer failure
surfaces as `500 transform_error`.
