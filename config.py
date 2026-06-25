import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Flask core
    SECRET_KEY = os.environ.get("SECRET_KEY") or "hard to guess string"

    # App-specific URLs (use T2P prefix to distinguish custom settings)
    T2P_TRANSFORMER_BASE_URL = (
        os.environ.get("TRANSFORMER_BASE_URL")
        or "https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer"
    )
    T2P_LLM_API_CONNECTOR_URL = (
        os.environ.get("LLM_API_CONNECTOR_URL")
        or "https://woped.dhbw-karlsruhe.de/llm-api-connector"
    )
    CONNECTOR_TIMEOUT = int(os.environ.get("CONNECTOR_TIMEOUT") or 60)
    CONNECTOR_INTERNAL_ASYNC_ENABLED = (
        os.environ.get("CONNECTOR_INTERNAL_ASYNC_ENABLED", "true").lower()
        in {"1", "true", "yes", "on"}
    )
    CONNECTOR_INTERNAL_ASYNC_FALLBACK_TO_SYNC = (
        os.environ.get("CONNECTOR_INTERNAL_ASYNC_FALLBACK_TO_SYNC", "true").lower()
        in {"1", "true", "yes", "on"}
    )
    CONNECTOR_ASYNC_POLL_INTERVAL_SECONDS = float(
        os.environ.get("CONNECTOR_ASYNC_POLL_INTERVAL_SECONDS") or 0.5
    )
    CONNECTOR_ASYNC_MAX_WAIT_SECONDS = float(
        os.environ.get("CONNECTOR_ASYNC_MAX_WAIT_SECONDS") or 120
    )

    # Server configuration
    T2P_FLASK_PORT = int(os.environ.get("FLASK_PORT") or 5000)
    T2P_FLASK_HOST = os.environ.get("FLASK_HOST") or "127.0.0.1"

    # Internal Redis (container-local by default)
    REDIS_HOST = os.environ.get("REDIS_HOST") or "127.0.0.1"
    REDIS_PORT = int(os.environ.get("REDIS_PORT") or 6379)
    REDIS_DB = int(os.environ.get("REDIS_DB") or 0)
    REDIS_URL = os.environ.get("REDIS_URL") or (
        f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )

    # Security
    SSL_REDIRECT = False
    WTF_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "False").lower() in [
        "true",
        "1",
        "yes",
    ]

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    CONNECTOR_INTERNAL_ASYNC_ENABLED = False
    CONNECTOR_INTERNAL_ASYNC_FALLBACK_TO_SYNC = True


class ProductionConfig(Config):
    SSL_REDIRECT = True

    @classmethod
    def init_app(cls, app):
        Config.init_app(app)


class DockerConfig(ProductionConfig):
    @classmethod
    def init_app(cls, app):
        ProductionConfig.init_app(app)


# Optional environment-specific configurations often used in Flask examples.
class HerokuConfig(ProductionConfig):
    @classmethod
    def init_app(cls, app):
        ProductionConfig.init_app(app)


class UnixConfig(ProductionConfig):
    @classmethod
    def init_app(cls, app):
        ProductionConfig.init_app(app)


config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "heroku": HerokuConfig,
    "docker": DockerConfig,
    "unix": UnixConfig,
    "default": DevelopmentConfig,
}
