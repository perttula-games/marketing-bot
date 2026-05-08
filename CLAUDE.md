# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`nemo-marketing-bot` is a Python CLI that uses NVIDIA Nemotron (via the OpenAI-compatible `integrate.api.nvidia.com` endpoint) to generate platform-native game marketing drafts, plan creator outreach, and publish to social platforms that have official APIs. It is a stateless one-shot CLI; recurring runs are driven by an external scheduler (cron / systemd timer / GitHub Actions).

## Commands

```bash
# Install in editable mode
python3.13 -m venv .venv && source .venv/bin/activate && pip install -e .

# Set up env (fill NVIDIA_API_KEY at minimum)
cp .env.example .env

# Run tests
pytest                           # all tests
pytest tests/test_security.py    # single file

# CLI entrypoint: nemo-bot
nemo-bot generate --topic "..." --details "..." --platforms all-content
nemo-bot post --topic "..." --platforms linkedin,bluesky,discord
nemo-bot from-rss --feed "https://..." --limit 2 --publish
nemo-bot review list
nemo-bot strategy show --compiled
nemo-bot creators plan --game "NemoClaw" --channels tiktok,youtube,instagram
nemo-bot growth plan --game "Kalma" --channels bluesky,x
nemo-bot telegram-approve
```

## Architecture

The data flow is: **input (CLI args / RSS feed) → Brief → Generator (Nemotron LLM) → PostBundle → ReviewStore / Publishers**.

### Pipeline layers

- **`cli.py`** — Typer entrypoint with subcommands: `generate`, `post`, `publish`, `from-rss`, `review`, `creators`, `strategy`, `growth`, `telegram-approve`. Platform parsing accepts aliases like `all-content` or `publish`.
- **`ingest.py`** — Turns CLI args or RSS feed entries into `Brief` objects. RSS fetching validates URLs against SSRF (no file://, no private/loopback IPs), enforces `MAX_FEED_BYTES = 5 MiB`, manually follows redirects but re-validates every hop.
- **`models.py`** — Pydantic models: `Brief` (source material), `GeneratedPost` (single platform output), `PostBundle` (brief + list of posts). `Platform` is the union of all 10 supported channels. `PublishPlatform` is the subset of 5 with API publishers.
- **`generator.py`** — Calls Nemotron via `openai.OpenAI` with temperature=0.7, top_p=0.95. `PLATFORM_RULES` dict defines length/tone/format rules per platform. `ContentGenerator.generate()` produces a PostBundle; `.revise()` rewrites a single post per natural-language instruction. Tenacity retries (3 attempts, exponential backoff). `_extract_json()` tolerates stray prose or fenced code blocks in model output.
- **`strategy.py`** — Loads the editable marketing system prompt from `marketing-system-prompt.md`. `build_generation_system_prompt()` concatenates: editable prompt + `CORE_SYSTEM_CONTRACT` (non-negotiable OS rules including prompt-injection isolation) + `GENERATION_RESPONSE_CONTRACT` (JSON-only response). `build_revision_system_prompt()` swaps the response contract for revision rules.
- **`pipeline.py`** — Orchestrates generate → review/publish. `run_once()` is the main entrypoint: generates a bundle, then either publishes (if `auto_publish=True`) or enqueues for review. `publish_bundle()` runs safety checks via `check_post_safety()` before each publish and skips non-publishable platforms.
- **`publishers.py`** — Five publishers implementing a `Publisher` Protocol: `LinkedInPublisher` (UGC Posts API), `XPublisher` (tweepy OAuth 1.0a), `InstagramPublisher` (Graph API, requires public image URL on allowlisted host), `BlueskyPublisher` (AT Protocol with session caching and link-preview embeds via uploadBlob), `DiscordPublisher` (webhook). All respect `settings.dry_run`.
- **`review.py`** — SQLite-backed review queue (`~/.nemo-bot/state.db`, WAL mode). Status flow: `pending → approved → published` (or `rejected` / `publish_failed`). `ReviewStore` tracks edits in a separate `edits` table. `mark_notified()` / `list_unnotified_pending()` support Telegram push notifications. The schema uses additive migrations (no framework — just ALTER TABLE in `__init__`).
- **`telegram_bot.py`** — Async Telegram bot (`python-telegram-bot`) for review workflow. Inline buttons for approve/reject/publish/quick-edit/AI-discuss. `_poll_new_drafts()` pushes unnotified pending drafts to configured approver chats. Chat-gated: `TELEGRAM_APPROVER_CHAT_IDS` required; `TELEGRAM_APPROVER_USER_IDS` optional for group-chat auth. AI discussion uses `ContentGenerator.revise()`.
- **`security.py`** — SSRF defense (`assert_safe_url()` with DNS resolution + denylist), Instagram image host allowlist, prompt-injection isolation (`sanitize_untrusted_text()`, `wrap_untrusted()` wraps in XML-like tags the system prompt treats as data-only), pre-publish content safety check (`check_post_safety()` validates length, forbidden phrases, repost markers, Discord mentions, Instagram image URL allowlist).
- **`config.py`** — pydantic-settings loading from `.env`. All secrets and feature flags are here.
- **`creator_outreach.py`** — Static planning data: manual setup tasks per channel, creator target profiles with search queries/deliverables/metrics, outreach DM templates in English and Finnish.
- **`growth.py`** — Organic follower growth plan for Bluesky and X: daily actions, target pools, engagement safety rules. Produces markdown or CSV.

### Safety defaults

`DRY_RUN=true` by default — all publishers only log in dry-run mode. The pipeline runs `check_post_safety()` before every publish, and `assert_safe_url()` validates every URL before it enters a prompt or an HTTP request.
