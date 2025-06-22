import os

# === Base runtime configuration ===
class BaseRuntimeConfig:
    PROMPTING_STRATEGIE = "few_shot"
    API_HOST = "woped.dhbw-karlsruhe.de"
    API_PORT = 443
    LLM_PROVIDER = "openai"  # Default LLM

# === Development configuration ===
class DevelopmentRuntimeConfig(BaseRuntimeConfig):
    PROMPTING_STRATEGIE = "few_shot"
    API_HOST = "localhost"
    API_PORT = 5000
    LLM_PROVIDER = "openai"  

# === Testing configuration ===
class TestingRuntimeConfig(BaseRuntimeConfig):
    PROMPTING_STRATEGIE = "zero_shot"
    API_HOST = "test.api"
    API_PORT = 8080
    LLM_PROVIDER = "gemini"

# === Production configuration ===
class ProductionRuntimeConfig(BaseRuntimeConfig):
    PROMPTING_STRATEGIE = os.getenv("PROMPTING_STRATEGIE", "few_shot")
    API_HOST = os.getenv("API_HOST", "woped.dhbw-karlsruhe.de")
    API_PORT = int(os.getenv("API_PORT", 443))
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()


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

PROMPTING_STRATEGIE = config.PROMPTING_STRATEGIE
API_HOST = config.API_HOST
API_PORT = config.API_PORT
LLM_PROVIDER = config.LLM_PROVIDER
