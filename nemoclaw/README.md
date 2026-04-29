# NemoClaw deployment

Run `nemo-marketing-bot` as an always-on NemoClaw sandbox. The sandbox hosts an
LLM agent ("Nemo", a marketing operator) that drives the bot's CLI on your
behalf and runs the scheduler in the background.

## What's in this folder

| Path | Purpose |
|---|---|
| `../Dockerfile` | Custom sandbox image: base NemoClaw + `nemo-marketing-bot` installed + workspace seed. Use the repo-root Dockerfile so the build context includes `pyproject.toml`, `src/`, `schedule.yaml`, and this `nemoclaw/` folder. |
| `skills/marketing-bot/SKILL.md` | Teaches the in-sandbox agent how to use `nemo-bot`. |
| `workspace/` | Persona files (`SOUL.md`, `IDENTITY.md`, `AGENTS.md`, `USER.md`, `MEMORY.md`) seeded on first boot. |
| `../marketing-system-prompt.md` | Editable marketing strategy and brand voice prompt. Seeded to `/sandbox/marketing-system-prompt.md` on boot. |
| `policies/marketing-bot.yaml` | Network policy preset: NVIDIA inference + LinkedIn/X/Instagram APIs + common RSS hosts. |
| `entrypoint.d/10-nemo-bot-scheduler.sh` | Boot hook that starts the APScheduler inside the sandbox. |

## One-time setup

```bash
# From the repo root
cd ~/Coding/nemo-marketing-bot

# 1) Install the network policy preset globally so sandboxes can apply it.
cp nemoclaw/policies/marketing-bot.yaml \
   ~/.nemoclaw/source/nemoclaw-blueprint/policies/presets/

# 2) Onboard a sandbox using this custom image.
# Use the repo-root Dockerfile. `--from nemoclaw/Dockerfile` does not include
# pyproject.toml or src/ in NemoClaw's build context.
nemoclaw onboard --from Dockerfile \
  --yes-i-accept-third-party-software
# Follow the prompts — name the sandbox e.g. "marketingbot".

# 3) Apply the network policy.
nemoclaw marketingbot policy-add marketing-bot

# 4) Push your credentials (LinkedIn/X/IG/NVIDIA tokens) into the sandbox.
nemoclaw marketingbot connect
# Inside the sandbox:
#   $ nano /sandbox/.env
# Paste the same keys you have in your local .env, keep DRY_RUN=true for now.
# Keep ALLOW_SCHEDULED_AUTOPUBLISH=false until scheduled live publishing is intentional.

# 5) Install the skill (already baked into the image, but this refreshes it
#    without a rebuild).
nemoclaw marketingbot skill install nemoclaw/skills/marketing-bot
```

## Day-to-day

```bash
# Chat with the marketing operator.
nemoclaw marketingbot connect
# Then: "Draft a LinkedIn post about the Nemotron 2 launch"
# Or: "Plan creator outreach for Kalma on TikTok, YouTube and Keymailer"

# Tail the scheduler log (background RSS + cron jobs).
nemoclaw marketingbot logs --follow

# Health check.
nemoclaw marketingbot status

# From the repo or sandbox shell, build the creator plan / CSV.
nemo-bot creators plan --game "Kalma" --genre "PC indie/AA action game"
nemo-bot creators export --output outreach/kalma-creators.csv \
  --game "Kalma" --genre "PC indie/AA action game"

# Inspect the editable strategy prompt that shapes all generated content.
nemo-bot strategy path
nemo-bot strategy show
nemo-bot strategy show --compiled

# Snapshot before risky changes (e.g. before flipping DRY_RUN=false).
nemoclaw marketingbot snapshot create
```

## Going live (disable dry run)

1. `nemoclaw marketingbot snapshot create`
2. `nemoclaw marketingbot connect`
3. Edit `/sandbox/.env`: set `DRY_RUN=false`.
4. Keep `ALLOW_SCHEDULED_AUTOPUBLISH=false` unless cron/RSS jobs should publish without per-post approval.
5. Exit the shell. Inside the agent chat, ask Nemo to draft + publish a smoke
   test. Nemo will confirm before publishing.

## Updating the marketing strategy

The live prompt file is `/sandbox/marketing-system-prompt.md`. Edit it whenever
the positioning, campaign priorities, target creators, tone, CTA, or content
pillars change. The generator reloads it on every run, so no rebuild is needed
for strategy updates.

Example agent request inside `nemoclaw marketingbot connect`:

```text
Open /sandbox/marketing-system-prompt.md. Update the voice to be more Finnish,
creator-first and wishlist-focused. Keep the non-hype rule. Then run a dry-run
TikTok + YouTube + Steam draft for the next demo beat.
```

Keep hard runtime rules in code: JSON shape, platform list, untrusted RSS
handling, and publish confirmation are not controlled by the editable prompt.

## Scheduled publishing guard

Scheduled jobs queue drafts by default. A job can publish live only when the job
uses a boolean YAML value `auto_publish: true` and `/sandbox/.env` has
`ALLOW_SCHEDULED_AUTOPUBLISH=true`. Quoted values like `"false"` are rejected to
avoid Python truthiness mistakes.

Telegram approvals are chat-gated by `TELEGRAM_APPROVER_CHAT_IDS`. For group
approval chats, also set `TELEGRAM_APPROVER_USER_IDS` to the exact users allowed
to approve or publish.

## Updating the bot code

When you change Python source in `src/`:

```bash
nemoclaw marketingbot rebuild --yes
```

Rebuild re-runs the Dockerfile's `pip install`, so the new version is in. The
PVC (including `schedule.yaml`, `/sandbox/.env`, and `.openclaw/workspace/`)
survives.

## Extending

- **More RSS hosts**: add them under `rss-feeds` in
  `policies/marketing-bot.yaml`, reinstall the preset, and re-apply.
- **Custom brand voice**: edit `/sandbox/marketing-system-prompt.md` in the
  running sandbox for immediate effect. Edit `../marketing-system-prompt.md`
  before a rebuild if you want to change the baked-in default.
- **More skills**: drop a new folder under `skills/` and run
  `nemoclaw marketingbot skill install nemoclaw/skills/<your-skill>`.
