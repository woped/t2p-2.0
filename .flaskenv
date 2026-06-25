# Flask configuration
FLASK_APP=flasky.py
FLASK_ENV=development
FLASK_DEBUG=1

# Application configuration
SECRET_KEY=dev-secret-key-change-in-production

# External service URLs
TRANSFORMER_BASE_URL=https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer
LLM_API_CONNECTOR_URL=http://127.0.0.1:5001

# Server configuration for local Flask CLI
FLASK_RUN_PORT=5000
FLASK_RUN_HOST=127.0.0.1

# Security
WTF_CSRF_ENABLED=False
