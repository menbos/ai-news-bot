"""Tests for startup config validation (Config.validate)."""
import pytest

from src.config import Config, ConfigError, NOTIFIER_REQUIRED_VARS, PROVIDER_API_KEY_VARS


# Every env var validate() reads; scrubbed so the developer's real .env
# (loaded with override=True in Config.__init__) can't leak into tests.
_ALL_VARS = (
    ["LLM_PROVIDER", "LLM_MODEL", "NOTIFICATION_METHODS", "AI_RESPONSE_LANGUAGE", "DRY_RUN"]
    + list(PROVIDER_API_KEY_VARS.values())
    + [v for group in NOTIFIER_REQUIRED_VARS.values() for v in group]
)


@pytest.fixture
def cfg(monkeypatch):
    """A Config with a clean env and a minimal valid setup (gemini + email)."""
    config = Config()  # constructed first: __init__ re-loads .env over the env
    for var in _ALL_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("NOTIFICATION_METHODS", "email")
    monkeypatch.setenv("GMAIL_ADDRESS", "bot@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")
    return config


def test_valid_config_passes(cfg):
    cfg.validate()


def test_missing_llm_key(cfg, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        cfg.validate()


def test_llm_key_names_match_selected_provider(cfg, monkeypatch):
    for provider, key_var in PROVIDER_API_KEY_VARS.items():
        monkeypatch.setenv("LLM_PROVIDER", provider)
        monkeypatch.delenv(key_var, raising=False)
        with pytest.raises(ConfigError, match=key_var):
            cfg.validate()
        monkeypatch.setenv(key_var, "test-key")
        cfg.validate()


def test_unknown_llm_provider(cfg, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    with pytest.raises(ConfigError, match="Unknown LLM provider 'llama'"):
        cfg.validate()


def test_missing_notifier_credentials(cfg, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_METHODS", "telegram")
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN.*TELEGRAM_CHAT_ID"):
        cfg.validate()


def test_unknown_notification_method(cfg, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_METHODS", "email,pigeon")
    with pytest.raises(ConfigError, match="Unknown notification method 'pigeon'"):
        cfg.validate()


def test_no_notification_methods_fails_outside_dry_run(cfg, monkeypatch):
    monkeypatch.setenv("NOTIFICATION_METHODS", "")
    with pytest.raises(ConfigError, match="NOTIFICATION_METHODS is empty"):
        cfg.validate()


def test_dry_run_skips_notifier_checks(cfg, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("NOTIFICATION_METHODS", "")
    cfg.validate()


def test_dry_run_still_requires_llm_key(cfg, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("GOOGLE_API_KEY")
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        cfg.validate()


def test_language_with_no_supported_code_fails(cfg, monkeypatch):
    monkeypatch.setenv("AI_RESPONSE_LANGUAGE", "fr,es")
    with pytest.raises(ConfigError, match="AI_RESPONSE_LANGUAGE"):
        cfg.validate()


def test_language_with_one_supported_code_passes(cfg, monkeypatch):
    monkeypatch.setenv("AI_RESPONSE_LANGUAGE", "en,fr")
    cfg.validate()
    monkeypatch.setenv("AI_RESPONSE_LANGUAGE", "zh")
    cfg.validate()


def test_all_problems_reported_at_once(cfg, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    monkeypatch.setenv("NOTIFICATION_METHODS", "telegram")
    with pytest.raises(ConfigError) as exc_info:
        cfg.validate()
    message = str(exc_info.value)
    assert "GOOGLE_API_KEY" in message
    assert "TELEGRAM_BOT_TOKEN" in message
