# nemo-marketing-bot

Marketing content bot that uses **NVIDIA Nemotron** (via the OpenAI-compatible
`integrate.api.nvidia.com` endpoint) to generate platform-native game marketing
drafts, plan creator outreach, and publish supported posts.

## Features

- Generates posts that follow each platform's rules (length, tone, hashtags).
- Drafts manual-channel content for Steam, TikTok/Reels/Shorts,
  YouTube, Reddit and Jodel.
- Plans creator outreach by channel: target profile, search queries,
  deliverables, acceptance criteria, metrics and reusable DM templates.
- Uses an editable marketing system prompt so strategy and brand voice can be
  changed without code changes.
- Pulls briefs from either a CLI prompt or an RSS/Atom feed.
- Publishes via APIs: LinkedIn UGC Posts, Bluesky AT Protocol, and Discord webhooks.
- Stateless one-shot CLI: drive recurring runs from cron, a systemd timer, or
  a GitHub Actions schedule.
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

The strategy layer lives in `marketing-system-prompt.md` by default. Edit that
file when you want to change how the bot positions each game, which content
pillars it prioritizes, or how creator outreach should sound. The generator
reloads it on each run, so the next `generate`, `post`, `from-rss`, or review
edit uses the newest text.

Useful commands:

```bash
nemo-bot strategy path
nemo-bot strategy show
nemo-bot strategy show --compiled
nemo-bot strategy init --path marketing-system-prompt.md
```

### Safety defaults

`DRY_RUN=true` is the default. Flip it to `false` in `.env` only when you are
ready to publish live.

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
| Discord | Server settings → Integrations → Webhooks | Create a webhook for the target channel and set `DISCORD_WEBHOOK_URL`. |

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
  --details "Show the new combat mechanic and route people to the latest devlog." \
  --platforms all-content
```

`all-content` includes LinkedIn, X, Instagram, Steam, Discord, TikTok, YouTube,
Reddit and Jodel drafts. Live API publishing is available for LinkedIn,
Bluesky, and Discord; all other channels are intentionally manual drafts.

### Creator outreach and page setup

Print the manual account/page checklist plus channel-specific creator targets:

```bash
nemo-bot creators plan \
  --game "NemoClaw" \
  --genre "PC indie/AA action game" \
  --audience "PC and console players" \
  --channels tiktok,youtube,instagram,twitch,lurkit,keymailer
```

Export the creator target matrix to a spreadsheet-friendly CSV:

```bash
nemo-bot creators export \
  --output outreach/nemoclaw-creators.csv \
  --game "NemoClaw" \
  --genre "PC indie/AA action game"
```

Use this before manual page creation so every account has the same CTA, link
tracking pattern, creator support path and deliverable expectations.

### Generate and publish

```bash
# Set DRY_RUN=false in .env once you're ready to actually post.
nemo-bot post --topic "Customer story: ACME" --details "Deployed in 3 weeks." \
  --platforms linkedin,bluesky,discord
```

### From an RSS feed

```bash
nemo-bot from-rss --feed https://blogs.nvidia.com/feed/ --limit 2 --publish
```

### Run on a schedule

The CLI is a stateless one-shot — drive it from any external scheduler.

Example crontab (every 30 min, queue drafts for Telegram review):

```cron
*/30 * * * * cd /opt/marketing-bot && /opt/marketing-bot/.venv/bin/nemo-bot from-rss --feed https://example.com/feed.xml --limit 2 >> /var/log/marketing-bot.log 2>&1
```

Example systemd timer (`/etc/systemd/system/marketing-bot.timer`):

```ini
[Unit]
Description=Run marketing-bot every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

Example GitHub Actions (`.github/workflows/devlog.yml`):

```yaml
on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -e .
      - run: nemo-bot from-rss --feed "$FEED_URL" --limit 2
        env:
          NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
          DRY_RUN: "false"
          FEED_URL: ${{ vars.FEED_URL }}
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
  publishers.py   # LinkedIn / Bluesky / Discord (+ optional X/Instagram clients)
  strategy.py     # Editable marketing system prompt loader
```

## Notes & limits

- **Instagram feed posts require a publicly hosted image URL.** For now, pass
  one in the post's `image_prompt` (when it starts with `http`). Extending the
  pipeline with an image generator (e.g. an NVIDIA NIM diffusion endpoint or
  an S3-hosted render) is a natural next step.
- **TikTok, YouTube, Steam, Reddit and Jodel are draft-only channels.**
  The bot creates the copy/script/checklist, then a human publishes or uploads
  it manually through the platform UI.
- **Discord webhooks** are secret credentials. If leaked, rotate the webhook
  from Discord server settings.
- **LinkedIn tokens expire** (60 days typical). Rotate or automate refresh.
- The generator uses `temperature=0.7`; tweak in `generator.py` if you want
  more deterministic output.

## License

MIT — use at your own risk, and comply with each platform's automation rules.
