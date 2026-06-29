"""Tests for GeminiProvider config + truncation guards (no API key needed)."""
import types as pytypes
from typing import Optional

import pytest

from google.genai import errors as genai_errors

from src.llm_providers.gemini_provider import GeminiProvider


def _bare_provider(model: str) -> GeminiProvider:
    # Bypass __init__ so we don't need an API key or a live client.
    p = GeminiProvider.__new__(GeminiProvider)
    p.model = model
    return p


def _api_error(code: int) -> genai_errors.APIError:
    # Build an APIError with a .code without going through its response-parsing
    # __init__ (which needs a live HTTP response object).
    e = genai_errors.APIError.__new__(genai_errors.APIError)
    e.code = code
    e.message = f"status {code}"
    return e


def _fake_response(finish_reason_name: Optional[str]):
    """Minimal stand-in for a google-genai response with one candidate."""
    finish = pytypes.SimpleNamespace(name=finish_reason_name) if finish_reason_name else None
    candidate = pytypes.SimpleNamespace(finish_reason=finish)
    return pytypes.SimpleNamespace(candidates=[candidate], text="partial")


def test_build_config_disables_thinking_on_flash_lite():
    p = _bare_provider("gemini-2.5-flash-lite")
    cfg = p._build_config(16000, 1.0, p.model)
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0
    assert cfg.max_output_tokens == 16000


def test_build_config_leaves_pro_thinking_untouched():
    p = _bare_provider("gemini-2.5-pro")
    cfg = p._build_config(16000, 1.0, p.model)
    assert cfg.thinking_config is None


def test_build_config_disables_thinking_on_flash_fallback():
    # The flash fallback (a 2.5 non-pro model) must also get thinking disabled,
    # even when the provider's primary model differs.
    p = _bare_provider("gemini-2.5-flash-lite")
    cfg = p._build_config(16000, 1.0, "gemini-2.5-flash")
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0


def test_raise_if_truncated_raises_on_max_tokens():
    with pytest.raises(Exception, match="truncated"):
        GeminiProvider._raise_if_truncated(_fake_response("MAX_TOKENS"))


def test_raise_if_truncated_passes_on_normal_stop():
    # STOP / no candidates must not raise.
    GeminiProvider._raise_if_truncated(_fake_response("STOP"))
    GeminiProvider._raise_if_truncated(pytypes.SimpleNamespace(candidates=[]))


def test_generate_falls_back_to_flash_on_persistent_503(monkeypatch):
    # flash-lite exhausts retries on 503 -> generate() should retry on flash.
    p = _bare_provider("gemini-2.5-flash-lite")
    calls = []

    def fake(prompt, config, model):
        calls.append(model)
        if model == "gemini-2.5-flash-lite":
            raise _api_error(503)
        return "ok from flash"

    monkeypatch.setattr(p, "_generate_with_retries", fake)
    out = p.generate([{"role": "user", "content": "hi"}], max_tokens=100)
    assert out == "ok from flash"
    assert calls == ["gemini-2.5-flash-lite", "gemini-2.5-flash"]


def test_generate_does_not_fall_back_on_non_transient_error(monkeypatch):
    # A 400 is not retryable and must not trigger the fallback model.
    p = _bare_provider("gemini-2.5-flash-lite")
    calls = []

    def fake(prompt, config, model):
        calls.append(model)
        raise _api_error(400)

    monkeypatch.setattr(p, "_generate_with_retries", fake)
    with pytest.raises(genai_errors.APIError):
        p.generate([{"role": "user", "content": "hi"}], max_tokens=100)
    assert calls == ["gemini-2.5-flash-lite"]
