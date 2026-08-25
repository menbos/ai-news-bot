"""
Deterministic near-duplicate detection for news headlines.

Used in two places within a single run:
  1. Pre-Stage-1: collapse the fetched candidate pool so the selector never
     sees four rewrites of the same story (saves Stage-2 tokens too).
  2. Post-Stage-2: a guaranteed backstop over the rendered items.

The comparison deliberately avoids Jaccard over the full token set: the LLM
rewrites headlines with varied filler ("Fuels AI Expansion", "Signals Expanding
Chinese Investment"), which inflates the union and drags Jaccard below any usable
threshold even when the stories are identical. Instead we use:

  * the **overlap coefficient** (|A∩B| / min(|A|,|B|)), robust to one headline
    being wordier than the other;
  * a **money token** so "$10.2 billion" / "$10.2bn" / "$10 billion" all collapse
    to a single "10B" signal — the strongest indicator that two funding stories
    are the same event. Parsing is strict (requires a currency sign or a
    fully-spelled unit word) so a distance like "100m" is never misread as
    "100 million";
  * **single-linkage clustering** (union-find) so transitively-related rewrites
    (A~B, B~C, but A≁C directly) still land in one cluster.

Nothing here generates text; it only groups already-fetched items, so it cannot
introduce facts that were not in the sources.
"""
import re
from typing import Callable, List, Sequence, Set

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "is", "are", "was", "were", "with", "its", "as", "by", "how", "why",
    "what", "that", "this", "has", "have", "will", "from", "new", "get",
    "says", "said", "report", "reports", "update", "updates", "but", "amid",
    "amidst", "after", "over", "into", "via", "plans", "raises", "raising",
    "questions", "about", "significance", "signals", "fuels", "secures",
}

# Default overlap-coefficient threshold above which two headlines are treated as
# the same story. 0.5 collapsed every real 08-24 duplicate cluster while leaving
# genuinely distinct stories separate (see tests/test_dedup.py).
DEFAULT_THRESHOLD = 0.5

_UNIT_LETTER = {"b": "B", "bn": "B", "billion": "B",
                "m": "M", "mn": "M", "million": "M",
                "t": "T", "tn": "T", "trillion": "T",
                "k": "K", "thousand": "K"}


def _money_tokens(text: str) -> Set[str]:
    """Normalized currency amounts, e.g. '10B'. Strict: a bare number with no
    currency sign and no spelled-out unit word is ignored, so distances/counts
    ('100m record', '400 rallies') are never treated as money."""
    out: Set[str] = set()
    low = text.lower()
    # $-prefixed amounts: "$10.2 billion", "$10.2bn", "$6.3b", "$500"
    for m in re.finditer(r"\$\s*(\d+(?:\.\d+)?)\s*(trillion|billion|million|thousand|bn|mn|tn|[bmtk])?\b", low):
        num = round(float(m.group(1)))
        unit = _UNIT_LETTER.get(m.group(2) or "", "")
        out.add(f"{num}{unit}")
    # Spelled-out unit without a $ sign: "10.2 billion", "6.3 billion"
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(trillion|billion|million|thousand)\b", low):
        num = round(float(m.group(1)))
        out.add(f"{num}{_UNIT_LETTER[m.group(2)]}")
    return out


def signature_tokens(text: str) -> Set[str]:
    """The set of comparison tokens for a headline: content words (len > 3, not a
    stopword) plus normalized money tokens."""
    words = re.sub(r"[^\w\s]", " ", (text or "").lower()).split()
    base = {w for w in words if w not in _STOPWORDS and len(w) > 3}
    return base | _money_tokens(text or "")


def overlap_coefficient(a: Set[str], b: Set[str]) -> float:
    """|A∩B| / min(|A|,|B|); 0 when either side is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def cluster_indices(texts: Sequence[str], threshold: float = DEFAULT_THRESHOLD) -> List[List[int]]:
    """Single-linkage cluster the given texts by headline overlap.

    Returns a list of clusters, each a list of indices into ``texts``. Every
    input index appears in exactly one cluster; cluster order follows first
    appearance, and indices within a cluster are sorted ascending.
    """
    n = len(texts)
    tokens = [signature_tokens(t) for t in texts]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for i in range(n):
        # Skip headlines too short to compare reliably (< 3 signal tokens).
        if len(tokens[i]) < 3:
            continue
        for j in range(i + 1, n):
            if len(tokens[j]) < 3:
                continue
            if overlap_coefficient(tokens[i], tokens[j]) >= threshold:
                union(i, j)

    clusters: dict = {}
    order: List[int] = []
    for i in range(n):
        root = find(i)
        if root not in clusters:
            clusters[root] = []
            order.append(root)
        clusters[root].append(i)
    return [sorted(clusters[root]) for root in order]


def deduplicate(
    items: List[dict],
    text_key: str,
    threshold: float = DEFAULT_THRESHOLD,
    representative: Callable[[List[dict]], dict] = None,
) -> List[dict]:
    """Collapse near-duplicate items to one per cluster.

    Args:
        items: the items to deduplicate.
        text_key: the dict key holding the headline/title to compare on.
        threshold: overlap-coefficient cutoff.
        representative: given a cluster's items (in original order), returns the
            one to keep. Defaults to the item with the longest ``summary``.

    Order of the first member of each cluster is preserved.
    """
    if not items:
        return []
    if representative is None:
        def representative(cluster):  # noqa: E306
            return max(cluster, key=lambda it: len(it.get("summary", "") or ""))

    texts = [it.get(text_key, "") or "" for it in items]
    kept: List[dict] = []
    for cluster in cluster_indices(texts, threshold):
        members = [items[i] for i in cluster]
        kept.append(representative(members))
    return kept
