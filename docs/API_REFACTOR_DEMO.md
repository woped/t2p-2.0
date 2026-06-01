# API Refactor Live Demo

This demo targets `feature/api-refactor` in `t2p-2.0` and
`t2p-llm-api-connector`. Use Postman rather than SoapUI: these APIs are REST
endpoints with OpenAPI 3 contracts and JSON request/response bodies, which
Postman can import, mock, script, and later execute unchanged against running
services.

## What changed

| Rebuild advantage | Evidence to show |
| --- | --- |
| Stable public contract | The public API is namespaced under `/v2`; Swagger is available at `/swagger` and its source at `/api/swagger.yaml`. |
| Credentials are no longer placed in the JSON body | `/v2/generate/*` accepts `Authorization: Bearer <api_key>`; compare this with the legacy `api_key` request field. |
| Provider choice is explicit and extensible | `/v2/models` returns provider/model pairs; generate requests select `provider` and `model`. |
| Clear separation of responsibilities | T2P orchestrates model formats; the connector owns LLM/provider dispatch via `/generate` and `/models`; the transformer converts BPMN to PNML. |
| Smaller, testable integration boundary | `ConnectorClient` replaces the old direct-provider pipeline in T2P; its transport behavior and error mapping are covered by focused tests. |
| Correct output pipeline | The connector's raw BPMN-structure JSON is converted to BPMN XML in T2P; `/v2/generate/pnml` then applies the BPMN-to-PNML transformer step. |
| Clients can handle errors predictably | v2 errors use `{ "error": { "code", "message" } }`, including `unauthorized`, `invalid_request`, `invalid_provider`, `upstream_error`, and `transform_error`. |
| Migration does not silently break existing callers | Compatible legacy routes include `Deprecation`, `Sunset`, and `Link` headers. The already expired `/api_call` explicitly returns `410 Gone`. |
| Behavior is already testable without an external LLM | Current local branch tests cover v2 routing, connector dispatch, errors, PNML transformation handling, and legacy migration responses. |

## Postman setup now: mock-backed demo

Import [`postman/WOPED-T2P-api-refactor.postman_collection.json`](postman/WOPED-T2P-api-refactor.postman_collection.json)
into Postman. The collection includes saved example responses and test scripts.

1. In Postman, create a mock server from the imported collection.
2. Copy its mock URL into the collection variable `baseUrl`.
3. Also set `connectorBaseUrl` to the same mock URL when showing the optional internal connector folder.
4. Run the requests in order. The `x-mock-response-name` headers select the saved examples.

This path presents the frozen contract and migration behavior without claiming
that provider calls or deployed service wiring are complete.

## Recommended presentation sequence

1. Open `GET /v2/health`: point out the versioned, minimal liveness contract.
2. Open `GET /v2/models`: explain that clients can discover available models rather than depending on one hard-coded provider.
3. Open `POST /v2/generate/bpmn`: show `Authorization: Bearer {{apiKey}}` and the absence of an `api_key` JSON field.
4. Open `POST /v2/generate/pnml`: show that output format is explicit and the orchestration handles the extra transformer step.
5. Send `Generate BPMN - missing bearer token`: show the `401` plus stable `unauthorized` error code.
6. Send `Generate BPMN - invalid request body`: show the `400` plus stable `invalid_request` code.
7. Send `Removed legacy /api_call`: show `410 Gone` and the migration `Link` header.
8. Send `Compatible legacy health`: show that supported older clients receive explicit `Deprecation` and `Sunset` guidance.
9. Optionally open `Connector models`: explain that public API and provider integration are separate contracts.

## Live execution later

Requests in the same collection can be executed against running services. The
failure and migration requests already avoid external provider calls; the two
successful generation requests require working connector/transformer wiring
and a provider API key.

Run the connector on port `5000`:

```bash
cd t2p-llm-api-connector
export FLASK_APP=llm-api-connector.py
export FLASK_DEBUG=1
.venv/bin/flask run --port 5000
```

Run the T2P orchestrator on port `5001`, configured to use the local connector:

```bash
cd t2p-2.0
export LLM_API_CONNECTOR_URL=http://localhost:5000
.venv/bin/flask --app flasky run --port 5001
```

Set Postman collection variable `baseUrl` to `http://localhost:5001`,
`connectorBaseUrl` to `http://localhost:5000`, and override `apiKey` as a
sensitive Postman environment variable only when performing a real
provider-backed generate call.

## Current verification

From the working tree on 27 May 2026:

```bash
cd t2p-2.0
.venv/bin/python -m pytest -q
# 81 passed

cd ../t2p-llm-api-connector
.venv/bin/python -m pytest -q
# 13 passed, 8 subtests passed
```

These results verify the local API behaviors under test. They do not verify an
end-to-end deployment with an LLM provider and the model transformer running.
