"""
AI News Generator using configurable LLM providers
"""
from typing import List, Optional, Dict
import json
import re
import email.utils
from datetime import datetime, timezone
from ..logger import setup_logger
from .fetcher import NewsFetcher, TIER_LABELS
from .history import NewsHistory, _normalize_url as history_normalize_url
from . import dedup
from ..llm_providers import get_llm_provider


logger = setup_logger(__name__)

CATEGORY_ORDER = [
    "Thematic Investing",
    "Product Launches & Updates",
    "Enterprise & Industry Applications",
    "Financial Services & Banking AI",
    "Funding & Market Dynamics",
    "AI Infrastructure & Hardware",
    "Large Language Models & Foundation Models",
    "Multimodal AI",
    "Robotics & Autonomous Vehicles",
    "Policy & Regulation",
    "Open Source & Community",
]


class NewsGenerator:
    """Generate AI news digest using configurable LLM providers"""

    def __init__(
        self,
        provider_name: str = "claude",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        lookback_hours: int = 48,
        history: Optional[NewsHistory] = None,
        blocked_sources: Optional[List[str]] = None
    ):
        """
        Initialize the NewsGenerator.

        Args:
            provider_name: Name of LLM provider to use ('claude' or 'deepseek')
            api_key: API key for the provider. If None, will read from environment
            model: Model name to use. If None, uses provider's default model
            lookback_hours: How many hours back to keep fetched news items
            history: Optional NewsHistory for cross-run "already covered" tracking
            blocked_sources: Publisher domains/names whose items are dropped at fetch time

        Raises:
            ValueError: If provider is not recognized or API key is not provided
        """
        # Initialize LLM provider
        self.provider = get_llm_provider(
            provider_name=provider_name,
            api_key=api_key,
            model=model
        )

        self.news_fetcher = NewsFetcher(lookback_hours=lookback_hours, blocked_sources=blocked_sources)
        self.history = history
        logger.info(
            f"NewsGenerator initialized with {self.provider.provider_name} "
            f"(model: {self.provider.model})"
        )

    def _format_date(self, date_str: str) -> str:
        """Parse and format an RSS/Atom date string for human-readable display."""
        if not date_str:
            return "No date"
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            return dt.strftime("%b %d, %Y %H:%M UTC")
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%b %d, %Y %H:%M UTC")
        except Exception:
            pass
        return "No date"

    def _format_news_with_ids(self, items: List[Dict]) -> tuple:
        """
        Format news with unique IDs for selection stage.

        Args:
            items: List of fetched news items

        Returns:
            Tuple of (formatted_text, news_items_dict)
        """
        formatted = "# Recent AI News Items for Selection\n\n"
        news_items = {}  # id -> full news item

        for item_id, item in enumerate(items, 1):
            news_id = f"INT-{item_id}"
            news_items[news_id] = item

            covered = " [COVERED]" if item.get('already_covered') else ""
            formatted += f"### [{news_id}]{covered} {item['title']}\n"
            tier_label = TIER_LABELS.get(item.get('tier', 4), "")
            formatted += f"**Source:** {item['source']} ({tier_label})\n"
            if item['description']:
                formatted += f"**Description:** {item['description'][:400]}...\n"
            if item['published']:
                formatted += f"**Published:** {item['published']}\n"
            formatted += "\n"

        return formatted, news_items

    def _parse_stage2_items(self, response_text: str) -> list:
        """Parse the Stage-2 JSON array, or raise if it isn't valid JSON.

        A parse failure here almost always means the LLM response was truncated
        (no closing ``]``). We must NOT fall back to emitting the raw text: that
        dumps a raw JSON dict into the digest/email. Raising instead lets the
        caller mark the run as failed so the bad output is never sent.
        """
        items = self._extract_json_array(response_text)
        if not items:
            preview = response_text[:200].replace("\n", " ")
            raise ValueError(
                "Stage 2 output was not a parseable JSON array "
                "(likely truncated at max_output_tokens). Refusing to emit raw "
                f"output as a digest. Preview: {preview!r}"
            )
        return items

    def _extract_json_array(self, text: str) -> Optional[list]:
        """Extract and parse a JSON array from LLM output, handling markdown code fences."""
        # Strip code fences
        text = re.sub(r'```(?:json)?\s*', '', text).strip().rstrip('`').strip()
        match = re.search(r'\[[\s\S]*\]', text)
        if not match:
            return None
        try:
            result = json.loads(match.group(0))
            return result if isinstance(result, list) else None
        except json.JSONDecodeError:
            return None

    def _match_category(self, raw: str) -> str:
        """Map a raw category string to the canonical name; fall back to the raw string."""
        normalized = raw.lower().strip()
        for cat in CATEGORY_ORDER:
            if cat.lower() == normalized:
                return cat
        # Partial prefix match (e.g. "Large Language Models" → full canonical name)
        for cat in CATEGORY_ORDER:
            if normalized in cat.lower() or cat.lower().split('&')[0].strip() in normalized:
                return cat
        return raw

    def _deduplicate_items(self, items: list) -> list:
        """Collapse near-duplicate rendered items to one per story, keeping the
        one with the longest summary. See src/news/dedup.py for the algorithm
        (overlap-coefficient + single-linkage clustering, money-aware)."""
        return dedup.deduplicate(items, text_key="headline")

    def _collapse_duplicate_candidates(self, items: list) -> list:
        """Cluster the fetched candidate pool BEFORE Stage-1 selection and keep
        one representative per story, so the selector never sees several rewrites
        of the same event (which it may otherwise all pick). The representative
        is the most authoritative source (lowest tier number), tie-broken by the
        longest description. A [COVERED] flag on any cluster member is preserved
        on the representative so the continuation filter still applies."""
        def representative(cluster: list) -> dict:
            rep = min(
                cluster,
                key=lambda it: (it.get("tier", 99), -len(it.get("description", "") or "")),
            )
            if any(m.get("already_covered") for m in cluster):
                rep["already_covered"] = True
            return rep

        collapsed = dedup.deduplicate(items, text_key="title", representative=representative)
        if len(collapsed) < len(items):
            logger.info(
                f"Pre-selection dedup: {len(items)} candidates → {len(collapsed)} "
                f"after collapsing {len(items) - len(collapsed)} near-duplicate(s)"
            )
        return collapsed

    def _render_digest_from_json(self, items: list) -> str:
        """Render a markdown digest from structured items, enforcing order and deduplication."""
        items = self._deduplicate_items(items)
        grouped: Dict[str, list] = {}
        for item in items:
            cat = self._match_category(item.get("category", "Other"))
            grouped.setdefault(cat, []).append(item)

        parts = []
        seen = set()

        for cat in CATEGORY_ORDER:
            cat_items = grouped.get(cat, [])
            if not cat_items:
                continue
            seen.add(cat)
            parts.append(f"## {cat}\n")
            for item in cat_items:
                parts.append(f"### {item.get('headline', 'Untitled')}\n")
                parts.append(f"\n*Published: {item.get('published', 'No date')}*\n")
                parts.append(f"\n{item.get('summary', '')}\n")
                src_name = item.get("source_name", "Source")
                src_url = item.get("source_url", "")
                if src_url:
                    parts.append(f"\n[{src_name}]({src_url})\n")
                parts.append("\n---\n")

        # Append any items whose category didn't match the canonical list
        for cat, cat_items in grouped.items():
            if cat not in seen:
                parts.append(f"## {cat}\n")
                for item in cat_items:
                    parts.append(f"### {item.get('headline', 'Untitled')}\n")
                    parts.append(f"\n*Published: {item.get('published', 'No date')}*\n")
                    parts.append(f"\n{item.get('summary', '')}\n")
                    src_name = item.get("source_name", "Source")
                    src_url = item.get("source_url", "")
                    if src_url:
                        parts.append(f"\n[{src_name}]({src_url})\n")
                    parts.append("\n---\n")

        return "\n".join(parts)

    def generate_news_digest_from_sources(
        self,
        max_tokens: int = 16000,
        max_items_per_source: int = 10,
        max_total_items: Optional[int] = None,
        stage1_template: Optional[str] = None,
        stage2_template: Optional[str] = None
    ) -> str:
        """
        Fetch real-time news and generate a digest using two-stage prompt chaining:
        Stage 1: Analyze and select 15-20 high-quality news items
        Stage 2: Create detailed summaries for selected items

        Args:
            max_tokens: Maximum tokens in response
            max_items_per_source: Maximum items to fetch per source
            stage1_template: Optional Stage 1 prompt template (from config)
            stage2_template: Optional Stage 2 prompt template (from config)

        Returns:
            Generated news digest as string

        Raises:
            Exception: If fetching or generation fails
        """
        try:
            # Fetch real-time news
            logger.info("Fetching real-time AI news from sources...")
            fetched_items = self.news_fetcher.fetch_recent_news(
                max_items_per_source=max_items_per_source,
                max_total_items=max_total_items
            )

            if not fetched_items:
                error_msg = "No news items fetched from RSS sources. Please check your network connection or RSS feed availability."
                logger.error(error_msg)
                raise Exception(error_msg)

            # Drop items already published in a previous digest — same URL, or a
            # near-identical headline (the same article re-fetched under a fresh
            # Google News redirect URL). Only genuinely fuzzy title matches are
            # kept and flagged [COVERED], so Stage 1 can still pick up a real
            # continuation of a covered story.
            if self.history:
                covered_count = dropped_count = 0
                kept = []
                for item in fetched_items:
                    kind = self.history.match_kind(item)
                    if kind in ('url', 'title_strong'):
                        dropped_count += 1
                        continue
                    if kind == 'title':
                        item['already_covered'] = True
                        covered_count += 1
                    kept.append(item)
                fetched_items = kept
                logger.info(f"History: dropped {dropped_count} already-published items "
                            f"(same URL or near-identical title), "
                            f"marked {covered_count} items as [COVERED]")

            # Collapse same-run duplicates (multiple outlets/rewrites of the same
            # story) to one representative each, before the selector sees them.
            fetched_items = self._collapse_duplicate_candidates(fetched_items)

            # Format news with unique IDs for selection
            formatted_news, news_items = self._format_news_with_ids(fetched_items)
            total_items = len(news_items)

            logger.info(f"Starting two-stage prompt chaining with {total_items} news items")

            # ============================================================
            # STAGE 1: Selection - Analyze and select 15-20 best items
            # ============================================================
            logger.info(f"Stage 1: Analyzing and selecting high-quality news items...")

            # Use provided template or load from config
            if stage1_template is None:
                from ..config import Config
                config = Config()
                stage1_template = config.stage1_prompt_template

            # Recent digest headlines, injected so the model can dedup at the
            # topic level (heuristic URL/title matching misses reworded stories).
            recent_coverage = ""
            if self.history:
                recent_titles = self.history.recent_titles()
                if recent_titles:
                    recent_coverage = (
                        "- The following stories were published in recent digests. Do NOT select any item "
                        "covering the same story or topic — even if worded differently or not marked "
                        "[COVERED] — unless it reports a genuinely NEW, material development:\n"
                        + "\n".join(f"  - {t}" for t in recent_titles)
                    )
                    logger.info(f"Injecting {len(recent_titles)} recent digest headlines into Stage 1 prompt")

            # Format Stage 1 prompt with placeholders
            selection_prompt = stage1_template.format(
                formatted_news=formatted_news,
                total_items=total_items,
                recent_coverage=recent_coverage
            )

            messages = [{"role": "user", "content": selection_prompt}]
            selection_response = self.provider.generate(
                messages=messages,
                max_tokens=4000 # give enough tokens for selection
            )

            # Parse selected IDs
            json_match = re.search(r'\[[\s\S]*?\]', selection_response)
            if not json_match:
                logger.warning("Could not parse JSON from selection response, using fallback")
                # Fallback: select first 18 items
                selected_ids = list(news_items.keys())[:18]
            else:
                try:
                    selected_ids = json.loads(json_match.group(0))
                    # Validate IDs
                    selected_ids = [id for id in selected_ids if id in news_items]

                    # Ensure we have 15-20 items
                    if len(selected_ids) < 15:
                        logger.warning(f"Only {len(selected_ids)} items selected, adding more")
                        remaining = [id for id in news_items.keys() if id not in selected_ids]
                        selected_ids.extend(remaining[:18 - len(selected_ids)])
                    elif len(selected_ids) > 20:
                        logger.warning(f"{len(selected_ids)} items selected, trimming to 20")
                        selected_ids = selected_ids[:20]

                except json.JSONDecodeError:
                    logger.warning("JSON parse error, using fallback selection")
                    selected_ids = list(news_items.keys())[:18]

            logger.info(f"Stage 1 completed: Selected {len(selected_ids)} news items")
            logger.debug(f"Selected IDs: {selected_ids}")

            # ============================================================
            # STAGE 2: Summarization - Create detailed summaries
            # ============================================================
            logger.info(f"Stage 2: Creating detailed summaries for selected items...")

            # Format selected news for summarization
            formatted_selected = "# Selected High-Quality AI News Items\n\n"
            for news_id in selected_ids:
                item = news_items[news_id]
                formatted_selected += f"### [{news_id}] {item['title']}\n"
                formatted_selected += f"**Source:** {item['source']}\n"
                if item['description']:
                    formatted_selected += f"**Content:** {item['description']}\n"
                formatted_selected += f"**Link:** {item['link']}\n"
                formatted_selected += f"**Published:** {self._format_date(item.get('published', ''))}\n"
                formatted_selected += "\n"

            # Use provided template or load from config
            if stage2_template is None:
                from ..config import Config
                config = Config()
                stage2_template = config.stage2_prompt_template

            # Format Stage 2 prompt with placeholders (avoid .format() — template may contain
            # literal JSON braces that would be misinterpreted as format specifiers)
            summarization_prompt = (
                stage2_template
                .replace("{count}", str(len(selected_ids)))
                .replace("{selected_news}", formatted_selected)
            )

            # Execute Stage 2: Generate structured JSON
            messages = [{"role": "user", "content": summarization_prompt}]
            response_text = self.provider.generate(
                messages=messages,
                max_tokens=max_tokens
            )

            # Parse JSON and render markdown deterministically. A parse failure
            # raises (rather than emitting raw JSON), so a truncated response
            # fails the run instead of mailing a raw dict to recipients.
            items = self._parse_stage2_items(response_text)
            logger.info(f"Stage 2: parsed {len(items)} structured items, rendering markdown")
            response_text = self._render_digest_from_json(items)
            # Persist what we published so future runs recognize continuations.
            # Attach the original RSS title to each item (matched by URL) so
            # future runs can compare incoming RSS titles like-for-like instead
            # of only against the LLM-rewritten headline.
            if self.history:
                link_to_rss_title = {}
                for news_id in selected_ids:
                    orig = news_items[news_id]
                    norm = history_normalize_url(orig.get('link', ''))
                    if norm:
                        link_to_rss_title[norm] = orig.get('title', '')
                for item in items:
                    rss_title = link_to_rss_title.get(history_normalize_url(item.get('source_url', '')))
                    if rss_title:
                        item['rss_title'] = rss_title
                self.history.record(items)

            # Add footer with GitHub link
            footer = "\n\n---\n\n*Generated by [AI News Bot](https://github.com/giftedunicorn/ai-news-bot) - Your AI-powered news assistant*"
            response_text += footer

            logger.info("Stage 2 completed: News digest generated successfully")
            logger.info(f"Two-stage prompt chaining completed: {total_items} items → {len(selected_ids)} selected → full digest")
            logger.debug(f"Response length: {len(response_text)} characters")

            return response_text

        except Exception as e:
            logger.error(f"Failed to generate news digest from sources: {str(e)}", exc_info=True)
            raise
