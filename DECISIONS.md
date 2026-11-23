# AI News Bot — Design Decisions

> Formerly TODO.md (originally an AI-generated code review from 2026-02-11,
> rewritten 2026-07-14, renamed 2026-07-15 once the last open item shipped).
> This file records what was built and why, and — more importantly — what was
> deliberately **not** built. Check the "Rejected" section before proposing
> improvements: several obvious-sounding ideas were considered and turned down
> for reasons that still hold.

## Done (kept here so it isn't re-proposed)

- **Startup config validation** — `Config.validate()` fails fast before any
  feed fetching or LLM spend, collecting every problem into one error:
  unknown/keyless LLM provider (exact env-var name per provider), unknown
  notification methods, missing credentials per enabled method, empty
  NOTIFICATION_METHODS outside dry-run, and AI_RESPONSE_LANGUAGE with no
  supported code. Dry-run skips notifier checks but still requires the LLM
  key. Note: `load_dotenv(override=True)` resolves `.env` relative to
  `src/config.py`, so on a dev machine the repo `.env` overrides shell env
  vars — validation bites mainly in CI, where env comes from secrets.

- **RSS retry** — `_get_with_retry` retries network errors, 5xx and 429 up
  to 3 attempts with 2s/4s backoff; other 4xx fail immediately. A feed that
  still fails is skipped, never fatal.

- **Concurrent RSS fetching** — `_fetch_feed_group` fetches feeds through a
  10-worker `ThreadPoolExecutor`; full 60-feed run dropped from minutes to
  ~5s. Results are collected in feed order so dedup tie-breaking and the
  tier sort stay deterministic.

- **Deduplication** — tier-aware Jaccard title dedup in `fetcher.py`, plus
  cross-run history dedup (`data/news_history.json`), plus near-identical-title
  hard drop (commit `fafd5f2`).
- **Source trust** — feed tier system, `blocked_sources` blocklist, and
  publisher-level re-tiering of Google News items with an "Unverified" tier
  (commit `31d83a0`, after a content farm's fabricated story reached a digest).
- **LLM retry** — Gemini provider retries 503/429 with jittered backoff.
  (Other providers have no retry; add only if a non-Gemini provider goes
  into real use.)

- **Stage-2 grounding against stale model knowledge** (2026-11-23) — the
  2026-11-21 digest called Trump "former President": the model (training data
  ending Jan 2025) padded a headline-only Google News item from memory. Stage 2
  now gets today's date, a `news.current_facts` list in `config.yaml`
  (maintained by hand; review when an office-holder or CEO changes), and a rule
  against stating roles/titles the source doesn't give. Items whose
  description adds <8 words beyond the title and publisher are tagged
  `[HEADLINE ONLY]` and asked for 2–3 sentences with no added facts.
- **Gemini 4 Hydrogen as default, 3.5 Flash-Lite as backup** (2026-11-23) —
  `gemini-2.5-flash` (the old backup) is deprecated and rerouted from
  2026-12-01. In a one-run-each dry-run comparison, Hydrogen followed the
  selection rules best (16 stories after the per-publisher cap vs 10 for
  Flash-Lite, which over-picks single publishers and ignores the headline-only
  length rule). Gemini 3.x+ models think before answering and that counts
  against `max_output_tokens`; it can't be turned off (Flash-Lite returns 400
  on `thinking_budget=0`, Hydrogen ignores it). Hence Stage 1's fixed 4000
  limit became `stage1_max_output_tokens: 16000` and Stage 2 went to 32000
  (Hydrogen used 15554 of 16000). Each Gemini call logs its thinking/output
  token usage. The `LLM_MODEL` secret overrides the default, so leave it
  unset unless pinning a model deliberately.

## Rejected / superseded (with reasons)

- **Multi-language output (zh, de)** — removed 2026-07-15 at the owner's
  request: only the English digest is used. Removal covered the per-language
  loop in `main.py`, `AI_RESPONSE_LANGUAGE`, `LANGUAGE_NAMES`, the Chinese and
  German "domestic" feed lists, the international/domestic split in the
  fetcher/generator (now a single flat item list; IDs stay `INT-n` so the
  prompts didn't change), and the notifiers' `language` parameter. Restoring a
  language means reverting that commit, not re-implementing from scratch.

- **Quality pre-scoring before Stage 1** — superseded by the tier system +
  publisher re-tiering + Stage-1 selection criteria; keyword scoring is a
  cruder version of what exists.
- **Incremental update mode** — superseded by `lookback_hours` + the committed
  news history; the bot runs once daily, there is no high-frequency use case.
- **Heuristic Stage-1 fallback / "simplified digest" fallback on Stage-2
  failure** — contradicts the deliberate fail-loudly design: a run must fail
  rather than silently send degraded output (see `_parse_stage2_items`
  docstring). Stage 1 already falls back to the first 18 tier-sorted (most
  authoritative) items.
- **RSS cache for local dev** — marginal; production runs once daily in CI.
- **Metrics collection module** — overkill for a daily digest bot; logs cover
  current needs.
- **Cutting headline-only summaries to 3 sentences after generation**
  (2026-11-23) — models often ignore the 2–3 sentence rule for `[HEADLINE
  ONLY]` items, but the extra sentences are general significance commentary,
  not invented facts. Declined by the owner: cosmetic gain, and a regex
  sentence splitter would break on abbreviations like "U.S.".
