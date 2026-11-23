"""Tests for NewsGenerator pure helpers (provider not constructed)."""
import pytest

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


def test_parse_stage2_items_returns_parsed_array():
    g = _bare_generator()
    items = g._parse_stage2_items('[{"headline": "A"}, {"headline": "B"}]')
    assert [i["headline"] for i in items] == ["A", "B"]


def test_parse_stage2_items_raises_on_truncated_json():
    g = _bare_generator()
    # Truncated array (no closing ']') must NOT fall back to raw text — it must
    # raise so the run fails instead of emailing a raw JSON dict.
    truncated = '[{"headline": "A", "summary": "incomplete'
    with pytest.raises(ValueError):
        g._parse_stage2_items(truncated)


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
    news = [
        {"title": "Primary scoop", "source": "OpenAI Blog", "tier": 1,
         "description": "d", "link": "u1", "published": "", "already_covered": True},
        {"title": "Media take", "source": "TechCrunch AI", "tier": 4,
         "description": "d", "link": "u2", "published": ""},
    ]
    text, items = g._format_news_with_ids(news)
    assert set(items) == {"INT-1", "INT-2"}
    assert "[COVERED]" in text
    assert "Primary/Official" in text and "Tech Media" in text


def test_category_order_is_unique():
    assert len(CATEGORY_ORDER) == len(set(CATEGORY_ORDER))


def test_is_headline_only_detects_google_news_title_echo():
    # Real Google News shape: description is the headline plus the outlet name.
    item = {
        "title": "Trump, Xi agreed that military AI decisions should involve humans, Bessent says - Reuters",
        "description": "Trump, Xi agreed that military AI decisions should involve humans, Bessent says  Reuters",
        "publisher": "Reuters",
        "source": "Reuters (via Google News)",
    }
    assert NewsGenerator._is_headline_only(item)
    assert NewsGenerator._is_headline_only({"title": "Some headline", "description": ""})


def test_is_headline_only_false_for_real_article_text():
    item = {
        "title": "OpenAI ships GPT-6",
        "description": "The new model doubles context length to two million tokens, cuts "
                       "API prices by forty percent, and is rolling out to enterprise customers first.",
        "source": "OpenAI Blog",
    }
    assert not NewsGenerator._is_headline_only(item)


def test_format_selected_news_tags_headline_only_items():
    g = _bare_generator()
    news_items = {
        "INT-1": {"title": "Big headline - CNN", "description": "Big headline  CNN",
                  "publisher": "CNN", "source": "CNN (via Google News)", "link": "u1", "published": ""},
        "INT-2": {"title": "Model launch", "source": "Vendor Blog", "link": "u2", "published": "",
                  "description": "A detailed paragraph describing benchmarks, pricing, availability "
                                 "regions, and the release timeline for developers."},
    }
    text = g._format_selected_news(["INT-1", "INT-2"], news_items)
    assert "### [INT-1] [HEADLINE ONLY] Big headline - CNN" in text
    assert "only the headline above is known" in text
    assert "### [INT-2] Model launch" in text
    assert "A detailed paragraph" in text


def test_build_stage2_prompt_fills_date_and_facts():
    template = "Date: {today}\nFacts:\n{current_facts}\n{count} items:\n{selected_news}\n[{\"k\": 1}]"
    prompt = NewsGenerator._build_stage2_prompt(
        template, count=2, selected_news="NEWS", current_facts=["Fact A", "Fact B"],
        today="November 21, 2026",
    )
    assert "Date: November 21, 2026" in prompt
    assert "- Fact A\n- Fact B" in prompt
    assert "2 items:\nNEWS" in prompt
    assert '[{"k": 1}]' in prompt  # literal JSON braces survive


def test_build_stage2_prompt_prepends_context_when_template_lacks_today():
    prompt = NewsGenerator._build_stage2_prompt(
        "Summarize {count}: {selected_news}", count=1, selected_news="NEWS",
        current_facts=[], today="November 21, 2026",
    )
    assert prompt.startswith("Today's date is November 21, 2026.")
    assert "- (none provided)" in prompt
    assert prompt.endswith("Summarize 1: NEWS")
    assert "{" not in prompt


def test_shipped_stage2_template_uses_date_and_facts_placeholders():
    from src.config import Config
    config = Config("config.yaml")
    assert "{today}" in config.stage2_prompt_template
    assert "{current_facts}" in config.stage2_prompt_template
    assert any("President" in fact for fact in config.current_facts)
