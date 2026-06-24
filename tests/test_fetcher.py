"""Tests for NewsFetcher pure logic (no network)."""
from src.news.fetcher import NewsFetcher, TIER_LABELS, _gnews


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
