# nemo-marketing-bot

Marketing content bot that uses **NVIDIA Nemotron** (via the OpenAI-compatible
`integrate.api.nvidia.com` endpoint) to generate platform-native posts for
**LinkedIn**, **X** and **Instagram**, and can publish them on a cron schedule.

## Features

- Generates posts that follow each platform's rules (length, tone, hashtags).
- Pulls briefs from either a CLI prompt or an RSS/Atom feed.
- Publishes via official APIs: LinkedIn UGC Posts, X API v2, Instagram Graph API.
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

### API keys you'll need

| Service | Where | Scope / notes |
| --- | --- | --- |
| NVIDIA Nemotron | https://build.nvidia.com/ → pick a Nemotron model → "Get API Key" | Required for generation. |
| LinkedIn | https://www.linkedin.com/developers/ → create app → Sign In with LinkedIn v2 + `w_member_social` | Obtain a user access token + your `urn:li:person:<id>`. |
| X / Twitter | https://developer.x.com/ → project → User authentication settings (OAuth 1.0a, Read+Write) | Set the 4 OAuth 1.0a keys/secrets. |
| Instagram | https://developers.facebook.com/ → Business app → Instagram Graph API | Link an IG Business/Creator account to a FB Page; get a long-lived token and the IG user id. |

## Usage

### One-shot generation (no publishing)

```bash
nemo-bot generate \
  --topic "Nemotron 2 launch" \
  --details "Announce the new reasoning modes and 2x throughput." \
  --url "https://example.com/launch" \
  --tags "AI,Nemotron,GenAI"
```

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
example included in the repo.

## Project layout

```
src/nemo_marketing_bot/
  cli.py          # Typer entrypoint
  config.py       # pydantic-settings (.env)
  generator.py    # Nemotron call via OpenAI SDK
  ingest.py       # CLI + RSS -> Brief
  models.py       # Brief, GeneratedPost, PostBundle
  pipeline.py     # generate -> publish glue
  publishers.py   # LinkedIn / X / Instagram
  scheduler.py    # APScheduler runner
```

## Notes & limits

- **Instagram feed posts require a publicly hosted image URL.** For now, pass
  one in the post's `image_prompt` (when it starts with `http`). Extending the
  pipeline with an image generator (e.g. an NVIDIA NIM diffusion endpoint or
  an S3-hosted render) is a natural next step.
- **X free tier** allows ~17 posts/24h per user — don't wire up high-frequency
  RSS jobs without monitoring quota.
- **LinkedIn tokens expire** (60 days typical). Rotate or automate refresh.
- The generator uses `temperature=0.7`; tweak in `generator.py` if you want
  more deterministic output.

## License

MIT — use at your own risk, and comply with each platform's automation rules.
