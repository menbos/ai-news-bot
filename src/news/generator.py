"""
AI News Generator using configurable LLM providers
"""
from typing import List, Optional, Dict
import json
import re
import email.utils
from urllib.parse import urlparse
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

# An item whose description adds fewer than this many words beyond its own
# title and publisher name is treated as headline-only. Google News search
# items are the common case: their <description> is just the headline plus
# the outlet name, so the model has no article text to summarize.
HEADLINE_ONLY_MIN_NEW_WORDS = 8

# Prepended to the Stage-2 prompt when the template has no {today}
# placeholder (e.g. an older custom template), so the date / current-facts
# grounding is never silently lost. The shipped config.yaml template places
# these placeholders itself, alongside fuller rules.
STAGE2_FALLBACK_CONTEXT = """Today's date is {today}. Your training data may be out of date: office-holders, job titles and company facts may have changed since your training cutoff. Treat the source text and the CURRENT FACTS below as authoritative over your own memory.

## CURRENT FACTS (authoritative; override your training data):
{current_facts}

Do not state or imply anyone's current role or title (e.g. "former", "current", "CEO of") unless the source text or CURRENT FACTS says it; otherwise refer to the person by name or use the exact title the source uses.

"""


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

    @staticmethod
    def _is_headline_only(item: Dict) -> bool:
        """True when the item's description adds (almost) nothing beyond its
        title and publisher name, i.e. there is no article text to summarize."""
        def tokens(text: Optional[str]) -> List[str]:
            return re.findall(r"[a-z0-9]+", (text or "").lower())

        known = set(tokens(item.get("title"))) | set(tokens(item.get("publisher"))) \
            | set(tokens(item.get("source"))) | {"nbsp"}
        new_words = [w for w in tokens(item.get("description")) if w not in known]
        return len(new_words) < HEADLINE_ONLY_MIN_NEW_WORDS

    def _format_selected_news(self, selected_ids: List[str], news_items: Dict[str, Dict]) -> str:
        """Format the selected items for Stage 2. Headline-only items are tagged
        [HEADLINE ONLY] and their (redundant) description is replaced by an
        explicit note, so the model knows not to pad them from memory."""
        formatted = "# Selected High-Quality AI News Items\n\n"
        for news_id in selected_ids:
            item = news_items[news_id]
            if self._is_headline_only(item):
                formatted += f"### [{news_id}] [HEADLINE ONLY] {item['title']}\n"
                formatted += f"**Source:** {item['source']}\n"
                formatted += (
                    "**Content:** (none available; only the headline above is known. "
                    "Summary must be 2-3 sentences and add no facts, names, titles or "
                    "numbers beyond the headline.)\n"
                )
            else:
                formatted += f"### [{news_id}] {item['title']}\n"
                formatted += f"**Source:** {item['source']}\n"
                formatted += f"**Content:** {item['description']}\n"
            formatted += f"**Link:** {item['link']}\n"
            formatted += f"**Published:** {self._format_date(item.get('published', ''))}\n"
            formatted += "\n"
        return formatted

    @staticmethod
    def _build_stage2_prompt(
        template: str,
        count: int,
        selected_news: str,
        current_facts: Optional[List[str]] = None,
        today: Optional[str] = None,
    ) -> str:
        """Fill the Stage-2 template. Uses str.replace rather than .format()
        because the template contains literal JSON braces."""
        today = today or datetime.now(timezone.utc).strftime("%B %d, %Y")
        facts = "\n".join(f"- {fact}" for fact in (current_facts or [])) or "- (none provided)"
        if "{today}" not in template:
            template = STAGE2_FALLBACK_CONTEXT + template
        return (
            template
            .replace("{today}", today)
            .replace("{current_facts}", facts)
            .replace("{count}", str(count))
            .replace("{selected_news}", selected_news)
        )

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

    @staticmethod
    def _publisher_host(url: str) -> str:
        """Registrable-ish host for a source URL, lowercased and www-stripped,
        used to bound how many items one publisher contributes to a digest."""
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return ""
        host = host.lower()
        return host[4:] if host.startswith("www.") else host

    def _cap_per_publisher(self, items: list, max_per_publisher: int = 2) -> list:
        """Drop items beyond `max_per_publisher` from the same publisher host,
        preserving order (keeping the earliest-selected). This stops a single
        vendor blog (e.g. the AWS ML blog, which is largely customer case
        studies) from flooding one digest. Items with no parseable host are
        never capped."""
        kept = []
        counts: Dict[str, int] = {}
        dropped = 0
        for item in items:
            host = self._publisher_host(item.get("source_url", ""))
            if host:
                if counts.get(host, 0) >= max_per_publisher:
                    dropped += 1
                    continue
                counts[host] = counts.get(host, 0) + 1
            kept.append(item)
        if dropped:
            logger.info(
                f"Per-publisher cap: dropped {dropped} item(s) exceeding "
                f"{max_per_publisher} per publisher host"
            )
        return kept

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
        items = self._cap_per_publisher(items)
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
                parts.append(f"### {(item.get('headline') or '').strip() or 'Untitled'}\n")
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
                    parts.append(f"### {(item.get('headline') or '').strip() or 'Untitled'}\n")
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
        stage2_template: Optional[str] = None,
        current_facts: Optional[List[str]] = None
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
            current_facts: Authoritative facts injected into the Stage 2 prompt
                to override stale model knowledge (from config)

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
            formatted_selected = self._format_selected_news(selected_ids, news_items)
            headline_only = sum(1 for nid in selected_ids if self._is_headline_only(news_items[nid]))
            if headline_only:
                logger.info(f"Stage 2: {headline_only}/{len(selected_ids)} selected items are headline-only")

            # Use provided template or load from config
            if stage2_template is None:
                from ..config import Config
                config = Config()
                stage2_template = config.stage2_prompt_template
                if current_facts is None:
                    current_facts = config.current_facts

            summarization_prompt = self._build_stage2_prompt(
                stage2_template,
                count=len(selected_ids),
                selected_news=formatted_selected,
                current_facts=current_facts,
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
