"""
News fetcher module - Fetches real-time AI news from various sources.

Feeds are organized by trust tier (1 = most primary). The tier travels with
each fetched item so that downstream selection and deduplication can prefer the
most authoritative source for a given story, mirroring the editorial hierarchy:

    1  Primary / official     company blogs, official docs, status pages
    2  Government / regulator  White House, NIST, FTC, policy trackers
    3  Wire / business         Reuters, Bloomberg, FT, WSJ, Axios
    4  Tech media              TechCrunch, The Verge, MIT Tech Review, verticals
    5  Research                arXiv, Nature
    6  Community / dev          Hacker News, GitHub Trending, Reddit
"""
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
import email.utils
import xml.etree.ElementTree as ET
from ..logger import setup_logger


logger = setup_logger(__name__)


# Human-readable label for each trust tier (lower number = more primary).
TIER_LABELS = {
    1: "Primary/Official",
    2: "Government/Regulator",
    3: "Wire/Business",
    4: "Tech Media",
    5: "Research",
    6: "Community/Dev",
    7: "Unverified",
}

# Tier assigned to Google News items whose publisher is not in PUBLISHER_TIERS.
UNVERIFIED_TIER = 7

# Publisher domain -> trust tier, for items that arrive via Google News search
# feeds. Those feeds carry a per-feed tier that says nothing about who actually
# wrote the piece (a content farm surfacing in the tier-1 "DeepSeek" search
# would otherwise be labeled Primary/Official). Matching is by domain suffix,
# so subdomains inherit the parent's tier. Publishers not listed here get
# UNVERIFIED_TIER; *.gov domains get tier 2 without needing an entry.
PUBLISHER_TIERS = {
    # Tier 1: first-party vendor domains
    "openai.com": 1,
    "anthropic.com": 1,
    "claude.com": 1,
    "deepseek.com": 1,
    "x.ai": 1,
    "spacex.com": 1,
    "meta.com": 1,
    "fb.com": 1,
    "blog.google": 1,
    "deepmind.google": 1,
    "cloud.google.com": 1,
    "microsoft.com": 1,
    "nvidia.com": 1,
    "aws.amazon.com": 1,
    "huggingface.co": 1,
    "github.blog": 1,
    "apple.com": 1,
    "mistral.ai": 1,
    "cohere.com": 1,
    "qwen.ai": 1,
    "nousresearch.com": 1,
    # Tier 3: wire / business press
    "reuters.com": 3,
    "bloomberg.com": 3,
    "ft.com": 3,
    "wsj.com": 3,
    "axios.com": 3,
    "cnbc.com": 3,
    "nytimes.com": 3,
    "washingtonpost.com": 3,
    "economist.com": 3,
    "fortune.com": 3,
    "businessinsider.com": 3,
    "theinformation.com": 3,
    "apnews.com": 3,
    "technode.com": 3,
    # Tier 4: tech media
    "techcrunch.com": 4,
    "theverge.com": 4,
    "arstechnica.com": 4,
    "wired.com": 4,
    "technologyreview.com": 4,
    "venturebeat.com": 4,
    "engadget.com": 4,
    "zdnet.com": 4,
    "macrumors.com": 4,
    "9to5mac.com": 4,
    "theregister.com": 4,
    "statnews.com": 4,
    "endpoints.news": 4,
    "36kr.com": 4,
    "jiqizhixin.com": 4,
    "heise.de": 4,
    "golem.de": 4,
    "t3n.de": 4,
    # Tier 5: research
    "arxiv.org": 5,
    "nature.com": 5,
    # Tier 6: community / dev
    "news.ycombinator.com": 6,
    "github.com": 6,
    "reddit.com": 6,
}


def _gnews(query: str, days: int = 2, lang: str = "en-US", country: str = "US") -> str:
    """Build a key-free Google News RSS search URL.

    Used to supplement first-party RSS for sources that have no usable feed of
    their own (Anthropic, xAI, Reuters, FT, WSJ, policy bodies, etc.). The
    ``site:`` operator and ``when:Nd`` recency filter both work inside the query.
    """
    from urllib.parse import quote
    q = quote(f"{query} when:{days}d")
    return f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={country}&ceid={country}:{lang.split('-')[0]}"


class NewsFetcher:
    """Fetch real-time AI news from RSS feeds and key-free search feeds."""

    def __init__(self, lookback_hours: int = 48, blocked_sources: Optional[List[str]] = None):
        """Initialize the news fetcher.

        Args:
            lookback_hours: Only keep items published within this many hours.
                Items with no parseable date are always kept.
            blocked_sources: Publishers to drop entirely. Each entry is either a
                domain ("technosports.co.in", matched against the item link and
                the Google News <source> URL) or a publisher-name substring
                ("technosports", matched case-insensitively against the
                <source> name). Needed because Google News search feeds carry
                whatever site gamed the index, including content farms that
                republish stale articles with fresh dates.
        """
        self.lookback_hours = lookback_hours
        self.blocked_sources = [b.strip().lower() for b in (blocked_sources or []) if b.strip()]

        # International feeds: name -> {"url", "tier", "type"}.
        # "type" is informational (blog/status/search/paper/forum/media).
        self.rss_feeds: Dict[str, Dict] = {
            # ---- Tier 1: Primary / official company sources ----
            "OpenAI Blog": {"url": "https://openai.com/news/rss.xml", "tier": 1, "type": "blog"},
            "Google AI Blog": {"url": "https://blog.google/technology/ai/rss/", "tier": 1, "type": "blog"},
            "Google DeepMind": {"url": "https://deepmind.google/blog/rss.xml", "tier": 1, "type": "blog"},
            "Meta AI (Google News)": {"url": _gnews("Meta AI OR Llama announces OR launches OR releases"), "tier": 1, "type": "search"},
            "Microsoft Blog": {"url": "https://blogs.microsoft.com/feed/", "tier": 1, "type": "blog"},
            "NVIDIA Blog": {"url": "https://blogs.nvidia.com/feed/", "tier": 1, "type": "blog"},
            "AWS Machine Learning": {"url": "https://aws.amazon.com/blogs/machine-learning/feed/", "tier": 1, "type": "blog"},
            "Hugging Face Blog": {"url": "https://huggingface.co/blog/feed.xml", "tier": 1, "type": "blog"},
            "GitHub Blog": {"url": "https://github.blog/feed/", "tier": 1, "type": "blog"},
            "Apple Newsroom": {"url": "https://www.apple.com/newsroom/rss-feed.rss", "tier": 1, "type": "blog"},
            # Primary vendors without a usable first-party feed -> key-free Google News search.
            "Anthropic (Google News)": {"url": _gnews("Anthropic OR Claude announces OR launches OR releases"), "tier": 1, "type": "search"},
            "xAI / Grok (Google News)": {"url": _gnews("xAI OR Grok announces OR launches OR releases"), "tier": 1, "type": "search"},
            "Mistral (Google News)": {"url": _gnews("Mistral AI announces OR launches OR releases"), "tier": 1, "type": "search"},
            "Cohere (Google News)": {"url": _gnews("Cohere AI announces OR launches OR releases"), "tier": 1, "type": "search"},
            "DeepSeek (Google News)": {"url": _gnews("DeepSeek announces OR launches OR releases model"), "tier": 1, "type": "search"},
            "Google Cloud AI (Google News)": {"url": _gnews("\"Google Cloud\" AI announces OR launches site:cloud.google.com"), "tier": 1, "type": "search"},
            # General vendor feature/release sweep (catches platform updates with no first-party feed).
            "Vendor Releases (Google News)": {
                "url": "https://news.google.com/rss/search?q=(OpenAI+OR+Anthropic+OR+Claude+OR+Codex+OR+Gemini+OR+%22Google+DeepMind%22)+(launch+OR+release+OR+feature+OR+update+OR+announces)+when:2d&hl=en-US&gl=US&ceid=US:en",
                "tier": 1, "type": "search",
            },

            # ---- Tier 1: Status / incident pages ----
            "OpenAI Status": {"url": "https://status.openai.com/history.rss", "tier": 1, "type": "status"},
            "Anthropic Status": {"url": "https://status.anthropic.com/history.rss", "tier": 1, "type": "status"},
            "Google Cloud Status": {"url": "https://status.cloud.google.com/en/feed.atom", "tier": 1, "type": "status"},
            "AWS Status": {"url": "https://status.aws.amazon.com/rss/all.rss", "tier": 1, "type": "status"},
            "GitHub Status": {"url": "https://www.githubstatus.com/history.rss", "tier": 1, "type": "status"},

            # ---- Tier 2: Government / regulation / policy ----
            "White House (Google News)": {"url": _gnews("White House AI OR \"executive order\" artificial intelligence", days=4), "tier": 2, "type": "search"},
            "NIST News": {"url": "https://www.nist.gov/news-events/news/rss.xml", "tier": 2, "type": "gov"},
            "FTC (Google News)": {"url": _gnews("FTC artificial intelligence OR antitrust", days=4), "tier": 2, "type": "search"},
            "AI Policy & Regulation (Google News)": {"url": _gnews("AI regulation OR \"AI Act\" OR \"export controls\" OR \"AI safety institute\"", days=3), "tier": 2, "type": "search"},

            # ---- Tier 3: Wire / business (key-free site-scoped search; these lack open RSS) ----
            "Reuters AI (Google News)": {"url": _gnews("artificial intelligence site:reuters.com"), "tier": 3, "type": "search"},
            "Bloomberg Technology": {"url": "https://feeds.bloomberg.com/technology/news.rss", "tier": 3, "type": "media"},
            "Financial Times AI (Google News)": {"url": _gnews("artificial intelligence site:ft.com"), "tier": 3, "type": "search"},
            "WSJ AI (Google News)": {"url": _gnews("artificial intelligence site:wsj.com"), "tier": 3, "type": "search"},
            "Axios AI (Google News)": {"url": _gnews("artificial intelligence site:axios.com"), "tier": 3, "type": "search"},

            # ---- Tier 4: Tech media ----
            "TechCrunch AI": {"url": "https://techcrunch.com/tag/artificial-intelligence/feed/", "tier": 4, "type": "media"},
            "VentureBeat AI": {"url": "https://venturebeat.com/category/ai/feed/", "tier": 4, "type": "media"},
            "MIT Technology Review": {"url": "https://www.technologyreview.com/feed/", "tier": 4, "type": "media"},
            "Ars Technica AI": {"url": "https://arstechnica.com/tag/ai/feed/", "tier": 4, "type": "media"},
            "Wired AI": {"url": "https://www.wired.com/feed/tag/ai/latest/rss", "tier": 4, "type": "media"},
            "The Verge AI": {"url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "tier": 4, "type": "media"},
            "Engadget": {"url": "https://www.engadget.com/rss.xml", "tier": 4, "type": "media"},
            "The Next Web": {"url": "https://thenextweb.com/feed", "tier": 4, "type": "media"},

            # ---- Tier 4: Industry verticals ----
            "Healthcare AI (Google News)": {"url": _gnews("healthcare AI OR clinical AI OR \"FDA\" AI", days=3), "tier": 4, "type": "search"},
            "Robotics Business Review": {"url": "https://www.roboticsbusinessreview.com/feed/", "tier": 4, "type": "media"},
            "Autonomous Vehicle News": {"url": "https://www.autonomousvehicleinternational.com/feed", "tier": 4, "type": "media"},
            "Banking AI (Google News)": {"url": _gnews("banking OR fintech artificial intelligence", days=3), "tier": 4, "type": "search"},
            "FinExtra AI": {"url": "https://www.finextra.com/rss/channel.aspx?channel=ai", "tier": 4, "type": "media"},

            # ---- Tier 4: Thematic investing (Tech Disruptor / Green Planet / Future Health) ----
            "ESG Today": {"url": "https://www.esgtoday.com/feed/", "tier": 4, "type": "media"},
            "CleanTechnica": {"url": "https://cleantechnica.com/feed/", "tier": 4, "type": "media"},
            "STAT News": {"url": "https://www.statnews.com/feed/", "tier": 4, "type": "media"},
            "BioPharma Dive": {"url": "https://www.biopharmadive.com/feeds/news/", "tier": 4, "type": "media"},

            # ---- Tier 4: Strategic materials & critical minerals ----
            "Mining.com": {"url": "https://www.mining.com/feed/", "tier": 4, "type": "media"},
            "Critical Minerals (Google News)": {"url": _gnews("lithium OR \"rare earth\" OR cobalt OR copper supply", days=3), "tier": 4, "type": "search"},
            "Energy Monitor": {"url": "https://www.energymonitor.ai/feed/", "tier": 4, "type": "media"},

            # ---- Tier 5: Research (high volume -> capped to keep the signal-to-noise high) ----
            "arXiv AI": {"url": "https://rss.arxiv.org/rss/cs.AI", "tier": 5, "type": "paper", "max": 3},
            "arXiv Machine Learning": {"url": "https://rss.arxiv.org/rss/cs.LG", "tier": 5, "type": "paper", "max": 3},
            "arXiv Computer Vision": {"url": "https://rss.arxiv.org/rss/cs.CV", "tier": 5, "type": "paper", "max": 3},
            "arXiv NLP": {"url": "https://rss.arxiv.org/rss/cs.CL", "tier": 5, "type": "paper", "max": 3},
            "Nature Machine Learning": {"url": "https://www.nature.com/subjects/machine-learning.rss", "tier": 5, "type": "paper", "max": 4},

            # ---- Tier 6: Open source & developer community (capped) ----
            "Hacker News (AI)": {"url": "https://hnrss.org/newest?q=AI+OR+LLM+OR+OpenAI+OR+Anthropic&points=80", "tier": 6, "type": "forum", "max": 6},
            "GitHub Trending": {"url": "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml", "tier": 6, "type": "forum", "max": 6},
            "Reddit r/LocalLLaMA": {"url": "https://www.reddit.com/r/LocalLLaMA/.rss", "tier": 6, "type": "forum", "max": 5},
            "Reddit r/MachineLearning": {"url": "https://www.reddit.com/r/MachineLearning/.rss", "tier": 6, "type": "forum", "max": 5},
        }

        # Chinese AI news sources (zh)
        self.chinese_feeds: Dict[str, Dict] = {
            "36Kr (36氪)": {"url": "https://36kr.com/feed", "tier": 4, "type": "media"},
            "JiQiZhiXin (机器之心)": {"url": "https://www.jiqizhixin.com/rss", "tier": 4, "type": "media"},
            "Leiphone (雷锋网)": {"url": "https://www.leiphone.com/feed", "tier": 4, "type": "media"},
            "iFeng Tech (凤凰科技)": {"url": "https://tech.ifeng.com/rss/index.xml", "tier": 4, "type": "media"},
            "Sina Tech (新浪科技)": {"url": "http://rss.sina.com.cn/tech/rollnews.xml", "tier": 4, "type": "media"},
            "Google News AI (CN)": {"url": "https://news.google.com/rss/search?q=人工智能+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "tier": 4, "type": "search"},
            "Google News LLM (CN)": {"url": "https://news.google.com/rss/search?q=大模型+GPT+Claude&hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "tier": 4, "type": "search"},
        }

        # German AI news sources (de)
        self.german_feeds: Dict[str, Dict] = {
            "Heise Online": {"url": "https://www.heise.de/rss/heise-atom.xml", "tier": 4, "type": "media"},
            "t3n Digital Pioneers": {"url": "https://t3n.de/tag/kuenstliche-intelligenz/feed/", "tier": 4, "type": "media"},
            "Golem.de": {"url": "https://rss.golem.de/rss.php?feed=RSS2.0", "tier": 4, "type": "media"},
            "Computerwoche": {"url": "https://www.computerwoche.de/rss/feed/computerwoche-alle", "tier": 4, "type": "media"},
            "Google News AI (DE)": {"url": "https://news.google.com/rss/search?q=künstliche+intelligenz&hl=de&gl=DE&ceid=DE:de", "tier": 4, "type": "search"},
        }

    _STOP_WORDS = {
        'a', 'an', 'the', 'is', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but',
        'with', 'by', 'from', 'as', 'this', 'that', 'it', 'its', 'are', 'was', 'were',
        'has', 'have', 'had', 'will', 'would', 'could', 'should', 'may', 'can', 'be',
        'says', 'said', 'just', 'more', 'also', 'now', 'after', 'over', 'into', 'about',
        'up', 'how', 'what', 'why', 'when', 'new', 'report', 'reports',
    }

    @staticmethod
    def _feed_meta(value) -> Tuple[str, int, str, Optional[int]]:
        """Normalize a feed entry (dict or bare URL string) to (url, tier, type, max).

        ``max`` is an optional per-feed item cap that overrides the global
        ``max_items_per_source`` — used to throttle high-volume, low-signal feeds
        (arXiv, Reddit, GitHub Trending) so they don't crowd out primary sources.
        """
        if isinstance(value, dict):
            return (
                value.get("url", ""),
                int(value.get("tier", 4)),
                value.get("type", ""),
                value.get("max"),
            )
        return value, 4, "", None

    @staticmethod
    def _hostname(url: str) -> str:
        """Lowercased hostname of a URL ('' if unparseable)."""
        from urllib.parse import urlsplit
        try:
            return (urlsplit(url).hostname or '').lower()
        except ValueError:
            return ''

    def _is_blocked(self, item: Dict[str, str]) -> bool:
        """True if the item comes from a blocked publisher.

        Domain entries (containing a dot) match the item link's host and the
        publisher <source> URL's host, including subdomains. Name entries match
        as a substring of the publisher name.
        """
        if not self.blocked_sources:
            return False
        hosts = [h for h in (self._hostname(item.get('link', '')),
                             self._hostname(item.get('publisher_url', ''))) if h]
        publisher = item.get('publisher', '').lower()
        for blocked in self.blocked_sources:
            if '.' in blocked:
                if any(h == blocked or h.endswith('.' + blocked) for h in hosts):
                    return True
            elif blocked in publisher:
                return True
        return False

    @classmethod
    def _publisher_tier(cls, host: str) -> int:
        """Trust tier for a publisher hostname (UNVERIFIED_TIER if unknown)."""
        if not host:
            return UNVERIFIED_TIER
        if host.endswith('.gov'):
            return 2
        for domain, tier in PUBLISHER_TIERS.items():
            if host == domain or host.endswith('.' + domain):
                return tier
        return UNVERIFIED_TIER

    def _apply_publisher_tier(self, item: Dict) -> None:
        """Re-tier a Google News-proxied item by its actual publisher.

        Search feeds carry a per-feed tier, but the publisher can be anyone
        Google indexed. Rate such items by the <source> element's domain
        instead, and surface the publisher name in 'source' so the Stage-1
        prompt judges the real outlet rather than the feed name.
        """
        if self._hostname(item.get('link', '')) != 'news.google.com':
            return
        item['tier'] = self._publisher_tier(self._hostname(item.get('publisher_url', '')))
        if item.get('publisher'):
            item['source'] = f"{item['publisher']} (via {item['source']})"

    def deduplicate_news(self, items: List[Dict]) -> List[Dict]:
        """
        Remove articles that cover the same story using title word-overlap
        (Jaccard similarity). On a collision, keep the item from the most
        primary source (lowest tier number) so the digest links the original
        announcement rather than a secondary rewrite.
        """
        import re

        def keywords(title: str) -> frozenset:
            words = re.sub(r'[^\w\s]', ' ', title.lower()).split()
            return frozenset(w for w in words if len(w) > 3 and w not in self._STOP_WORDS)

        threshold = 0.4
        kept: List[Dict] = []
        kept_kw: List[frozenset] = []

        for item in items:
            kw = keywords(item['title'])
            if len(kw) < 2:
                kept.append(item)
                kept_kw.append(kw)
                continue

            dup_index = None
            for i, seen_kw in enumerate(kept_kw):
                if len(seen_kw) < 2:
                    continue
                union_size = len(kw | seen_kw)
                if union_size and len(kw & seen_kw) / union_size >= threshold:
                    dup_index = i
                    break

            if dup_index is None:
                kept.append(item)
                kept_kw.append(kw)
            else:
                # Same story: keep whichever source is more primary (lower tier).
                if item.get('tier', 4) < kept[dup_index].get('tier', 4):
                    kept[dup_index] = item
                    kept_kw[dup_index] = kw

        removed = len(items) - len(kept)
        if removed:
            logger.info(f"Deduplication removed {removed} near-duplicate articles")
        return kept

    def fetch_rss_feed(self, feed_url: str, max_items: int = 10) -> List[Dict[str, str]]:
        """
        Fetch news items from an RSS feed.

        Args:
            feed_url: URL of the RSS feed
            max_items: Maximum number of items to fetch

        Returns:
            List of news items with title, link, description, and published date
        """
        try:
            logger.info(f"Fetching RSS feed: {feed_url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            response = requests.get(feed_url, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)

            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

            items = []
            # Handle both RSS 2.0 and Atom formats
            if root.tag == 'rss':
                news_items = root.findall('.//item')[:max_items]
                for item in news_items:
                    title = item.find('title')
                    link = item.find('link')
                    description = item.find('description')
                    pub_date = item.find('pubDate')
                    # Google News search feeds name the real publisher here;
                    # the <link> itself is a news.google.com redirect.
                    source = item.find('source')

                    pub_date_str = pub_date.text if pub_date is not None else ''
                    parsed_date = self._parse_date(pub_date_str)
                    if parsed_date and parsed_date < cutoff:
                        continue

                    parsed = {
                        'title': title.text if title is not None else '',
                        'link': link.text if link is not None else '',
                        'description': self._clean_html(description.text if description is not None else ''),
                        'published': pub_date_str,
                        'publisher': (source.text or '') if source is not None else '',
                        'publisher_url': source.get('url', '') if source is not None else '',
                    }
                    if self._is_blocked(parsed):
                        logger.info(f"Dropping blocked source item: {parsed['title']!r} ({parsed['publisher'] or parsed['link']})")
                        continue
                    items.append(parsed)
            else:
                # Atom format
                namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('.//atom:entry', namespace)[:max_items]
                for entry in entries:
                    title = entry.find('atom:title', namespace)
                    link = entry.find('atom:link', namespace)
                    summary = entry.find('atom:summary', namespace)
                    updated = entry.find('atom:updated', namespace)

                    updated_str = updated.text if updated is not None else ''
                    parsed_date = self._parse_date(updated_str)
                    if parsed_date and parsed_date < cutoff:
                        continue

                    parsed = {
                        'title': title.text if title is not None else '',
                        'link': link.get('href', '') if link is not None else '',
                        'description': self._clean_html(summary.text if summary is not None else ''),
                        'published': updated_str,
                    }
                    if self._is_blocked(parsed):
                        logger.info(f"Dropping blocked source item: {parsed['title']!r} ({parsed['link']})")
                        continue
                    items.append(parsed)

            logger.info(f"Fetched {len(items)} items from RSS feed")
            return items

        except Exception as e:
            logger.error(f"Failed to fetch RSS feed {feed_url}: {str(e)}")
            return []

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse an RSS/Atom date string into a timezone-aware datetime."""
        if not date_str:
            return None
        try:
            return email.utils.parsedate_to_datetime(date_str)
        except Exception:
            pass
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except Exception:
            pass
        return None

    def _clean_html(self, text: Optional[str]) -> str:
        """Remove HTML tags from text (tolerates None / empty elements)."""
        if not text:
            return ''
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text).strip()

    def _fetch_feed_group(self, feeds: Dict[str, Dict], max_items_per_source: int) -> List[Dict]:
        """Fetch every feed in a group, tagging each item with source/tier/type."""
        collected: List[Dict] = []
        for source_name, meta in feeds.items():
            url, tier, source_type, feed_max = self._feed_meta(meta)
            limit = feed_max if feed_max is not None else max_items_per_source
            for item in self.fetch_rss_feed(url, limit):
                item['source'] = source_name
                item['tier'] = tier
                item['source_type'] = source_type
                self._apply_publisher_tier(item)
                collected.append(item)
        return collected

    def fetch_recent_news(
        self,
        language: str = "en",
        max_items_per_source: int = 10,
        max_total_items: Optional[int] = None
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetch recent AI news from all configured sources.

        Args:
            language: Language code for the response
            max_items_per_source: Maximum items to fetch per source
            max_total_items: Optional cap on international items kept after dedup.
                Feeds are tier-ordered (primary first), so trimming keeps the most
                authoritative sources and bounds the Stage-1 prompt size.

        Returns:
            Dictionary with 'international' and 'domestic' news lists
        """
        logger.info("Fetching recent AI news from all sources...")

        all_news = {
            'international': self._fetch_feed_group(self.rss_feeds, max_items_per_source),
            'domestic': [],
        }

        # Fetch domestic news based on language
        language_feeds_map = {
            "zh": self.chinese_feeds,
            "de": self.german_feeds,
        }

        feeds = language_feeds_map.get(language)
        if feeds:
            all_news['domestic'] = self._fetch_feed_group(feeds, max_items_per_source)
        else:
            logger.warning(f"No domestic feeds configured for language: {language}, using international only")

        # Deduplicate within each category (tier-aware: keeps the most primary source)
        all_news['international'] = self.deduplicate_news(all_news['international'])
        all_news['domestic'] = self.deduplicate_news(all_news['domestic'])

        # Restore tier order: publisher re-tiering can demote items from
        # early (tier-1) Google News feeds, so feed order alone no longer
        # guarantees it. Stable sort keeps within-tier feed order.
        all_news['international'].sort(key=lambda i: i.get('tier', 4))

        # Bound the total to keep the Stage-1 prompt manageable. Items are
        # tier-ordered, so this trims the long tail of low-tier feeds first.
        if max_total_items and len(all_news['international']) > max_total_items:
            logger.info(
                f"Trimming international items {len(all_news['international'])} -> {max_total_items} (max_total_items)"
            )
            all_news['international'] = all_news['international'][:max_total_items]

        logger.info(
            f"Fetched {len(all_news['international'])} international news items "
            f"and {len(all_news['domestic'])} domestic ({language}) news items after deduplication"
        )

        return all_news

    def format_news_for_summary(self, news_data: Dict[str, List[Dict[str, str]]]) -> str:
        """
        Format fetched news into a text suitable for AI summarization.

        Args:
            news_data: Dictionary with 'international' and 'domestic' news lists

        Returns:
            Formatted news text
        """
        formatted = "# Recent AI News Items to Summarize\n\n"

        for section_title, key in (("International News", "international"), ("Domestic News", "domestic")):
            if not news_data[key]:
                continue
            formatted += f"## {section_title}\n\n"
            for i, item in enumerate(news_data[key], 1):
                formatted += f"### {i}. {item['title']}\n"
                tier_label = TIER_LABELS.get(item.get('tier', 4), "")
                formatted += f"**Source:** {item['source']} ({tier_label})\n"
                if item['description']:
                    formatted += f"**Description:** {item['description'][:300]}...\n"
                formatted += f"**Link:** {item['link']}\n"
                if item['published']:
                    formatted += f"**Published:** {item['published']}\n"
                formatted += "\n"

        return formatted
