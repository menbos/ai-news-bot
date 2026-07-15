# AI News Bot — TODO

> Rewritten 2026-07-14. The original version of this file was an AI-generated
> code review saved on 2026-02-11; most of it had since been implemented,
> superseded, or invalidated. Items below reflect the current code.

## Open

(nothing)

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

## Rejected / superseded (with reasons)

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
