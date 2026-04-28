# NemoClaw deployment

Run `nemo-marketing-bot` as an always-on NemoClaw sandbox. The sandbox hosts an
LLM agent ("Nemo", a marketing operator) that drives the bot's CLI on your
behalf and runs the scheduler in the background.

## What's in this folder

| Path | Purpose |
|---|---|
| `Dockerfile` | Custom sandbox image: base NemoClaw + `nemo-marketing-bot` installed + workspace seed. |
| `skills/marketing-bot/SKILL.md` | Teaches the in-sandbox agent how to use `nemo-bot`. |
| `workspace/` | Persona files (`SOUL.md`, `IDENTITY.md`, `AGENTS.md`, `USER.md`, `MEMORY.md`) seeded on first boot. |
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
nemoclaw onboard --from nemoclaw/Dockerfile \
  --yes-i-accept-third-party-software
# Follow the prompts — name the sandbox e.g. "marketingbot".

# 3) Apply the network policy.
nemoclaw marketingbot policy-add marketing-bot

# 4) Push your credentials (LinkedIn/X/IG/NVIDIA tokens) into the sandbox.
nemoclaw marketingbot connect
# Inside the sandbox:
#   $ nano /sandbox/.env
# Paste the same keys you have in your local .env, keep DRY_RUN=true for now.

# 5) Install the skill (already baked into the image, but this refreshes it
#    without a rebuild).
nemoclaw marketingbot skill install nemoclaw/skills/marketing-bot
```

## Day-to-day

```bash
# Chat with the marketing operator.
nemoclaw marketingbot connect
# Then: "Draft a LinkedIn post about the Nemotron 2 launch"
# Or: "Plan creator outreach for NemoClaw on TikTok, YouTube and Keymailer"

# Tail the scheduler log (background RSS + cron jobs).
nemoclaw marketingbot logs --follow

# Health check.
nemoclaw marketingbot status

# From the repo or sandbox shell, build the creator plan / CSV.
nemo-bot creators plan --game "NemoClaw" --genre "PC indie/AA action game"
nemo-bot creators export --output outreach/nemoclaw-creators.csv \
  --game "NemoClaw" --genre "PC indie/AA action game"

# Snapshot before risky changes (e.g. before flipping DRY_RUN=false).
nemoclaw marketingbot snapshot create
```

## Going live (disable dry run)

1. `nemoclaw marketingbot snapshot create`
2. `nemoclaw marketingbot connect`
3. Edit `/sandbox/.env`: set `DRY_RUN=false`.
4. Exit the shell. Inside the agent chat, ask Nemo to draft + publish a smoke
   test. Nemo will confirm before publishing.

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
- **Custom brand voice**: edit `workspace/SOUL.md` (either here before a
  rebuild, or inside the running sandbox for immediate effect).
- **More skills**: drop a new folder under `skills/` and run
  `nemoclaw marketingbot skill install nemoclaw/skills/<your-skill>`.
