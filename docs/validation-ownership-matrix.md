# Validation Ownership Matrix

Date: 2026-07-01

Scope:
- t2p-2.0 (orchestrator)
- t2p-llm-api-connector (connector)
- model-transformer (transform service)

Goal:
- Make ownership explicit for all validation responsibilities.
- Identify residual validation logic in t2p-2.0.
- Define concrete removals needed if connector should become sole validator.

## Executive Summary

Current state:
- Primary request and process-model validation is owned by t2p-llm-api-connector.
- t2p-2.0 performs integration payload sanity checks only (connector payload decode/build safety), mapped as upstream integration errors.
- model-transformer is primarily parsing/transformation, not business-rule validation owner.

Implication:
- Validation is mostly centralized in connector, but not fully removed from t2p-2.0.

## Ownership Matrix (Current State)

| Validation Job | Owner (Current) | Location | Interface/Entry | Result on Failure |
|---|---|---|---|---|
| Authorization header format | t2p-llm-api-connector | app/api/routes.py (`_extract_bearer_key`, `_validate_request`) | `POST /generate`, `POST /internal/jobs/generate` | 401 `unauthorized` |
| Request body type and required fields (`user_text`, `provider`, `model`) | t2p-llm-api-connector | app/api/routes.py (`_validate_request`) | `POST /generate`, `POST /internal/jobs/generate` | 400 `invalid_request` |
| Provider/model existence | t2p-llm-api-connector | app/api/routes.py (`_validate_request`), app/services/model_registry.py | same as above | 400 `invalid_provider` |
| Process model semantic validation (workflow-net style checks) | t2p-llm-api-connector | app/validation.py (`validate_model`, VALIDATORS), app/api/routes.py (`_generate_validated`) | generation flow (sync + async worker) | 422 `model_unprocessable` |
| Structured output schema validation (LLM output shape/types) | t2p-llm-api-connector | app/schemas.py (Pydantic), app/services/llm_service.py (`ProcessModel` usage) | provider call parse/schema step | upstream/provider or validation error flow |
| Async job payload shape and lifecycle consistency | t2p-llm-api-connector | app/services/async_jobs.py, app/api/routes.py (`internal_generate_submit`, `internal_generate_status`) | `/internal/jobs/*` | status + normalized error payload |
| Connector response JSON parse safety | t2p-2.0 (integration safety) | app/backend/bpmn_builder.py (`_decode`) | connector response -> BPMN conversion | 502 `upstream_error` (via route mapping) |
| Connector response graph build safety (missing keys / malformed structure) | t2p-2.0 (integration safety) | app/backend/bpmn_builder.py (`_build`) | connector response -> BPMN conversion | 502 `upstream_error` (via route mapping) |
| Route-level relay/mapping of connector validation errors | t2p-2.0 | app/api/routes.py (`_v2_generate`) | `/v2/generate/*` | relay connector 4xx/422 shape |
| BPMN<->PNML structural/business validation | model-transformer | not primary owner | transform operations | transform exceptions / parser failures |
| Token/rate guard endpoint | model-transformer | app/checkTokens/main.py (`check_tokens`) | checkTokens endpoint path | validation/rate error |

## Ownership Matrix (Target State)

Target assumption:
- Connector is sole owner for request + process-model validation.
- t2p-2.0 acts only as orchestrator/relay and transformation coordinator.
- model-transformer remains parser/transform service.

| Validation Job | Target Owner | Change Needed |
|---|---|---|
| Request and auth validation | t2p-llm-api-connector | none |
| Provider/model validation | t2p-llm-api-connector | none |
| Process model semantic validation | t2p-llm-api-connector | none |
| Schema validation | t2p-llm-api-connector | none |
| Connector response parse/build validation in t2p | t2p-llm-api-connector | optional removal/refactor in t2p-2.0 (see below) |
| Error relay contract | t2p-2.0 | keep (orchestrator concern) |

## Residual Checks in t2p-2.0 (What Still Exists)

1. Defensive JSON decode safety in `app/backend/bpmn_builder.py`:
- `_decode(raw_response)` raises `ConnectorPayloadError` when connector returns non-JSON.

2. Defensive graph-shape safety in `app/backend/bpmn_builder.py`:
- `_build(raw_response, build)` catches `KeyError` and raises `ConnectorPayloadError`.

3. Route mapping to upstream integration error in `app/api/routes.py`:
- `_v2_generate` catches `ConnectorPayloadError` and returns `502 upstream_error`.

These are not business-rule validators; they are integration payload safety checks.

## If You Want Connector as Sole Validator (Concrete t2p Cleanup)

Minimal option (recommended): keep t2p defensive guards
- Keep current behavior for crash safety and backward compatibility.
- Continue treating malformed connector payloads as integration faults (`invalid_model`).

Strict centralization option: remove local validation semantics from t2p (implemented)
1. In `app/backend/bpmn_builder.py`
- Replaced `InvalidModelError` with integration exception class `ConnectorPayloadError`.
- Guardrails retained as transport/integration sanity checks.

2. In `app/api/routes.py`
- Connector payload failures mapped to `upstream_error` (502).

3. In docs/contracts
- Updated `docs/api-contract.md` and OpenAPI docs to reflect 502 `upstream_error` for payload incompatibility.

4. Tests
- Updated tests that previously asserted `invalid_model` for malformed connector output.
- Passthrough tests for connector-owned 4xx/422 remain intact.

## Verification Checklist After Any Cleanup

1. Connector-owned validation still returns unchanged error contracts:
- 400 `invalid_request`
- 400 `invalid_provider`
- 401 `unauthorized`
- 422 `model_unprocessable`

2. t2p relay behavior remains stable:
- Connector 4xx/422 responses are relayed with body and status.

3. t2p malformed connector payload handling is explicit and documented:
- `upstream_error` (502) with integration-contract semantics.

4. Integration tests pass across all three services for:
- sync generate path
- internal async submit/poll path
- BPMN and PNML generation paths

## Source Pointers

- t2p-2.0:
  - app/api/routes.py
  - app/backend/bpmn_builder.py
- t2p-llm-api-connector:
  - app/api/routes.py
  - app/validation.py
  - app/schemas.py
  - app/services/llm_service.py
- model-transformer:
  - app/checkTokens/main.py
  - app/transform/...
