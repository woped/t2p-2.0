"""Shared sample data for tests."""

# A minimal well-formed connector reply (logical process model JSON string).
RAW_MODEL_JSON = """{
  "events": [
    {"id": "start", "type": "startEvent", "name": "Start"},
    {"id": "end", "type": "endEvent", "name": "End"}
  ],
  "tasks": [],
  "gateways": [],
  "flows": [
    {"id": "flow", "type": "sequenceFlow", "source": "start", "target": "end"}
  ]
}"""
