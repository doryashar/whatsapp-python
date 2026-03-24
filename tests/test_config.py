import os
import pytest
from pydantic import ValidationError
from unittest.mock import patch


class TestSettingsDefaults:
    def test_default_host(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.host == "0.0.0.0"

    def test_default_port(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.port == 8080

    def test_default_debug(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.debug is False

    def test_default_base_url(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.base_url == "http://localhost:8080"

    def test_default_max_messages(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.max_messages == 1000

    def test_default_auto_login(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.auto_login is True

    def test_default_webhook_urls(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.webhook_urls == []

    def test_default_webhook_secret(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.webhook_secret == ""

    def test_default_webhook_timeout(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.webhook_timeout == 30

    def test_default_webhook_retries(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.webhook_retries == 3

    def test_default_rate_limit_per_minute(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.rate_limit_per_minute == 60

    def test_default_rate_limit_per_hour(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.rate_limit_per_hour == 1000

    def test_default_health_check_interval(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.health_check_interval_seconds == 30

    def test_default_bridge_timeout(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.bridge_timeout_seconds == 60

    def test_default_admin_log_buffer_size(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.admin_log_buffer_size == 2000

    def test_default_cors_origins(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.cors_origins == []

    def test_default_trusted_proxies(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert "10.0.0.0/8" in s.trusted_proxies
        assert "172.16.0.0/12" in s.trusted_proxies
        assert "192.168.0.0/16" in s.trusted_proxies

    def test_default_service_name(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.service_name == "whatsapp-api"

    def test_default_service_version(self):
        from src.config import Settings

        s = Settings(_env_file=None)
        assert s.service_version == "2.0.0"


class TestSettingsEnvOverride:
    def test_env_host_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("HOST", "127.0.0.1")
        s = Settings()
        assert s.host == "127.0.0.1"

    def test_env_port_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("PORT", "3000")
        s = Settings()
        assert s.port == 3000

    def test_env_debug_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("DEBUG", "true")
        s = Settings()
        assert s.debug is True

    def test_env_database_url(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        s = Settings()
        assert s.database_url == "postgresql://user:pass@localhost/db"

    def test_env_admin_password(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("ADMIN_PASSWORD", "secret123")
        s = Settings()
        assert s.admin_password == "secret123"

    def test_env_webhook_urls_json(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("WEBHOOK_URLS", '["http://example.com/hook"]')
        s = Settings()
        assert s.webhook_urls == ["http://example.com/hook"]


class TestSettingsSecurityValidation:
    def test_production_requires_database_url(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError):
            Settings()

    def test_staging_requires_database_url(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(ValidationError):
            Settings()

    def test_development_allows_no_database(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        s = Settings()
        assert s.database_url == ""

    def test_admin_log_buffer_size_minimum(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("ADMIN_LOG_BUFFER_SIZE", "0")
        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_port(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("PORT", "not_a_number")
        with pytest.raises(ValidationError):
            Settings()

    def test_non_numeric_port(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("PORT", "not_a_number")
        with pytest.raises(ValidationError):
            Settings()

    def test_port_accepts_zero(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("PORT", "0")
        s = Settings()
        assert s.port == 0
