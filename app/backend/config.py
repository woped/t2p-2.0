import os

# === Base runtime configuration ===
class BaseRuntimeConfig:
    API_HOST = "woped.dhbw-karlsruhe.de"
    API_PORT = 443

# === Development configuration ===
class DevelopmentRuntimeConfig(BaseRuntimeConfig):
    API_HOST = "localhost"
    API_PORT = 5000

# === Testing configuration ===
class TestingRuntimeConfig(BaseRuntimeConfig):
    API_HOST = "test.api"
    API_PORT = 8080

# === Production configuration ===
class ProductionRuntimeConfig(BaseRuntimeConfig):
    API_HOST = os.getenv("API_HOST", "woped.dhbw-karlsruhe.de")
    API_PORT = int(os.getenv("API_PORT", 443))


# === Return active config class based on FLASK_ENV ===
def get_runtime_config():
    env = os.getenv("FLASK_ENV", "development").lower()
    if env == "production":
        return ProductionRuntimeConfig()
    elif env == "testing":
        return TestingRuntimeConfig()
    else:
        return DevelopmentRuntimeConfig()


# === Load active runtime values (shortcut access) ===
config = get_runtime_config()

API_HOST = config.API_HOST
API_PORT = config.API_PORT
TRANSFORMER_BASE_URL = os.environ.get('TRANSFORMER_BASE_URL') or 'https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer'
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
