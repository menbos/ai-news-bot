"""
News fetcher module - Fetches real-time AI news from various sources
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import email.utils
import xml.etree.ElementTree as ET
from ..logger import setup_logger


logger = setup_logger(__name__)


class NewsFetcher:
    """Fetch real-time AI news from RSS feeds and news APIs"""

    def __init__(self, lookback_hours: int = 48):
        """Initialize the news fetcher.

        Args:
            lookback_hours: Only keep items published within this many hours.
                Items with no parseable date are always kept.
        """
        self.lookback_hours = lookback_hours
        # RSS feed sources for AI news (reliable sources only)
        self.rss_feeds = {
            # Major Tech Media
            "TechCrunch AI": "https://techcrunch.com/tag/artificial-intelligence/feed/",
            "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
            "MIT Technology Review": "https://www.technologyreview.com/feed/",
            "Ars Technica AI": "https://arstechnica.com/tag/ai/feed/",
            "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
            "The Next Web": "https://thenextweb.com/feed",
            "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "Engadget AI": "https://www.engadget.com/tag/ai/rss.xml",

            # Official AI Company Blogs
            "OpenAI Blog": "https://openai.com/blog/rss/",
            "Google AI Blog": "https://blog.google/technology/ai/rss/",
            "DeepMind Blog": "https://deepmind.google/blog/rss.xml",
            "Meta AI Blog": "https://ai.meta.com/blog/rss/",
            "Microsoft AI Blog": "https://blogs.microsoft.com/ai/feed/",

            # Vendor feature/release announcements (via Google News search feeds).
            # Catches product launches and developer-platform updates (e.g. new
            # Codex/API features) that have no first-party RSS feed of their own.
            "Vendor Releases (Google News)": "https://news.google.com/rss/search?q=(OpenAI+OR+Anthropic+OR+Claude+OR+Codex+OR+Gemini+OR+%22Google+DeepMind%22)+(launch+OR+release+OR+feature+OR+update+OR+announces)+when:3d&hl=en-US&gl=US&ceid=US:en",

            # Research & Academic
            "arXiv AI": "https://rss.arxiv.org/rss/cs.AI",
            "arXiv Machine Learning": "https://rss.arxiv.org/rss/cs.LG",
            "arXiv Computer Vision": "https://rss.arxiv.org/rss/cs.CV",
            "arXiv NLP": "https://rss.arxiv.org/rss/cs.CL",

            # Industry Verticals
            "Healthcare IT News AI": "https://www.healthcareitnews.com/taxonomy/term/31/feed",
            "Robotics Business Review": "https://www.roboticsbusinessreview.com/feed/",
            "Autonomous Vehicle News": "https://www.autonomousvehicleinternational.com/feed",

            # Finance & Banking AI
            "American Banker": "https://www.americanbanker.com/feed",
            "FinExtra AI": "https://www.finextra.com/rss/channel.aspx?channel=ai",
            "Bloomberg Technology": "https://feeds.bloomberg.com/technology/news.rss",
            "Reuters Finance": "https://feeds.reuters.com/reuters/businessNews",

            # Thematic Investing (Tech Disruptor / Green Planet / Future Health / Global Thematic)
            "ESG Today": "https://www.esgtoday.com/feed/",
            "CleanTechnica": "https://cleantechnica.com/feed/",
            "STAT News": "https://www.statnews.com/feed/",
            "BioPharma Dive": "https://www.biopharmadive.com/feeds/news/",

            # Strategic Materials & Critical Minerals
            "Mining.com": "https://www.mining.com/feed/",
            "Reuters Commodities": "https://feeds.reuters.com/reuters/commoditiesNews",
            "Benchmark Mineral Intelligence": "https://www.benchmarkminerals.com/feed/",
            "Energy Monitor": "https://www.energymonitor.ai/feed/",
        }

        # Chinese AI news sources (zh)
        self.chinese_feeds = {
            # Tech News Outlets
            "36Kr (36氪)": "https://36kr.com/feed",
            "JiQiZhiXin (机器之心)": "https://www.jiqizhixin.com/rss",
            "Leiphone (雷锋网)": "https://www.leiphone.com/feed",
            "iFeng Tech (凤凰科技)": "https://tech.ifeng.com/rss/index.xml",
            "Sina Tech (新浪科技)": "http://rss.sina.com.cn/tech/rollnews.xml",
            # Google News (fallback)
            "Google News AI (CN)": "https://news.google.com/rss/search?q=人工智能+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
            "Google News LLM (CN)": "https://news.google.com/rss/search?q=大模型+GPT+Claude&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        }

        # German AI news sources (de)
        self.german_feeds = {
            # Tech News Outlets
            "Heise Online": "https://www.heise.de/rss/heise-atom.xml",
            "t3n Digital Pioneers": "https://t3n.de/tag/kuenstliche-intelligenz/feed/",
            "Golem.de": "https://rss.golem.de/rss.php?feed=RSS2.0",
            "Computerwoche": "https://www.computerwoche.de/rss/feed/computerwoche-alle",
            # Google News
            "Google News AI (DE)": "https://news.google.com/rss/search?q=künstliche+intelligenz&hl=de&gl=DE&ceid=DE:de",
        }


    _STOP_WORDS = {
        'a', 'an', 'the', 'is', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but',
        'with', 'by', 'from', 'as', 'this', 'that', 'it', 'its', 'are', 'was', 'were',
        'has', 'have', 'had', 'will', 'would', 'could', 'should', 'may', 'can', 'be',
        'says', 'said', 'just', 'more', 'also', 'now', 'after', 'over', 'into', 'about',
        'up', 'how', 'what', 'why', 'when', 'new', 'report', 'reports',
    }

    def deduplicate_news(self, items: List[Dict]) -> List[Dict]:
        """
        Remove articles that cover the same story using title word-overlap (Jaccard similarity).
        When duplicates are found, keeps the first occurrence.
        """
        import re

        def keywords(title: str) -> frozenset:
            words = re.sub(r'[^\w\s]', ' ', title.lower()).split()
            return frozenset(w for w in words if len(w) > 3 and w not in self._STOP_WORDS)

        threshold = 0.4
        deduplicated = []
        seen: List[frozenset] = []

        for item in items:
            kw = keywords(item['title'])
            if len(kw) < 2:
                deduplicated.append(item)
                seen.append(kw)
                continue

            is_duplicate = False
            for seen_kw in seen:
                if len(seen_kw) < 2:
                    continue
                union_size = len(kw | seen_kw)
                if union_size and len(kw & seen_kw) / union_size >= threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                deduplicated.append(item)
                seen.append(kw)

        removed = len(items) - len(deduplicated)
        if removed:
            logger.info(f"Deduplication removed {removed} near-duplicate articles")
        return deduplicated

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

                    pub_date_str = pub_date.text if pub_date is not None else ''
                    parsed_date = self._parse_date(pub_date_str)
                    if parsed_date and parsed_date < cutoff:
                        continue

                    items.append({
                        'title': title.text if title is not None else '',
                        'link': link.text if link is not None else '',
                        'description': self._clean_html(description.text if description is not None else ''),
                        'published': pub_date_str,
                    })
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

                    items.append({
                        'title': title.text if title is not None else '',
                        'link': link.get('href', '') if link is not None else '',
                        'description': self._clean_html(summary.text if summary is not None else ''),
                        'published': updated_str,
                    })

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

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags from text"""
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text).strip()

    def fetch_recent_news(
        self,
        language: str = "en",
        max_items_per_source: int = 5
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetch recent AI news from all configured sources.

        Args:
            language: Language code for the response
            max_items_per_source: Maximum items to fetch per source

        Returns:
            Dictionary with 'international' and 'domestic' news lists
        """
        logger.info("Fetching recent AI news from all sources...")

        all_news = {
            'international': [],
            'domestic': []
        }

        # Fetch international news
        for source_name, feed_url in self.rss_feeds.items():
            items = self.fetch_rss_feed(feed_url, max_items_per_source)
            for item in items:
                item['source'] = source_name
                all_news['international'].append(item)

        # Fetch domestic news based on language
        language_feeds_map = {
            "zh": self.chinese_feeds,
            "de": self.german_feeds,
        }

        feeds = language_feeds_map.get(language)
        if not feeds:
            logger.warning(f"No domestic feeds configured for language: {language}, using international only")
            return all_news

        for source_name, feed_url in feeds.items():
            items = self.fetch_rss_feed(feed_url, max_items_per_source)
            for item in items:
                item['source'] = source_name
                all_news['domestic'].append(item)

        # Deduplicate within each category
        all_news['international'] = self.deduplicate_news(all_news['international'])
        all_news['domestic'] = self.deduplicate_news(all_news['domestic'])

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

        if news_data['international']:
            formatted += "## International News\n\n"
            for i, item in enumerate(news_data['international'], 1):
                formatted += f"### {i}. {item['title']}\n"
                formatted += f"**Source:** {item['source']}\n"
                if item['description']:
                    formatted += f"**Description:** {item['description'][:300]}...\n"
                formatted += f"**Link:** {item['link']}\n"
                if item['published']:
                    formatted += f"**Published:** {item['published']}\n"
                formatted += "\n"

        if news_data['domestic']:
            formatted += "## Domestic News\n\n"
            for i, item in enumerate(news_data['domestic'], 1):
                formatted += f"### {i}. {item['title']}\n"
                formatted += f"**Source:** {item['source']}\n"
                if item['description']:
                    formatted += f"**Description:** {item['description'][:300]}...\n"
                formatted += f"**Link:** {item['link']}\n"
                if item['published']:
                    formatted += f"**Published:** {item['published']}\n"
                formatted += "\n"

        return formatted
