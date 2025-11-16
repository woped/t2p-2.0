import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Flask core
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'
    
    # App-specific URLs (use T2P prefix to distinguish custom settings)
    T2P_TRANSFORMER_BASE_URL = os.environ.get('TRANSFORMER_BASE_URL') or 'https://woped.dhbw-karlsruhe.de/pnml-bpmn-transformer'
    T2P_LLM_API_CONNECTOR_URL = os.environ.get('LLM_API_CONNECTOR_URL') or 'https://woped.dhbw-karlsruhe.de/llm-api-connector'
    T2P_OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
    
    # Server configuration
    T2P_FLASK_PORT = int(os.environ.get('FLASK_PORT') or 5000)
    T2P_FLASK_HOST = os.environ.get('FLASK_HOST') or '127.0.0.1'
    
    # Security
    SSL_REDIRECT = False
    WTF_CSRF_ENABLED = os.environ.get('WTF_CSRF_ENABLED', 'False').lower() in ['true', '1', 'yes']
    
    
    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False


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
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'heroku': HerokuConfig,
    'docker': DockerConfig,
    'unix': UnixConfig,

    'default': DevelopmentConfig
}