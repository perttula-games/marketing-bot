---
name: "marketing-bot"
description: "Operates the nemo-marketing-bot CLI to generate and publish LinkedIn, X, and Instagram posts using NVIDIA Nemotron. Use when the user asks to draft a post, schedule a campaign, poll an RSS feed for announcements, check publish status, or tune brand voice. Covers dry-run verification, per-platform length/tone rules, and safe publish workflow."
---

<!-- Marketing bot skill for NemoClaw sandboxes -->

# Marketing Bot

Operate the installed `nemo-marketing-bot` package (CLI entrypoint: `nemo-bot`) to generate and publish platform-native social posts.

## Context

The sandbox ships with the `nemo-marketing-bot` Python package pre-installed. It uses NVIDIA Nemotron (via `integrate.api.nvidia.com`) to draft posts for LinkedIn, X, and Instagram, and publishes them through each platform's official API.

All credentials live in `/sandbox/.env` (loaded by pydantic-settings). The agent MUST NOT print secrets back to the user; refer to them by name only.

## When to Use

- User asks to draft, review, or publish a social post.
- User asks about an announcement, product update, release, or customer story.
- User wants to start, pause, or edit a recurring campaign.
- User shares a blog/article URL and wants it turned into posts.
- RSS-driven postings need a status check.

## Core Commands

Always prefer `nemo-bot` CLI over raw Python calls.

| Command | Purpose |
|---|---|
| `nemo-bot generate --topic "<t>" --details "<d>" [--url <u>] [--tags a,b]` | Draft posts without publishing. Always run this first. |
| `nemo-bot post --topic "<t>" --details "<d>" --platforms linkedin,x` | Generate AND publish. Requires `DRY_RUN=false`. |
| `nemo-bot from-rss --feed <url> --limit N [--publish]` | Turn latest feed items into posts. |
| `nemo-bot schedule --config schedule.yaml` | Run the APScheduler loop (already managed as a sandbox service — do not start a second one). |

## Safe Publish Workflow

Follow this order every time the user asks to publish:

1. **Draft**: run `nemo-bot generate` and show the output to the user.
2. **Confirm**: ask the user to approve per platform. If they ask for changes, regenerate with updated `--details` or `--tags`.
3. **Check dry-run flag**: read `/sandbox/.env`. If `DRY_RUN=true`, warn the user that `post` will only print, not publish.
4. **Publish**: run `nemo-bot post` with the approved `--platforms`.
5. **Report**: summarize the per-platform results dict returned by `publish_bundle` (e.g. `linkedin: urn:li:share:...`, `x: 17xxxx...`, or `error: ...`).

Never publish without an explicit "yes, publish" from the user unless a scheduled job is running (those are pre-approved via `schedule.yaml`).

## Per-Platform Rules

The generator already enforces these in its system prompt, but verify before publish:

- **LinkedIn**: 1–3 short paragraphs, 3–5 hashtags at the end, first line is a hook, no emoji spam. Optional link at the end.
- **X**: single post, ≤ 280 chars including URL (23 chars for t.co). Max 2 hashtags. Hook in first 8 words.
- **Instagram**: caption up to ~2200 chars, 5–15 hashtags. **Requires a public image URL** — the `image_prompt` field must start with `http` or the publish will fail. If missing, ask the user for an image URL or skip `--platforms instagram`.

## Credentials & Health

If any platform publish fails with an auth error:

1. `nemo-bot doctor` (if present) to test credentials.
2. Otherwise, check `/sandbox/.env` keys:
   - `NVIDIA_API_KEY` (required for all generation)
   - `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_URN`
   - `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
   - `IG_ACCESS_TOKEN`, `IG_USER_ID`
3. LinkedIn tokens expire ~60 days. Suggest re-running the LinkedIn OAuth flow if 401.
4. X free tier = ~17 posts / 24h per user. If rate-limited, pause the `blog-rss-poll` job.

## Editing the Schedule

The scheduler config lives at `/sandbox/schedule.yaml`. Jobs have two types:

```yaml
jobs:
  - name: weekly-product-update
    cron: "0 9 * * MON"
    type: topic
    topic: "Weekly product update"
    details: "..."
    platforms: [linkedin, x]

  - name: blog-rss-poll
    cron: "*/30 * * * *"
    type: rss
    feed: "https://blogs.nvidia.com/feed/"
    limit: 2
    platforms: [linkedin, x, instagram]
```

After editing, restart the scheduler service: `systemctl --user restart nemo-bot-scheduler` inside the sandbox (or whichever init the sandbox uses — check `ps -ef | grep nemo-bot`).

## Brand Voice

Brand rules live in `/sandbox/.openclaw/workspace/SOUL.md` under the "Marketing voice" section. When the user asks to tweak tone, edit that file; the generator picks up changes via the workspace mount on the next run.

## Troubleshooting

| Symptom | Action |
|---|---|
| "Publishing to instagram failed: image_prompt must be http" | Ask user for an image URL, or drop `instagram` from `--platforms`. |
| "401 from LinkedIn" | Token expired — user must refresh via their LinkedIn developer app. |
| "429 from X" | Rate-limited. Pause RSS job, wait for 24h window reset. |
| Nemotron call hangs | Check `NVIDIA_API_KEY` and network policy allows `integrate.api.nvidia.com`. |
| Duplicate posts from RSS | State file (`~/.nemo-bot/state.db`) may be missing — check it exists and is writable. |

## Do Not

- Do not call Nemotron directly from the agent loop. Use `nemo-bot generate` so brand voice, length rules, and logging stay consistent.
- Do not edit `/sandbox/.env` to change `DRY_RUN=false` without explicit user confirmation in the same session.
- Do not publish the same `--topic` twice in under 6 hours without the user explicitly acknowledging it's intentional.
