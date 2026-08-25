"""Tests for deterministic near-duplicate detection (src/news/dedup.py).

The clusters below are the real duplicate storylines that leaked into the
2026-08-24 digest (four Alibaba funding rewrites, three humanoid-robot 100m
rewrites). They are the regression this module exists to prevent.
"""
from src.news import dedup
from src.news.generator import NewsGenerator


# --- The real 08-24 duplicate clusters -------------------------------------

ALIBABA = [
    "Alibaba Raises $10 Billion in Record Hong Kong Share Sale for AI Expansion",
    "Alibaba's $10.2 Billion Share Placement Fuels AI Expansion",
    "Alibaba's $10.2bn Share Placement Signals Expanding Chinese AI Investment",
    "Alibaba Secures $10.2 Billion for AI Investments via Share Placement",
]

ROBOT = [
    "Humanoid Robots Surpass Usain Bolt's 100m Record at Beijing Games",
    "Humanoid Robot Shatters Usain Bolt's 100m Record, Raising Questions About its Significance",
    "Humanoid Robot Beats Usain Bolt's 100m Record, But Roboticists Remain Underwhelmed",
]

# Genuinely distinct stories that also appeared on 08-24 — must NOT be merged.
DISTINCT = [
    "OpenAI Unveils Harness for Agent Runtime Dominance Post-Black Whale Launch",
    "SoftBank Plans Record $6.3 Billion Bond Sale for OpenAI Investments",
    "DeepSeek Introduces Weekend Off-Peak Pricing, Affecting AI Compute Costs",
    "Twitch and Amazon Face Lawsuit Over AI Training Data Consent",
]


def test_money_tokens_normalize_amounts():
    assert "10B" in dedup.signature_tokens("Alibaba's $10.2 Billion Share Placement")
    assert "10B" in dedup.signature_tokens("Alibaba's $10.2bn Share Placement")
    assert "10B" in dedup.signature_tokens("Alibaba Raises $10 Billion")


def test_money_parsing_is_strict_no_bare_numbers():
    # "100m" here is a running distance, not $100 million — it must not become a
    # money token (that was the false-merge risk we deliberately avoided).
    toks = dedup.signature_tokens("Humanoid Robot Beats 100m Record")
    assert "100M" not in toks
    assert "400 rallies" and "400M" not in dedup.signature_tokens("Robot wins 400 rallies")


def test_alibaba_cluster_collapses_to_one():
    clusters = dedup.cluster_indices(ALIBABA)
    assert len(clusters) == 1
    assert clusters[0] == [0, 1, 2, 3]


def test_robot_cluster_collapses_to_one():
    clusters = dedup.cluster_indices(ROBOT)
    assert len(clusters) == 1


def test_distinct_stories_are_not_merged():
    clusters = dedup.cluster_indices(DISTINCT)
    assert len(clusters) == len(DISTINCT)


def test_full_08_24_pool_deduplicates_correctly():
    # Interleave duplicates and distinct items the way they arrived in one run.
    pool = ALIBABA + ROBOT + DISTINCT
    clusters = dedup.cluster_indices(pool)
    # 1 (alibaba) + 1 (robot) + len(DISTINCT) distinct = 2 + 4
    assert len(clusters) == 2 + len(DISTINCT)


def test_deduplicate_keeps_representative_per_cluster():
    items = [{"title": h, "summary": ""} for h in ALIBABA + ROBOT + DISTINCT]
    kept = dedup.deduplicate(items, text_key="title")
    assert len(kept) == 2 + len(DISTINCT)


# --- Integration with NewsGenerator ----------------------------------------

def _bare_generator() -> NewsGenerator:
    return NewsGenerator.__new__(NewsGenerator)


def test_pre_selection_collapse_keeps_most_authoritative_source():
    g = _bare_generator()
    items = [
        {"title": ALIBABA[0], "source": "SEO Farm", "tier": 7, "description": "long-ish text here"},
        {"title": ALIBABA[1], "source": "Reuters", "tier": 3, "description": "x"},
        {"title": ALIBABA[2], "source": "Blog", "tier": 6, "description": "y"},
    ]
    kept = g._collapse_duplicate_candidates(items)
    assert len(kept) == 1
    assert kept[0]["source"] == "Reuters"  # lowest tier number wins


def test_pre_selection_collapse_preserves_covered_flag():
    g = _bare_generator()
    items = [
        {"title": ALIBABA[0], "source": "A", "tier": 3, "description": "x"},
        {"title": ALIBABA[1], "source": "B", "tier": 4, "description": "y", "already_covered": True},
    ]
    kept = g._collapse_duplicate_candidates(items)
    assert len(kept) == 1
    assert kept[0]["already_covered"] is True


def test_post_stage2_dedup_collapses_and_keeps_longer_summary():
    g = _bare_generator()
    items = [{"headline": h, "summary": "short"} for h in ALIBABA]
    items[2]["summary"] = "a much longer and more complete analytical summary of the round"
    kept = g._deduplicate_items(items)
    assert len(kept) == 1
    assert kept[0]["summary"].startswith("a much longer")
