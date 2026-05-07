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
# Use the repo-root Dockerfile. It must be run from the repository root because
# NemoClaw uses the Dockerfile directory as the Docker build context.
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

## Updating the network policy

`nemoclaw policy-add` reads presets from
`~/.nemoclaw/source/nemoclaw-blueprint/policies/presets/`, **not** from the
repo. After editing `nemoclaw/policies/marketing-bot.yaml` you must re-sync
and re-apply it:

```bash
# 1) Sync repo edits to the blueprint dir.
cp nemoclaw/policies/marketing-bot.yaml \
   ~/.nemoclaw/source/nemoclaw-blueprint/policies/presets/

# 2) Detach the old version (interactive: enter the preset's number, then Y).
nemoclaw marketingbot policy-remove marketing-bot

# 3) Re-apply the updated preset (interactive: number + Y).
nemoclaw marketingbot policy-add marketing-bot

# 4) Verify the rule landed.
nemoclaw marketingbot status | grep -A 30 "bluesky:"

# 5) Smoke-test from inside the sandbox.
nemoclaw marketingbot connect
# sandbox$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" https://bsky.social/xrpc/_health
# Expect: HTTP 200 (proxy lets the host through).
```

The proxy at `10.200.0.1:3128` is the in-sandbox shield. Its allowlist is the
merged `network_policies` shown in `nemoclaw <name> status`. Until the preset
is re-applied, a sandbox keeps the old policy version even if the YAML on disk
has changed.

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

## Remote desktop (VNC)

The sandbox includes Xvfb (virtual framebuffer) and tightvncserver, so you can
run GUI applications remotely. Firefox is pre-installed for browsing.

**Connect from the host:**

```bash
vncviewer <forwarded-host>:5900
```

When NemoClaw runs inside the local OpenShell Docker runtime, host `localhost`
may not be the same network namespace as the sandbox. Use a host-side port
forward or the Docker bridge IP printed by your forwarding command.

Then inside the VNC window, launch Firefox or other GUI tools:

```bash
# Inside the VNC desktop (right-click -> xterm, or from sandbox shell):
DISPLAY=:0 firefox-esr &
```

**Disable VNC** (default on, minimal overhead):

```bash
# Inside `nemoclaw marketingbot connect`, edit /sandbox/.env:
VNC_DISABLED=true
```

Then restart the sandbox to stop VNC services.

**Configuration:**

By default, VNC uses display `:0`, port `5900`, resolution `1280x1024`,
and 24-bit color.
Change in `/sandbox/.env`:

```bash
VNC_DISPLAY=0
VNC_GEOMETRY=1920x1080
VNC_DEPTH=32
VNC_DISABLED=false
```

The default VNC password is `nemo1234`; set `VNC_PASSWORD` before first boot to
change it. Logs are in `/sandbox/.vnc/vnc-server.log`.
