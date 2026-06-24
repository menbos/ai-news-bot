"""
Gemini Provider - Google Gemini API implementation (google-genai SDK)
"""
import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from .base_provider import BaseLLMProvider
from ..logger import setup_logger


logger = setup_logger(__name__)


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
        try:
            logger.debug(f"Calling Gemini API with {len(messages)} messages")

            prompt = self._convert_messages_to_prompt(messages)

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )

            if response.text:
                return response.text

            raise Exception("No response received from Gemini")

        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}", exc_info=True)
            raise

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
