#!/usr/bin/env python3
"""
AI News Bot - Main Application

Generates and distributes daily AI news digests using Anthropic's Claude API.
"""
import sys
from pathlib import Path
from datetime import datetime
from src.config import Config
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


def write_dry_run_output(content: str, language: str) -> tuple:
    """Render the digest to output/digest_<lang>.{md,html} and send nothing.

    The HTML is produced by the real email renderer, so the file is exactly what
    recipients would have received. Returns the (markdown_path, html_path) written.
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    lang_suffix = f" [{language.upper()}]" if language != "en" else ""
    subject = f"AI News Digest - {today}{lang_suffix}"

    md_path = out_dir / f"digest_{language}.md"
    html_path = out_dir / f"digest_{language}.html"

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

        # Get list of languages to process
        languages = config.ai_response_languages
        
        logger.info("=" * 60)
        logger.info("AI News Bot Starting")
        logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"LLM Provider: {config.llm_provider}")
        if config.llm_model:
            logger.info(f"LLM Model: {config.llm_model}")
        logger.info(f"Languages: {', '.join(languages)}")
        if config.dry_run:
            logger.info("DRY RUN enabled: digests render to output/ and nothing is sent")
        logger.info("=" * 60)

        # Initialize cross-run "already covered" memory (committed back by CI).
        # Skipped in dry-run so a test never mutates the history file.
        history = None
        if config.history_enabled and not config.dry_run:
            history = NewsHistory(
                path=config.history_path,
                retention_days=config.history_retention_days,
            )
            logger.info(f"Cross-run history enabled at {config.history_path}")

        # Initialize news generator once
        logger.info("Initializing news generator...")
        news_gen = NewsGenerator(
            provider_name=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            lookback_hours=config.lookback_hours,
            history=history
        )

        # Get enabled notification methods
        notification_methods = config.notification_methods
        logger.info(f"Enabled notification methods: {notification_methods}")

        # Track overall results
        overall_results = {"sent": [], "failed": []}
        
        # Process each language
        for language in languages:
            logger.info("=" * 60)
            logger.info(f"Processing language: {language.upper()}")
            logger.info("=" * 60)

            try:
                # Generate news digest for this language
                logger.info(f"Generating AI news digest in {language.upper()} from real-time sources...")
                news_digest = news_gen.generate_news_digest_from_sources(
                    language=language,
                    max_tokens=config.max_output_tokens,
                    max_items_per_source=config.max_items_per_source,
                    max_total_items=config.max_total_items,
                    stage1_template=config.stage1_prompt_template,
                    stage2_template=config.stage2_prompt_template
                )

                logger.info(f"News digest generated for {language.upper()} ({len(news_digest)} characters)")
                logger.info("-" * 60)
                logger.info(f"News Digest Preview ({language.upper()}):")
                logger.info("-" * 60)
                # Print first 500 characters as preview
                preview = news_digest[:500] + "..." if len(news_digest) > 500 else news_digest
                logger.info(preview)
                logger.info("-" * 60)

                # Dry run: render to files, send nothing to the distribution list.
                if config.dry_run:
                    md_path, html_path = write_dry_run_output(news_digest, language)
                    logger.info(f"DRY RUN: wrote {md_path} and {html_path} (no notifications sent)")
                    overall_results["sent"].append(f"dry-run ({language.upper()})")
                    continue

                # Track notification results for this language
                lang_results = {"sent": [], "failed": []}

                # Send email notification if enabled
                if "email" in notification_methods:
                    logger.info(f"Sending email notification for {language.upper()}...")
                    email_notifier = EmailNotifier()
                    if email_notifier.send(news_digest, language=language):
                        lang_results["sent"].append("email")
                        logger.info(f"Email notification sent successfully for {language.upper()}")
                    else:
                        lang_results["failed"].append("email")
                        logger.warning(f"Email notification failed for {language.upper()}")

                # Send webhook notification if enabled
                if "webhook" in notification_methods:
                    logger.info(f"Sending webhook notification for {language.upper()}...")
                    webhook_notifier = WebhookNotifier()
                    if webhook_notifier.send(news_digest, language=language):
                        lang_results["sent"].append("webhook")
                        logger.info(f"Webhook notification sent successfully for {language.upper()}")
                    else:
                        lang_results["failed"].append("webhook")
                        logger.warning(f"Webhook notification failed for {language.upper()}")

                # Send Slack notification if enabled
                if "slack" in notification_methods:
                    logger.info(f"Sending Slack notification for {language.upper()}...")
                    slack_notifier = SlackNotifier()
                    if slack_notifier.send(news_digest, language=language):
                        lang_results["sent"].append("slack")
                        logger.info(f"Slack notification sent successfully for {language.upper()}")
                    else:
                        lang_results["failed"].append("slack")
                        logger.warning(f"Slack notification failed for {language.upper()}")

                # Send Telegram notification if enabled
                if "telegram" in notification_methods:
                    logger.info(f"Sending Telegram notification for {language.upper()}...")
                    telegram_notifier = TelegramNotifier()
                    if telegram_notifier.send(news_digest, language=language):
                        lang_results["sent"].append("telegram")
                        logger.info(f"Telegram notification sent successfully for {language.upper()}")
                    else:
                        lang_results["failed"].append("telegram")
                        logger.warning(f"Telegram notification failed for {language.upper()}")

                # Send Discord notification if enabled
                if "discord" in notification_methods:
                    logger.info(f"Sending Discord notification for {language.upper()}...")
                    discord_notifier = DiscordNotifier()
                    if discord_notifier.send(news_digest, language=language):
                        lang_results["sent"].append("discord")
                        logger.info(f"Discord notification sent successfully for {language.upper()}")
                    else:
                        lang_results["failed"].append("discord")
                        logger.warning(f"Discord notification failed for {language.upper()}")

                # Update overall results
                for method in lang_results["sent"]:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["sent"]:
                        overall_results["sent"].append(result_key)
                
                for method in lang_results["failed"]:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["failed"]:
                        overall_results["failed"].append(result_key)

                logger.info(f"Language {language.upper()} completed successfully")

            except Exception as lang_error:
                logger.error(f"Error processing language {language.upper()}: {str(lang_error)}", exc_info=True)
                # Mark all notification methods as failed for this language
                for method in notification_methods:
                    result_key = f"{method} ({language.upper()})"
                    if result_key not in overall_results["failed"]:
                        overall_results["failed"].append(result_key)

        # Final Summary
        logger.info("=" * 60)
        logger.info("AI News Bot Completed")
        logger.info(f"Processed {len(languages)} language(s): {', '.join(lang.upper() for lang in languages)}")
        logger.info(f"Successfully sent: {', '.join(overall_results['sent']) if overall_results['sent'] else 'None'}")
        if overall_results["failed"]:
            logger.warning(f"Failed to send: {', '.join(overall_results['failed'])}")
        logger.info("=" * 60)

        # Return exit code based on results
        if notification_methods and not overall_results["sent"]:
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
