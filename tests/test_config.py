import pytest

from riff.config import ConfigurationError, Settings


def test_settings_accepts_postgres_url_without_logging_or_normalizing_secret():
    settings = Settings.from_env(
        {
            "RIFF_DATABASE_URL": "postgresql://user:secret@localhost:5432/riff",
            "RIFF_ENV": "test",
            "RIFF_LOG_LEVEL": "debug",
            "RIFF_MCP_ALLOWED_HOSTS": "riff.example.com,localhost:8000",
            "RIFF_MCP_ALLOWED_ORIGINS": "https://chatgpt.com",
        }
    )
    assert settings.database_url.endswith("/riff")
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.mcp_allowed_hosts == ("riff.example.com", "localhost:8000")
    assert settings.mcp_allowed_origins == ("https://chatgpt.com",)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"RIFF_DATABASE_URL": "sqlite:///riff.db"},
        {"RIFF_DATABASE_URL": "postgresql://"},
    ],
)
def test_settings_reject_missing_or_invalid_database_url(values):
    with pytest.raises(ConfigurationError, match="RIFF_DATABASE_URL"):
        Settings.from_env(values)
