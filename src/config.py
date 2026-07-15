"""
Configuration management for AI News Bot
"""
import os
import yaml
from typing import Dict, List, Any, Optional
from pathlib import Path
from dotenv import load_dotenv
from .logger import setup_logger


logger = setup_logger(__name__)


# Env var holding the API key for each supported LLM provider
PROVIDER_API_KEY_VARS = {
    "claude": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "grok": "XAI_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# Env vars each notifier requires (must match what the notifier classes read)
NOTIFIER_REQUIRED_VARS = {
    "email": ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "EMAIL_TO"),
    "webhook": ("WEBHOOK_URL",),
    "slack": ("SLACK_WEBHOOK_URL",),
    "telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
    "discord": ("DISCORD_WEBHOOK_URL",),
}


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


class Config:
    """Application configuration manager"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config.yaml file. If None, searches for it in default locations
        """
        # Load environment variables from .env file
        load_dotenv(override=True)

        # Find and load YAML config
        self.config_path = self._find_config_file(config_path)
        self.config_data = self._load_yaml_config()

        logger.info(f"Configuration loaded from {self.config_path}")

    def _find_config_file(self, config_path: Optional[str] = None) -> Path:
        """
        Find the configuration file.

        Args:
            config_path: Explicit path to config file

        Returns:
            Path to configuration file

        Raises:
            FileNotFoundError: If config file cannot be found
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Search in default locations
        search_paths = [
            Path("config.yaml"),
            Path("config.yml"),
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent.parent / "config.yml",
        ]

        for path in search_paths:
            if path.exists():
                return path

        raise FileNotFoundError(
            "Config file not found. Searched: " + ", ".join(str(p) for p in search_paths)
        )

    def _load_yaml_config(self) -> Dict[str, Any]:
        """
        Load YAML configuration file.

        Returns:
            Configuration dictionary
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config or {}
        except Exception as e:
            logger.error(f"Failed to load config file: {str(e)}")
            return {}

    @property
    def news_topics(self) -> List[str]:
        """Get list of news topics to cover"""
        return self.config_data.get("news", {}).get("topics", [
            "Latest AI developments and breakthroughs"
        ])

    @property
    def stage1_prompt_template(self) -> str:
        """Get the Stage 1 selection prompt template"""
        default_template = """{formatted_news}

## YOUR TASK - STAGE 1: NEWS SELECTION

You are a senior AI industry analyst. Analyze the {total_items} news items above and select exactly 15-20 of the highest-quality items.

### SELECTION CRITERIA:
- ✅ Groundbreaking research or technical breakthroughs
- ✅ Major product launches or significant updates
- ✅ Important policy changes or regulations
- ✅ Large funding rounds or M&A activities
- ✅ Balanced coverage across categories (LLM, Agents, Research, Products, etc.)
- ✅ Prefer primary sources over secondary reporting

### OUTPUT FORMAT:
Return ONLY a JSON array of selected news IDs. No explanations, no markdown, just the JSON array.

Example format:
["INT-1", "INT-5", "INT-12", ...]

CRITICAL: Select exactly 15-20 items. No more, no less."""

        return self.config_data.get("news", {}).get("stage1_prompt_template", default_template)

    @property
    def stage2_prompt_template(self) -> str:
        """Get the Stage 2 summarization prompt template"""
        default_template = """You are a senior AI industry analyst. Create a comprehensive, in-depth news digest for the {count} pre-selected news items below.

{selected_news}

## OUTPUT STRUCTURE:

Organize news items into relevant categories (use only categories that have news):
1. **Large Language Models & Foundation Models**
3. **Product Launches & Updates**
4. **AI Infrastructure & Hardware**
5. **Funding & Market Dynamics**
6. **Policy & Regulation**
7. **AI in Finance & Banking**

## CONTENT REQUIREMENTS:

For each news item:
- **Clear Headline**: Informative title
- **Analytical Summary (4-6 sentences)**: What happened, technical details, why it matters, implications
- **Source Attribution**: [Source Name](URL)

## WRITING STYLE:
- Professional, analytical tone
- Include specific metrics and data
- Technical accuracy
- Context and analysis

## QUALITY REQUIREMENTS:
- ✅ Summarize ALL {count} items (no skipping)
- ✅ Each summary exactly 4-6 sentences
- ✅ Include specific numbers and data
- ✅ Balanced coverage across categories
- ✅ All sources as clickable markdown links

## AVOID:
❌ Generic statements
❌ Wrong summary length
❌ Missing links
❌ Skipping items"""

        return self.config_data.get("news", {}).get("stage2_prompt_template", default_template)

    @property
    def log_level(self) -> str:
        """Get logging level"""
        return self.config_data.get("logging", {}).get("level", "INFO")

    @property
    def log_format(self) -> str:
        """Get logging format"""
        return self.config_data.get("logging", {}).get(
            "format",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    @property
    def notification_methods(self) -> List[str]:
        """Get enabled notification methods from environment"""
        methods_str = os.getenv("NOTIFICATION_METHODS", "")
        if not methods_str:
            return []
        return [m.strip().lower() for m in methods_str.split(",")]

    @property
    def dry_run(self) -> bool:
        """Dry-run mode: render the digest to files under output/ and send nothing."""
        return os.getenv("DRY_RUN", "false").strip().lower() in ("true", "1", "yes", "on")

    @property
    def max_items_per_source(self) -> int:
        """Maximum news items to fetch per source"""
        return self.config_data.get("news", {}).get("max_items_per_source", 10)

    @property
    def max_total_items(self) -> Optional[int]:
        """Optional cap on total international items sent to Stage 1 (None = no cap)"""
        return self.config_data.get("news", {}).get("max_total_items", 150)

    @property
    def max_output_tokens(self) -> int:
        """Max output tokens for the Stage-2 digest. Must be large enough for all
        selected items or the JSON is truncated and rendering falls back to raw text."""
        return self.config_data.get("news", {}).get("max_output_tokens", 16000)

    @property
    def lookback_hours(self) -> int:
        """How many hours back to keep news items (items with no date are kept)"""
        return self.config_data.get("news", {}).get("lookback_hours", 48)

    @property
    def blocked_sources(self) -> List[str]:
        """Publisher domains/names whose items are dropped at fetch time"""
        value = self.config_data.get("news", {}).get("blocked_sources", [])
        return [str(v) for v in value] if isinstance(value, list) else []

    @property
    def history_enabled(self) -> bool:
        """Whether to track already-covered stories across runs"""
        return bool(self.config_data.get("news", {}).get("history", {}).get("enabled", True))

    @property
    def history_path(self) -> str:
        """Path to the committed cross-run history JSON file"""
        return self.config_data.get("news", {}).get("history", {}).get("path", "data/news_history.json")

    @property
    def history_retention_days(self) -> int:
        """How many days a covered story stays in the history before expiring"""
        return int(self.config_data.get("news", {}).get("history", {}).get("retention_days", 7))

    @property
    def history_prompt_days(self) -> int:
        """How many days of published headlines to inject into the Stage-1 prompt"""
        return int(self.config_data.get("news", {}).get("history", {}).get("prompt_days", 3))

    @property
    def llm_provider(self) -> str:
        """Get the LLM provider to use (claude or deepseek)"""
        # Check environment variable first, then config file
        env_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if env_provider:
            return env_provider
        return self.config_data.get("llm", {}).get("provider", "claude").lower()

    @property
    def llm_model(self) -> Optional[str]:
        """Get the specific model to use (if specified)"""
        # Check environment variable first, then config file
        env_model = os.getenv("LLM_MODEL", "").strip()
        if env_model:
            return env_model
        return self.config_data.get("llm", {}).get("model")

    @property
    def llm_api_key(self) -> Optional[str]:
        """Get the API key for the LLM provider"""
        # Check environment variables based on provider
        provider = self.llm_provider
        if provider == "deepseek":
            return os.getenv("DEEPSEEK_API_KEY")
        elif provider == "claude":
            return os.getenv("ANTHROPIC_API_KEY")
        elif provider == "gemini":
            return os.getenv("GOOGLE_API_KEY")
        elif provider == "grok":
            return os.getenv("XAI_API_KEY")
        elif provider == "openai":
            return os.getenv("OPENAI_API_KEY")
        return None

    def validate(self) -> None:
        """Fail fast on missing or invalid settings, before any feed fetching
        or LLM spend. Collects every problem and raises a single ConfigError,
        so one failed run surfaces the complete list instead of the first item.

        In dry-run mode notifier checks are skipped (nothing is sent), but the
        LLM key is still required.
        """
        problems: List[str] = []

        provider = self.llm_provider
        key_var = PROVIDER_API_KEY_VARS.get(provider)
        if key_var is None:
            problems.append(
                f"Unknown LLM provider '{provider}'. "
                f"Supported: {', '.join(sorted(PROVIDER_API_KEY_VARS))}"
            )
        elif not (os.getenv(key_var) or "").strip():
            problems.append(
                f"{key_var} is not set (required by LLM provider '{provider}')"
            )

        if not self.dry_run:
            methods = [m for m in self.notification_methods if m]
            if not methods:
                problems.append(
                    "NOTIFICATION_METHODS is empty: the digest would be generated "
                    "but sent nowhere. Enable at least one method, or set "
                    "DRY_RUN=true to render to output/ instead."
                )
            for method in methods:
                required = NOTIFIER_REQUIRED_VARS.get(method)
                if required is None:
                    problems.append(
                        f"Unknown notification method '{method}'. "
                        f"Supported: {', '.join(sorted(NOTIFIER_REQUIRED_VARS))}"
                    )
                    continue
                missing = [v for v in required if not (os.getenv(v) or "").strip()]
                if missing:
                    problems.append(
                        f"Notification method '{method}' is enabled but missing: "
                        f"{', '.join(missing)}"
                    )

        if problems:
            raise ConfigError(
                "Invalid configuration:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.

        Args:
            key: Dot-separated key path (e.g., "news.topics")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self.config_data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

            if value is None:
                return default

        return value
