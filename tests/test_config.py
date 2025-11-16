"""
Tests for configuration module
"""
import os
from config import (
    Config, 
    DevelopmentConfig, 
    TestingConfig, 
    ProductionConfig, 
    DockerConfig,
    HerokuConfig,
    UnixConfig,
    config
)


class TestBaseConfig:
    """Tests for base Config class"""
    
    def test_config_has_secret_key(self):
        assert hasattr(Config, 'SECRET_KEY')
        assert Config.SECRET_KEY is not None
    
    def test_config_has_transformer_url(self):
        assert hasattr(Config, 'T2P_TRANSFORMER_BASE_URL')
        assert Config.T2P_TRANSFORMER_BASE_URL is not None
    
    def test_config_has_llm_connector_url(self):
        assert hasattr(Config, 'T2P_LLM_API_CONNECTOR_URL')
        assert Config.T2P_LLM_API_CONNECTOR_URL is not None
    
    def test_config_has_port_and_host(self):
        assert hasattr(Config, 'T2P_FLASK_PORT')
        assert hasattr(Config, 'T2P_FLASK_HOST')
        assert isinstance(Config.T2P_FLASK_PORT, int)
        assert isinstance(Config.T2P_FLASK_HOST, str)
    
    def test_config_ssl_redirect_default(self):
        assert Config.SSL_REDIRECT == False
    
    def test_config_init_app(self):
        from unittest.mock import Mock
        app = Mock()
        # Should not raise exception
        Config.init_app(app)


class TestDevelopmentConfig:
    """Tests for DevelopmentConfig"""
    
    def test_development_debug_enabled(self):
        assert DevelopmentConfig.DEBUG == True


class TestTestingConfig:
    """Tests for TestingConfig"""
    
    def test_testing_flag_enabled(self):
        assert TestingConfig.TESTING == True
    
    def test_testing_csrf_disabled(self):
        assert TestingConfig.WTF_CSRF_ENABLED == False
    

class TestProductionConfig:
    """Tests for ProductionConfig"""
    
    def test_production_ssl_redirect_enabled(self):
        assert ProductionConfig.SSL_REDIRECT == True
    
    def test_production_init_app(self):
        from unittest.mock import Mock
        app = Mock()
        ProductionConfig.init_app(app)
        # Should not raise exception


class TestDockerConfig:
    """Tests for DockerConfig"""
    
    def test_docker_inherits_from_production(self):
        assert issubclass(DockerConfig, ProductionConfig)
    
    def test_docker_init_app(self):
        from unittest.mock import Mock
        app = Mock()
        DockerConfig.init_app(app)


class TestHerokuConfig:
    """Tests for HerokuConfig"""
    
    def test_heroku_inherits_from_production(self):
        assert issubclass(HerokuConfig, ProductionConfig)


class TestUnixConfig:
    """Tests for UnixConfig"""
    
    def test_unix_inherits_from_production(self):
        assert issubclass(UnixConfig, ProductionConfig)


class TestConfigDict:
    """Tests for config dictionary"""
    
    def test_config_dict_has_all_environments(self):
        assert 'development' in config
        assert 'testing' in config
        assert 'production' in config
        assert 'docker' in config
        assert 'heroku' in config
        assert 'unix' in config
        assert 'default' in config
    
    def test_config_default_is_development(self):
        assert config['default'] == DevelopmentConfig
    
    def test_config_values_are_classes(self):
        for key, value in config.items():
            assert isinstance(value, type)
            assert issubclass(value, Config)


class TestConfigEnvironmentVariables:
    """Tests for environment variable handling"""
    
    def test_secret_key_from_env(self, monkeypatch):
        test_key = 'test-secret-key-123'
        monkeypatch.setenv('SECRET_KEY', test_key)
        # Reload config
        from importlib import reload
        import config as config_module
        reload(config_module)
        assert config_module.Config.SECRET_KEY == test_key
    
    def test_flask_port_from_env(self, monkeypatch):
        monkeypatch.setenv('FLASK_PORT', '8080')
        from importlib import reload
        import config as config_module
        reload(config_module)
        assert config_module.Config.T2P_FLASK_PORT == 8080
    
    def test_flask_host_from_env(self, monkeypatch):
        test_host = '0.0.0.0'
        monkeypatch.setenv('FLASK_HOST', test_host)
        from importlib import reload
        import config as config_module
        reload(config_module)
        assert config_module.Config.T2P_FLASK_HOST == test_host
