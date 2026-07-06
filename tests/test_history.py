"""Tests for cross-run NewsHistory."""
import json
from datetime import datetime, timezone, timedelta

from src.news.history import NewsHistory, _normalize_url, _tokens


def test_normalize_url_strips_scheme_www_query_fragment():
    assert _normalize_url("https://www.example.com/a/b/?q=1#frag") == "example.com/a/b"
    assert _normalize_url("http://openai.com/blog/x/") == "openai.com/blog/x"
    # Does not over-strip a leading 'w' from a real domain
    assert _normalize_url("https://www.weather.com/a") == "weather.com/a"


def test_is_covered_by_url_and_title(tmp_path):
    p = tmp_path / "h.json"
    h = NewsHistory(path=str(p), retention_days=7)
    h.record([{"headline": "OpenAI launches GPT-6 reasoning model",
               "source_url": "https://openai.com/blog/gpt6?utm=x"}])

    h2 = NewsHistory(path=str(p), retention_days=7)
    # Same URL, different scheme/query -> covered
    assert h2.is_covered({"link": "http://www.openai.com/blog/gpt6"}) is True
    # Same story by title overlap -> covered
    assert h2.is_covered({"title": "OpenAI launches GPT-6 reasoning model today"}) is True
    # Unrelated -> not covered
    assert h2.is_covered({"title": "Anthropic raises a Series F funding round",
                          "link": "https://example.com/x"}) is False


def test_same_session_record_does_not_flag_later_languages(tmp_path):
    """The match snapshot is frozen at load, so en's records don't suppress zh."""
    p = tmp_path / "h.json"
    h = NewsHistory(path=str(p), retention_days=7)
    h.record([{"headline": "Brand new Mistral model release announced",
               "source_url": "https://mistral.ai/news/new"}])
    assert h.is_covered({"title": "Brand new Mistral model release announced"}) is False


def test_retention_prunes_old_entries(tmp_path):
    p = tmp_path / "h.json"
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps({"entries": [
        {"url": "example.com/old", "title": "an old story long gone", "first_seen": old},
        {"url": "example.com/new", "title": "a fresh story still relevant", "first_seen": fresh},
    ]}), encoding="utf-8")

    h = NewsHistory(path=str(p), retention_days=7)
    assert h.is_covered({"link": "https://example.com/old"}) is False  # pruned
    assert h.is_covered({"link": "https://example.com/new"}) is True


def test_match_kind_distinguishes_url_and_title(tmp_path):
    p = tmp_path / "h.json"
    h = NewsHistory(path=str(p), retention_days=7)
    h.record([{"headline": "OpenAI launches GPT-6 reasoning model",
               "source_url": "https://openai.com/blog/gpt6"}])

    h2 = NewsHistory(path=str(p), retention_days=7)
    assert h2.match_kind({"link": "http://www.openai.com/blog/gpt6"}) == "url"
    assert h2.match_kind({"title": "OpenAI launches GPT-6 reasoning model today"}) == "title"
    assert h2.match_kind({"title": "Anthropic raises a Series F funding round",
                          "link": "https://example.com/x"}) is None


def test_record_keeps_rss_title_and_matches_against_it(tmp_path):
    p = tmp_path / "h.json"
    h = NewsHistory(path=str(p), retention_days=7)
    h.record([{"headline": "Cohere Secures US Drone Defense Contract",
               "rss_title": "Anduril taps Cohere for military drone AI partnership",
               "source_url": "https://example.com/a"}])

    h2 = NewsHistory(path=str(p), retention_days=7)
    # A next-day RSS item phrased like the original RSS title still matches
    assert h2.is_covered({"title": "Anduril taps Cohere for military drone AI work",
                          "link": "https://example.com/b"}) is True


def test_recent_titles_respects_prompt_days(tmp_path):
    p = tmp_path / "h.json"
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps({"entries": [
        {"url": "example.com/old", "title": "Old story from last week", "first_seen": old},
        {"url": "example.com/new", "title": "Fresh story from today", "first_seen": fresh},
        {"url": "example.com/dup", "title": "Fresh story from today", "first_seen": fresh},
    ]}), encoding="utf-8")

    h = NewsHistory(path=str(p), retention_days=7, prompt_days=3)
    assert h.recent_titles() == ["Fresh story from today"]  # old excluded, dup collapsed
    assert "Old story from last week" in h.recent_titles(days=7)


def test_tokens_drops_stopwords_and_short_words():
    toks = _tokens("The new AI model from OpenAI")
    assert "the" not in toks and "new" not in toks
    assert "openai" in toks and "model" in toks
