#!/usr/bin/env python3
"""
AI News Bot - Main Application

Generates and distributes daily AI news digests using Anthropic's Claude API.
"""
import sys
from pathlib import Path
from datetime import datetime
from src.config import Config, ConfigError
from src.logger import setup_logger
from src.news import NewsGenerator
from src.news.history import NewsHistory
from src.notifiers import (
    EmailNotifier,
    WebhookNotifier,
    SlackNotifier,
    TelegramNotifier,
    DiscordNotifier
)


def write_dry_run_output(content: str) -> tuple:
    """Render the digest to output/digest.{md,html} and send nothing.

    The HTML is produced by the real email renderer, so the file is exactly what
    recipients would have received. Returns the (markdown_path, html_path) written.
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"AI News Digest - {today}"

    md_path = out_dir / "digest.md"
    html_path = out_dir / "digest.html"

    md_path.write_text(content, encoding="utf-8")
    # Placeholder creds avoid the "not configured" warning; rendering needs none.
    renderer = EmailNotifier(gmail_address="dry@run", gmail_app_password="x", email_to="dry@run")
    html_path.write_text(renderer._create_html_email(content, subject), encoding="utf-8")

    return md_path, html_path


def main():
    """Main application entry point"""
    try:
        # Load configuration
        config = Config()

        # Setup logger with config
        logger = setup_logger(
            "ai_news_bot",
            level=config.log_level,
            log_format=config.log_format
        )

        # Fail fast on bad config before any feed fetching or LLM spend
        try:
            config.validate()
        except ConfigError as e:
            logger.error(str(e))
            return 1

        logger.info("=" * 60)
        logger.info("AI News Bot Starting")
        logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"LLM Provider: {config.llm_provider}")
        if config.llm_model:
            logger.info(f"LLM Model: {config.llm_model}")
        if config.dry_run:
            logger.info("DRY RUN enabled: digest renders to output/ and nothing is sent")
        logger.info("=" * 60)

        # Initialize cross-run "already covered" memory (committed back by CI).
        # Skipped in dry-run so a test never mutates the history file.
        history = None
        if config.history_enabled and not config.dry_run:
            history = NewsHistory(
                path=config.history_path,
                retention_days=config.history_retention_days,
                prompt_days=config.history_prompt_days,
            )
            logger.info(f"Cross-run history enabled at {config.history_path}")

        # Initialize news generator
        logger.info("Initializing news generator...")
        news_gen = NewsGenerator(
            provider_name=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            lookback_hours=config.lookback_hours,
            history=history,
            blocked_sources=config.blocked_sources
        )

        # Get enabled notification methods
        notification_methods = config.notification_methods
        logger.info(f"Enabled notification methods: {notification_methods}")

        # Generate news digest
        logger.info("Generating AI news digest from real-time sources...")
        news_digest = news_gen.generate_news_digest_from_sources(
            max_tokens=config.max_output_tokens,
            max_items_per_source=config.max_items_per_source,
            max_total_items=config.max_total_items,
            stage1_template=config.stage1_prompt_template,
            stage2_template=config.stage2_prompt_template
        )

        logger.info(f"News digest generated ({len(news_digest)} characters)")
        logger.info("-" * 60)
        logger.info("News Digest Preview:")
        logger.info("-" * 60)
        # Print first 500 characters as preview
        preview = news_digest[:500] + "..." if len(news_digest) > 500 else news_digest
        logger.info(preview)
        logger.info("-" * 60)

        # Dry run: render to files, send nothing to the distribution list.
        if config.dry_run:
            md_path, html_path = write_dry_run_output(news_digest)
            logger.info(f"DRY RUN: wrote {md_path} and {html_path} (no notifications sent)")
            logger.info("=" * 60)
            logger.info("AI News Bot Completed")
            logger.info("=" * 60)
            return 0

        # Track notification results
        results = {"sent": [], "failed": []}

        notifiers = {
            "email": EmailNotifier,
            "webhook": WebhookNotifier,
            "slack": SlackNotifier,
            "telegram": TelegramNotifier,
            "discord": DiscordNotifier,
        }

        for method, notifier_class in notifiers.items():
            if method not in notification_methods:
                continue
            logger.info(f"Sending {method} notification...")
            notifier = notifier_class()
            if notifier.send(news_digest):
                results["sent"].append(method)
                logger.info(f"{method.capitalize()} notification sent successfully")
            else:
                results["failed"].append(method)
                logger.warning(f"{method.capitalize()} notification failed")

        # Final Summary
        logger.info("=" * 60)
        logger.info("AI News Bot Completed")
        logger.info(f"Successfully sent: {', '.join(results['sent']) if results['sent'] else 'None'}")
        if results["failed"]:
            logger.warning(f"Failed to send: {', '.join(results['failed'])}")
        logger.info("=" * 60)

        # Return exit code based on results
        if notification_methods and not results["sent"]:
            logger.error("All notifications failed")
            return 1

        return 0

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"Application error: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
