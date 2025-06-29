import os

# Prüfen, ob TRANSFORMER_BASE_URL gesetzt ist, ansonsten Default setzen
if not os.getenv("TRANSFORMER_BASE_URL"):
    os.environ["TRANSFORMER_BASE_URL"] = "https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer"

if not os.getenv("OPENAI_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"

TRANSFORMER_BASE_URL = os.environ["TRANSFORMER_BASE_URL"]
OPENAI_BASE_URL = os.environ["OPENAI_BASE_URL"]