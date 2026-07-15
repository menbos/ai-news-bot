"""
Cross-run "already covered" memory.

Persists a small JSON record of recently covered stories (URL + headline) so the
digest can tell a genuinely new development apart from a continuation of a story
already reported on a previous day. The store is committed back to the repo by
the GitHub Actions workflow, since the runner itself is ephemeral.
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from ..logger import setup_logger

logger = setup_logger(__name__)

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "with", "its", "as", "by", "how", "why",
    "what", "that", "this", "has", "have", "will", "from", "new", "get",
    "says", "said", "report", "reports", "update", "updates",
}


def _normalize_url(url: str) -> str:
    """Drop scheme/query/fragment so the same article matches across feeds."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parts.path.rstrip("/")
        return urlunsplit(("", netloc, path, "", "")).lstrip("/")
    except Exception:
        return url.strip().lower()


def _tokens(title: str) -> set:
    words = re.sub(r"[^\w\s]", "", (title or "").lower()).split()
    return {w for w in words if w not in _STOPWORDS and len(w) > 3}


class NewsHistory:
    """Tracks recently covered stories across runs."""

    def __init__(self, path: str = "data/news_history.json", retention_days: int = 7,
                 title_similarity: float = 0.6, strong_title_similarity: float = 0.85,
                 prompt_days: int = 3):
        self.path = Path(path)
        self.retention_days = retention_days
        self.title_similarity = title_similarity
        self.strong_title_similarity = strong_title_similarity
        self.prompt_days = prompt_days
        self._entries: List[Dict] = self._load()
        # Matching structures are a frozen snapshot of what was loaded from disk.
        # They are NOT updated by record(), so a story recorded during this run
        # is never treated as "already covered" by the same run.
        self._match_urls = {e["url"] for e in self._entries if e.get("url")}
        # Match on both the published headline and the original RSS title (when
        # recorded) — incoming items carry RSS titles, so comparing against the
        # LLM-rewritten headline alone weakens the overlap.
        self._match_tokens = []
        for e in self._entries:
            self._match_tokens.append(_tokens(e.get("title", "")))
            if e.get("rss_title"):
                self._match_tokens.append(_tokens(e["rss_title"]))
        # URLs already written this session, to avoid duplicate file entries.
        self._recorded_urls = set(self._match_urls)

    def _load(self) -> List[Dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data.get("entries", []) if isinstance(data, dict) else []
        except Exception as e:
            logger.warning(f"Could not read history file {self.path}: {e}")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        fresh = []
        for e in entries:
            ts = e.get("first_seen")
            try:
                seen_at = datetime.fromisoformat(ts) if ts else None
            except Exception:
                seen_at = None
            if seen_at is None or seen_at >= cutoff:
                fresh.append(e)
        logger.info(f"Loaded {len(fresh)} recently-covered stories from history (retention {self.retention_days}d)")
        return fresh

    def match_kind(self, item: Dict) -> Optional[str]:
        """How this item matches the history: 'url' (same article),
        'title_strong' (near-identical headline — same article re-fetched under
        a different URL, e.g. Google News re-encoding its redirect links),
        'title' (fuzzy headline overlap), or None."""
        url = _normalize_url(item.get("link") or item.get("source_url") or "")
        if url and url in self._match_urls:
            return "url"

        tokens = _tokens(item.get("title") or item.get("headline") or "")
        if len(tokens) < 3:
            return None
        best = 0.0
        for seen_tokens in self._match_tokens:
            if len(seen_tokens) < 3:
                continue
            union = tokens | seen_tokens
            if union:
                best = max(best, len(tokens & seen_tokens) / len(union))
        if best >= self.strong_title_similarity:
            return "title_strong"
        if best >= self.title_similarity:
            return "title"
        return None

    def is_covered(self, item: Dict) -> bool:
        """True if this item was already reported in a recent digest."""
        return self.match_kind(item) is not None

    def recent_titles(self, days: Optional[int] = None) -> List[str]:
        """Headlines published within the last `days` (default prompt_days),
        for injection into the Stage-1 prompt as already-covered context."""
        days = self.prompt_days if days is None else days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        titles, seen = [], set()
        for e in self._entries:
            ts = e.get("first_seen")
            try:
                seen_at = datetime.fromisoformat(ts) if ts else None
            except Exception:
                seen_at = None
            if seen_at is not None and seen_at < cutoff:
                continue
            title = (e.get("title") or "").strip()
            if title and title.lower() not in seen:
                seen.add(title.lower())
                titles.append(title)
        return titles

    def record(self, items: List[Dict]) -> None:
        """Add newly published items to the store and persist (pruning old ones)."""
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        for item in items:
            url = _normalize_url(item.get("source_url") or item.get("link") or "")
            title = item.get("headline") or item.get("title") or ""
            if not title:
                continue
            if url and url in self._recorded_urls:
                continue
            entry = {"url": url, "title": title, "first_seen": now}
            rss_title = (item.get("rss_title") or "").strip()
            if rss_title and rss_title != title:
                entry["rss_title"] = rss_title
            self._entries.append(entry)
            if url:
                self._recorded_urls.add(url)
            added += 1

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"updated": now, "entries": self._entries}
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Recorded {added} new stories to history ({len(self._entries)} total)")
        except Exception as e:
            logger.warning(f"Could not write history file {self.path}: {e}")
