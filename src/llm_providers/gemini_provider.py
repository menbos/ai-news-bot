"""
Gemini Provider - Google Gemini API implementation (google-genai SDK)
"""
import os
import random
import time
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from .base_provider import BaseLLMProvider
from ..logger import setup_logger


logger = setup_logger(__name__)

# Transient errors worth retrying: 503 (overloaded) and 429 (rate limited).
_RETRYABLE_STATUS = {429, 503}
_MAX_ATTEMPTS = 5

# Sibling model to fall back to when the primary keeps returning a transient
# (503/429) error after exhausting retries. flash-lite is the lowest-capacity
# free tier and sheds heavy requests first during demand spikes; flash has a
# separate capacity pool, so a fallback there often succeeds when lite is
# overloaded. Pro is paid-only (since 2026-04-01), so it is not a free-tier
# fallback. The fallback uses the same free tier and works without billing.
_FALLBACK_MODELS = {
    "gemini-2.5-flash-lite": "gemini-2.5-flash",
}


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Gemini provider.

        Args:
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var
            model: Model name to use. If None, uses default model

        Raises:
            ValueError: If API key is not provided and not in environment
        """
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Google API key must be provided or set in GOOGLE_API_KEY environment variable"
            )

        super().__init__(api_key=api_key, model=model or self.default_model)

        # Configure Gemini API client (google-genai SDK)
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"Gemini provider initialized with model: {self.model}")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return "gemini-2.5-flash-lite"

    def _build_config(
        self, max_tokens: int, temperature: float, model: str
    ) -> "types.GenerateContentConfig":
        """Build the request config, disabling 'thinking' on 2.5 flash models.

        Gemini 2.5 models spend part of ``max_output_tokens`` on internal
        thinking. That can truncate the actual JSON we asked for, which then
        gets dumped into the digest as a raw dict. Disabling thinking
        (``thinking_budget=0``) gives the whole budget to real output. Pro has a
        non-zero minimum thinking budget, so it is left untouched. Keyed on the
        per-call ``model`` so a flash fallback gets the right config too.
        """
        kwargs: Dict[str, Any] = dict(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        name = (model or "").lower()
        if name.startswith("gemini-2.5") and "pro" not in name:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def _describe_empty_response(response: Any) -> str:
        """Explain why ``response.text`` came back empty.

        The SDK returns an empty/None ``.text`` both when the prompt was
        blocked outright (``prompt_feedback.block_reason``) and when a
        candidate was generated but its content was withheld (candidate
        ``finish_reason`` of SAFETY/RECITATION/PROHIBITED_CONTENT/etc, with no
        MAX_TOKENS handled separately in ``_raise_if_truncated``). Neither case
        raises an APIError, so without this the failure just looks like "no
        response" with no way to tell a safety block from an SDK/network hiccup.
        """
        parts = []
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None)
        if block_reason:
            parts.append(f"prompt blocked: {block_reason}")
            block_message = getattr(feedback, "block_reason_message", None)
            if block_message:
                parts.append(f"({block_message})")

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            parts.append("no candidates returned")
        else:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            if finish_reason:
                parts.append(f"finish_reason={finish_reason}")
            safety_ratings = getattr(candidates[0], "safety_ratings", None) or []
            flagged = [
                f"{getattr(r, 'category', '?')}={getattr(r, 'probability', '?')}"
                for r in safety_ratings
                if getattr(r, "probability", None) not in (None, "NEGLIGIBLE", "LOW")
            ]
            if flagged:
                parts.append(f"safety_ratings=[{', '.join(flagged)}]")

        return f" ({'; '.join(parts)})" if parts else ""

    @staticmethod
    def _raise_if_truncated(response: Any) -> None:
        """Raise if Gemini stopped because it hit the output-token limit.

        A MAX_TOKENS finish means the text is cut off mid-output (e.g. an
        unterminated JSON array). Returning it would feed a truncated response
        downstream, so fail loudly instead. This is not retryable — retrying the
        same prompt/budget truncates again — so callers should treat it as fatal.
        """
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return
        finish_reason = getattr(candidates[0], "finish_reason", None)
        name = getattr(finish_reason, "name", str(finish_reason)) if finish_reason else ""
        if name == "MAX_TOKENS":
            raise Exception(
                "Gemini response truncated at max_output_tokens; increase "
                "news.max_output_tokens or shorten the prompt."
            )

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 1.0,
        **kwargs
    ) -> str:
        """
        Generate a response using the Gemini API.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional Gemini-specific parameters

        Returns:
            Generated text response

        Raises:
            Exception: If API call fails
        """
        prompt = self._convert_messages_to_prompt(messages)

        # Try the primary model, then a sibling fallback if it keeps returning a
        # transient error. flash-lite overload (503) is the common failure, and
        # flash draws from separate capacity, so the fallback often succeeds.
        models = [self.model]
        fallback = _FALLBACK_MODELS.get((self.model or "").lower())
        if fallback and fallback != self.model:
            models.append(fallback)

        last_error: Optional[Exception] = None
        for index, model in enumerate(models):
            config = self._build_config(max_tokens, temperature, model)
            try:
                return self._generate_with_retries(prompt, config, model)
            except genai_errors.APIError as e:
                last_error = e
                # Advance to the fallback model only on transient overload/limit.
                is_last = index == len(models) - 1
                if getattr(e, "code", None) in _RETRYABLE_STATUS and not is_last:
                    logger.warning(
                        f"Gemini model '{model}' still {e.code} after "
                        f"{_MAX_ATTEMPTS} attempts; falling back to '{models[index + 1]}'"
                    )
                    continue
                raise

        # Should be unreachable (loop either returns or raises), but keep a guard.
        raise last_error

    def _generate_with_retries(
        self, prompt: str, config: "types.GenerateContentConfig", model: str
    ) -> str:
        """Call one Gemini model, retrying transient 503/429 with jittered backoff."""
        last_error: Optional[Exception] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                logger.debug(f"Calling Gemini API model='{model}' (attempt {attempt}/{_MAX_ATTEMPTS})")
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                self._raise_if_truncated(response)
                if response.text:
                    return response.text
                raise Exception(
                    "No response received from Gemini"
                    + self._describe_empty_response(response)
                )

            except genai_errors.APIError as e:
                # Retry transient overload/rate-limit responses with backoff.
                # Jitter spreads retries so concurrent runs don't resync onto the
                # same overloaded window.
                if getattr(e, "code", None) in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS:
                    wait = min(2 ** attempt, 30) + random.uniform(0, 1)
                    last_error = e
                    logger.warning(
                        f"Gemini {e.code} on '{model}' (attempt {attempt}/{_MAX_ATTEMPTS}); "
                        f"retrying in {wait:.1f}s"
                    )
                    time.sleep(wait)
                    continue
                logger.error(f"Gemini API error on '{model}': {str(e)}", exc_info=True)
                raise

        # Exhausted retries on a transient error.
        logger.error(f"Gemini '{model}' still failing after {_MAX_ATTEMPTS} attempts: {last_error}")
        raise last_error

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 2000,
        max_iterations: int = 8,
        tool_handler: Optional[callable] = None,
        **kwargs
    ) -> str:
        """
        Tool-calling is not implemented for Gemini; falls back to plain generation.
        Retained to satisfy the BaseLLMProvider interface.
        """
        logger.debug("Gemini generate_with_tools: tools unsupported, using plain generate")
        return self.generate(messages, max_tokens=max_tokens, **kwargs)

    def _convert_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """
        Flatten standard role/content messages into a single prompt string.

        Gemini's single-turn generate_content takes plain text; the bot only ever
        sends one user message per call, so a simple role-prefixed join is enough.
        """
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        return "\n\n".join(prompt_parts)
