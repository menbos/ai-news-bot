"""Tests for NewsFetcher pure logic (no network)."""
import pytest
import requests

from src.news import fetcher as fetcher_mod
from src.news.fetcher import NewsFetcher, TIER_LABELS, UNVERIFIED_TIER, _gnews


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"<rss></rss>"):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_feed_meta_dict_and_string():
    assert NewsFetcher._feed_meta({"url": "u", "tier": 1, "type": "blog"}) == ("u", 1, "blog", None)
    assert NewsFetcher._feed_meta({"url": "u", "tier": 5, "max": 3}) == ("u", 5, "", 3)
    # Bare string falls back to tier 4, no cap
    assert NewsFetcher._feed_meta("http://x") == ("http://x", 4, "", None)


def test_dedup_keeps_most_primary_source():
    f = NewsFetcher(lookback_hours=48)
    items = [
        {"title": "OpenAI launches GPT-6 reasoning model today", "tier": 4, "source": "TechCrunch"},
        {"title": "OpenAI launches GPT-6 reasoning model", "tier": 1, "source": "OpenAI Blog"},
        {"title": "Totally unrelated lithium mining supply story", "tier": 4, "source": "Mining"},
    ]
    kept = f.deduplicate_news(items)
    assert len(kept) == 2
    # The duplicate is resolved toward the lowest tier number (most primary).
    assert {k["source"] for k in kept} == {"OpenAI Blog", "Mining"}


def test_dedup_preserves_order_and_short_titles():
    f = NewsFetcher(lookback_hours=48)
    items = [
        {"title": "AI", "tier": 1, "source": "a"},          # < 2 keywords -> always kept
        {"title": "Another short one", "tier": 1, "source": "b"},
    ]
    kept = f.deduplicate_news(items)
    assert len(kept) == 2


def test_all_feed_tiers_have_labels():
    f = NewsFetcher(lookback_hours=48)
    for meta in f.rss_feeds.values():
        assert meta["tier"] in TIER_LABELS


def test_high_volume_feeds_are_capped():
    f = NewsFetcher(lookback_hours=48)
    # arXiv / Reddit / GitHub Trending should carry an explicit per-feed cap.
    for name in ("arXiv AI", "Reddit r/LocalLLaMA", "GitHub Trending"):
        assert f.rss_feeds[name].get("max") is not None


def test_gnews_builds_recency_query():
    url = _gnews("Anthropic Claude", days=2)
    assert "news.google.com/rss/search" in url
    assert "when%3A2d" in url  # "when:2d" url-encoded


def test_clean_html_handles_none():
    f = NewsFetcher(lookback_hours=48)
    assert f._clean_html(None) == ""
    assert f._clean_html("<p>hi <b>there</b></p>") == "hi there"


def test_blocked_source_matches_link_domain_and_subdomains():
    f = NewsFetcher(lookback_hours=48, blocked_sources=["technosports.co.in"])
    assert f._is_blocked({"link": "https://technosports.co.in/deepseek-x/"})
    assert f._is_blocked({"link": "https://www.technosports.co.in/deepseek-x/"})
    # Same registrable string embedded in a different domain must NOT match.
    assert not f._is_blocked({"link": "https://nottechnosports.co.in/story/"})
    assert not f._is_blocked({"link": "https://techcrunch.com/story/"})


def test_blocked_source_matches_google_news_publisher():
    f = NewsFetcher(lookback_hours=48, blocked_sources=["technosports.co.in"])
    # Google News items link to news.google.com; the publisher travels in <source>.
    item = {
        "link": "https://news.google.com/rss/articles/CBMie0FV",
        "publisher": "TechnoSports Media Group",
        "publisher_url": "https://technosports.co.in",
    }
    assert f._is_blocked(item)


def test_blocked_source_name_substring():
    f = NewsFetcher(lookback_hours=48, blocked_sources=["technosports"])
    assert f._is_blocked({
        "link": "https://news.google.com/rss/articles/CBMie0FV",
        "publisher": "TechnoSports Media Group",
    })
    assert not f._is_blocked({
        "link": "https://news.google.com/rss/articles/CBMie0FV",
        "publisher": "Reuters",
    })


def test_no_blocklist_blocks_nothing():
    f = NewsFetcher(lookback_hours=48)
    assert not f._is_blocked({"link": "https://technosports.co.in/anything/"})


def test_publisher_tier_lookup():
    # Known outlets map to their curated tier, subdomains included.
    assert NewsFetcher._publisher_tier("reuters.com") == 3
    assert NewsFetcher._publisher_tier("www.wired.com") == 4
    assert NewsFetcher._publisher_tier("openai.com") == 1
    # Government domains are tier 2 without an explicit entry.
    assert NewsFetcher._publisher_tier("ftc.gov") == 2
    # Unknown publishers are unverified, and a known domain embedded in a
    # different registrable domain must not match.
    assert NewsFetcher._publisher_tier("technosports.co.in") == UNVERIFIED_TIER
    assert NewsFetcher._publisher_tier("notreuters.com") == UNVERIFIED_TIER
    assert NewsFetcher._publisher_tier("") == UNVERIFIED_TIER


def test_apply_publisher_tier_demotes_unknown_google_news_publisher():
    f = NewsFetcher(lookback_hours=48)
    item = {
        "link": "https://news.google.com/rss/articles/CBMie0FV",
        "source": "DeepSeek (Google News)",
        "tier": 1,
        "publisher": "TechnoSports Media Group",
        "publisher_url": "https://technosports.co.in",
    }
    f._apply_publisher_tier(item)
    assert item["tier"] == UNVERIFIED_TIER
    assert item["source"] == "TechnoSports Media Group (via DeepSeek (Google News))"


def test_apply_publisher_tier_keeps_known_publisher_tier():
    f = NewsFetcher(lookback_hours=48)
    item = {
        "link": "https://news.google.com/rss/articles/CBMie0FV",
        "source": "Vendor Releases (Google News)",
        "tier": 1,
        "publisher": "Wired",
        "publisher_url": "https://www.wired.com",
    }
    f._apply_publisher_tier(item)
    assert item["tier"] == 4
    assert item["source"].startswith("Wired (via ")


def test_apply_publisher_tier_ignores_first_party_feeds():
    f = NewsFetcher(lookback_hours=48)
    item = {"link": "https://openai.com/index/gpt-5-6/", "source": "OpenAI Blog", "tier": 1}
    f._apply_publisher_tier(item)
    assert item["tier"] == 1
    assert item["source"] == "OpenAI Blog"


def test_fetch_feed_group_concurrent_preserves_feed_order_and_tags():
    import time

    f = NewsFetcher(lookback_hours=48)
    feeds = {
        "Slow Feed": {"url": "http://slow", "tier": 1, "type": "blog"},
        "Fast Feed": {"url": "http://fast", "tier": 4, "type": "media"},
        "Broken Feed": {"url": "http://broken", "tier": 4, "type": "media"},
    }

    def fake_fetch(url, max_items):
        if url == "http://slow":
            time.sleep(0.05)  # finishes after Fast Feed; order must not change
            return [{"title": "slow story", "link": "https://a.example/1", "description": "", "published": ""}]
        if url == "http://fast":
            return [{"title": "fast story", "link": "https://b.example/1", "description": "", "published": ""}]
        raise RuntimeError("boom")  # a raising future must not kill the group

    f.fetch_rss_feed = fake_fetch
    items = f._fetch_feed_group(feeds, max_items_per_source=5)

    assert [i["source"] for i in items] == ["Slow Feed", "Fast Feed"]
    assert [i["tier"] for i in items] == [1, 4]
    assert items[0]["source_type"] == "blog"


def test_get_with_retry_recovers_from_transient_errors(monkeypatch):
    f = NewsFetcher(lookback_hours=48)
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if len(calls) == 1:
            raise requests.ConnectionError("boom")
        if len(calls) == 2:
            return FakeResponse(503)
        return FakeResponse(200)

    monkeypatch.setattr(fetcher_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetcher_mod.time, "sleep", lambda s: None)

    response = f._get_with_retry("http://feed")
    assert response.status_code == 200
    assert len(calls) == 3


def test_get_with_retry_does_not_retry_permanent_4xx(monkeypatch):
    f = NewsFetcher(lookback_hours=48)
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(404)

    monkeypatch.setattr(fetcher_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetcher_mod.time, "sleep", lambda s: None)

    with pytest.raises(requests.HTTPError):
        f._get_with_retry("http://feed")
    assert len(calls) == 1


def test_get_with_retry_gives_up_after_max_attempts(monkeypatch):
    f = NewsFetcher(lookback_hours=48)
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        raise requests.Timeout("slow")

    monkeypatch.setattr(fetcher_mod.requests, "get", fake_get)
    monkeypatch.setattr(fetcher_mod.time, "sleep", lambda s: None)

    with pytest.raises(requests.Timeout):
        f._get_with_retry("http://feed")
    assert len(calls) == NewsFetcher._FETCH_ATTEMPTS

    # And fetch_rss_feed still swallows the failure into an empty list.
    calls.clear()
    assert f.fetch_rss_feed("http://feed") == []
    assert len(calls) == NewsFetcher._FETCH_ATTEMPTS
