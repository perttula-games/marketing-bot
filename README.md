# nemo-marketing-bot

Marketing content bot that uses **NVIDIA Nemotron** (via the OpenAI-compatible
`integrate.api.nvidia.com` endpoint) to generate platform-native game marketing
drafts, plan creator outreach, and publish supported posts on a cron schedule.

## Features

- Generates posts that follow each platform's rules (length, tone, hashtags).
- Drafts manual-channel content for Steam, Discord, TikTok/Reels/Shorts,
  YouTube, Reddit and Jodel.
- Plans creator outreach by channel: target profile, search queries,
  deliverables, acceptance criteria, metrics and reusable DM templates.
- Plans manual organic follower growth for X and Bluesky with feed/search
  targets, daily engagement actions, safety limits and KPI tracking columns.
- Uses an editable marketing system prompt so strategy and brand voice can be
  changed without code changes.
- Pulls briefs from either a CLI prompt or an RSS/Atom feed.
- Publishes via official APIs: LinkedIn UGC Posts, X API v2, Instagram Graph API, and Bluesky AT Protocol.
- Schedules recurring campaigns and RSS polls from a YAML config (APScheduler).
- `DRY_RUN=true` (default) prints posts instead of publishing — safe to try.

## Setup

```bash
cd ~/nemo-marketing-bot
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Fill in NVIDIA_API_KEY (from https://build.nvidia.com/) at minimum.
```

### Marketing system prompt

The Kalma source-of-truth fact sheet lives in `kalma-marketing-foundation.md`.
The strategy layer lives in `marketing-system-prompt.md` by default. Edit that
file when you want to change how the bot positions Kalma, which content
pillars it prioritizes, or how creator outreach should sound. The generator
reloads it on each run, so the next `generate`, `post`, `from-rss`, scheduled
job, or review edit uses the newest text.

Useful commands:

```bash
nemo-bot strategy path
nemo-bot strategy show
nemo-bot strategy show --compiled
nemo-bot strategy init --path marketing-system-prompt.md
```

In NemoClaw the image seeds this file to `/sandbox/marketing-system-prompt.md`.
Ask the agent to edit that file when the marketing strategy changes, then ask it
to run a dry-run draft before publishing.

### Safety defaults

`DRY_RUN=true` is the default. Scheduled jobs also require a second explicit
gate before they can publish live: set `auto_publish: true` on the job and
`ALLOW_SCHEDULED_AUTOPUBLISH=true` in the environment. Quoted YAML values such
as `auto_publish: "false"` are rejected instead of coerced.

For Telegram approvals, configure `TELEGRAM_APPROVER_CHAT_IDS`. If approvals
happen in a group chat, also configure `TELEGRAM_APPROVER_USER_IDS` so only the
listed users can approve or publish.

### API keys you'll need

| Service | Where | Scope / notes |
| --- | --- | --- |
| NVIDIA Nemotron | https://build.nvidia.com/ → pick a Nemotron model → "Get API Key" | Required for generation. |
| LinkedIn | https://www.linkedin.com/developers/ → create app → Sign In with LinkedIn v2 + `w_member_social` | Obtain a user access token + your `urn:li:person:<id>`. |
| X / Twitter | https://developer.x.com/ → project → User authentication settings (OAuth 1.0a, Read+Write) | Set the 4 OAuth 1.0a keys/secrets. |
| Instagram | https://developers.facebook.com/ → Business app → Instagram Graph API | Link an IG Business/Creator account to a FB Page; get a long-lived token and the IG user id. |
| Bluesky | https://bsky.app/settings/app-passwords | Create an app password and set `BLUESKY_IDENTIFIER` + `BLUESKY_APP_PASSWORD`. |

## Usage

### One-shot generation (no publishing)

```bash
nemo-bot generate \
  --topic "Nemotron 2 launch" \
  --details "Announce the new reasoning modes and 2x throughput." \
  --url "https://example.com/launch" \
  --tags "AI,Nemotron,GenAI"
```

Generate content for the broader manual game marketing stack:

```bash
nemo-bot generate \
  --topic "Demo reveal" \
  --details "Show the new combat mechanic and route people to the Steam wishlist." \
  --platforms all-content
```

`all-content` includes LinkedIn, X, Bluesky, Instagram, Steam, Discord, TikTok,
YouTube, Reddit and Jodel drafts. LinkedIn, X, Instagram and Bluesky have API
publishers; the other channels are intentionally manual drafts.

For the current Kalma social-only test, generate X and Bluesky drafts without
publishing:

```bash
nemo-bot generate \
  --topic "Kalma first look" \
  --details "First-person survival horror from Perttula Game Studio. Unreal Engine 5.7. Dying northern town buried under snow. CTA: read the devlog and follow for updates." \
  --url "https://perttulagamestudio.com/devlog/kalma-first-look" \
  --platforms x,bluesky
```

### Creator outreach and page setup

Print the manual account/page checklist plus channel-specific creator targets:

```bash
nemo-bot creators plan \
  --game "Kalma" \
  --genre "PC first-person survival horror" \
  --audience "PC horror players" \
  --channels tiktok,youtube,instagram,twitch,lurkit,keymailer
```

Export the creator target matrix to a spreadsheet-friendly CSV:

```bash
nemo-bot creators export \
  --output outreach/kalma-creators.csv \
  --game "Kalma" \
  --genre "PC first-person survival horror"
```

Use this before manual page creation so every account has the same CTA, link
tracking pattern, creator support path and deliverable expectations.

### Organic follower growth

Build a safe manual action plan for growing the new X and Bluesky accounts:

```bash
nemo-bot growth plan \
  --game "Kalma" \
  --positioning "PC first-person survival horror" \
  --audience "PC horror players and indie horror developers" \
  --channels bluesky,x
```

Export the daily action list for tracking:

```bash
nemo-bot growth export \
  --output outreach/kalma-growth-actions.csv \
  --game "Kalma" \
  --channels bluesky,x
```

Growth actions are intentionally manual. The bot should not automate follows,
likes, reposts, DMs or replies; it creates target pools, reply prompts, limits
and KPI columns so the account grows through relevant interactions.

### Generate and publish

```bash
# Set DRY_RUN=false in .env once you're ready to actually post.
nemo-bot post --topic "Customer story: ACME" --details "Deployed in 3 weeks." \
  --platforms linkedin,x
```

### From an RSS feed

```bash
nemo-bot from-rss --feed https://blogs.nvidia.com/feed/ --limit 2 --publish
```

### Scheduled / automated

```bash
nemo-bot schedule --config schedule.yaml
```

`schedule.yaml` defines cron-triggered jobs of type `topic` or `rss`. See the
example included in the repo. Scheduled jobs use the same active marketing
system prompt as manual CLI runs, so changing `marketing-system-prompt.md`
updates future automated drafts.

Scheduled jobs queue drafts by default. Live scheduled publishing requires both:

```yaml
auto_publish: true
```

and:

```bash
ALLOW_SCHEDULED_AUTOPUBLISH=true
```

## Project layout

```
src/nemo_marketing_bot/
  cli.py          # Typer entrypoint
  config.py       # pydantic-settings (.env)
  creator_outreach.py # Creator search, setup checklists, outreach templates
  generator.py    # Nemotron call via OpenAI SDK
  ingest.py       # CLI + RSS -> Brief
  models.py       # Brief, GeneratedPost, PostBundle
  pipeline.py     # generate -> publish glue
  publishers.py   # LinkedIn / X / Instagram / Bluesky
  scheduler.py    # APScheduler runner
  strategy.py     # Editable marketing system prompt loader
```

## Notes & limits

- **Instagram feed posts require a publicly hosted image URL.** For now, pass
  one in the post's `image_prompt` (when it starts with `http`). Extending the
  pipeline with an image generator (e.g. an NVIDIA NIM diffusion endpoint or
  an S3-hosted render) is a natural next step.
- **TikTok, YouTube, Steam, Discord, Reddit and Jodel are draft-only channels.**
  The bot creates the copy/script/checklist, then a human publishes or uploads
  it manually through the platform UI.
- **X free tier** allows ~17 posts/24h per user — don't wire up high-frequency
  RSS jobs without monitoring quota.
- **LinkedIn tokens expire** (60 days typical). Rotate or automate refresh.
- The generator uses `temperature=0.7`; tweak in `generator.py` if you want
  more deterministic output.

## License

MIT — use at your own risk, and comply with each platform's automation rules.
