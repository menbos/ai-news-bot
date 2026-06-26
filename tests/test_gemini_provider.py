"""Tests for GeminiProvider config + truncation guards (no API key needed)."""
import types as pytypes
from typing import Optional

import pytest

from src.llm_providers.gemini_provider import GeminiProvider


def _bare_provider(model: str) -> GeminiProvider:
    # Bypass __init__ so we don't need an API key or a live client.
    p = GeminiProvider.__new__(GeminiProvider)
    p.model = model
    return p


def _fake_response(finish_reason_name: Optional[str]):
    """Minimal stand-in for a google-genai response with one candidate."""
    finish = pytypes.SimpleNamespace(name=finish_reason_name) if finish_reason_name else None
    candidate = pytypes.SimpleNamespace(finish_reason=finish)
    return pytypes.SimpleNamespace(candidates=[candidate], text="partial")


def test_build_config_disables_thinking_on_flash_lite():
    cfg = _bare_provider("gemini-2.5-flash-lite")._build_config(16000, 1.0)
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0
    assert cfg.max_output_tokens == 16000


def test_build_config_leaves_pro_thinking_untouched():
    cfg = _bare_provider("gemini-2.5-pro")._build_config(16000, 1.0)
    assert cfg.thinking_config is None


def test_raise_if_truncated_raises_on_max_tokens():
    with pytest.raises(Exception, match="truncated"):
        GeminiProvider._raise_if_truncated(_fake_response("MAX_TOKENS"))


def test_raise_if_truncated_passes_on_normal_stop():
    # STOP / no candidates must not raise.
    GeminiProvider._raise_if_truncated(_fake_response("STOP"))
    GeminiProvider._raise_if_truncated(pytypes.SimpleNamespace(candidates=[]))
