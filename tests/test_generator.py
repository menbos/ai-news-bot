"""Tests for NewsGenerator pure helpers (provider not constructed)."""
from src.news.generator import NewsGenerator, CATEGORY_ORDER


def _bare_generator() -> NewsGenerator:
    # Bypass __init__ so we don't need an API key / provider.
    return NewsGenerator.__new__(NewsGenerator)


def test_match_category_exact_and_partial():
    g = _bare_generator()
    assert g._match_category("Policy & Regulation") == "Policy & Regulation"
    assert g._match_category("large language models") == "Large Language Models & Foundation Models"
    # Unknown category falls back to the raw string
    assert g._match_category("Quantum Widgets") == "Quantum Widgets"


def test_extract_json_array_handles_code_fences():
    g = _bare_generator()
    assert g._extract_json_array('```json\n["A", "B"]\n```') == ["A", "B"]
    assert g._extract_json_array('noise before ["X"] noise after') == ["X"]
    assert g._extract_json_array("not json at all") is None


def test_deduplicate_items_keeps_longer_summary():
    g = _bare_generator()
    items = [
        {"headline": "OpenAI ships GPT-6 model", "summary": "short"},
        {"headline": "OpenAI ships GPT-6 model today", "summary": "a much longer and richer summary"},
        {"headline": "Unrelated robotics breakthrough story", "summary": "x"},
    ]
    kept = g._deduplicate_items(items)
    assert len(kept) == 2
    gpt = [k for k in kept if "GPT-6" in k["headline"]][0]
    assert gpt["summary"] == "a much longer and richer summary"


def test_format_news_with_ids_marks_covered_and_tier():
    g = _bare_generator()
    news = {
        "international": [
            {"title": "Primary scoop", "source": "OpenAI Blog", "tier": 1,
             "description": "d", "link": "u1", "published": "", "already_covered": True},
            {"title": "Media take", "source": "TechCrunch AI", "tier": 4,
             "description": "d", "link": "u2", "published": ""},
        ],
        "domestic": [],
    }
    text, items = g._format_news_with_ids(news)
    assert set(items) == {"INT-1", "INT-2"}
    assert "[COVERED]" in text
    assert "Primary/Official" in text and "Tech Media" in text


def test_category_order_is_unique():
    assert len(CATEGORY_ORDER) == len(set(CATEGORY_ORDER))
