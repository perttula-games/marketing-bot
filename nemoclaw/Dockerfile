# Sandbox image for direct Docker builds with the repository root as context.
#
# For NemoClaw onboarding, use the repo-root Dockerfile instead:
#   nemoclaw onboard --from Dockerfile --yes-i-accept-third-party-software
#
# NemoClaw uses the Dockerfile's directory as the build context. If this nested
# file is passed directly to `nemoclaw --from`, pyproject.toml and src/ are not
# included and COPY will fail.
#
# Extends the default NemoClaw sandbox base by installing the
# nemo-marketing-bot package and pre-seeding the workspace files.

ARG NEMOCLAW_BASE=ghcr.io/nvidia/nemoclaw/sandbox-base@sha256:3f5b8a3d6487326e30ca3bb1fc72d7ff91c6419035ac55e3b6cbc2056033534c
ARG PIP_VERSION=24.2
FROM ${NEMOCLAW_BASE}

# Re-declare ARG after FROM so it is visible to subsequent RUN steps.
ARG PIP_VERSION

ENV MARKETING_SYSTEM_PROMPT_FILE=/sandbox/marketing-system-prompt.md

USER root

# System deps for feedparser + tweepy + pillow (in case image utils get added)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
     git ca-certificates python3-venv \
 && rm -rf /var/lib/apt/lists/*

# Install the marketing bot package itself.
# Copy source from the repo so rebuilds pick up local changes.
COPY pyproject.toml /usr/local/lib/nemo-marketing-bot/pyproject.toml
COPY src/ /usr/local/lib/nemo-marketing-bot/src/
RUN python3 -m venv /usr/local/lib/nemo-marketing-bot/.venv \
 && /usr/local/lib/nemo-marketing-bot/.venv/bin/pip install --no-cache-dir --upgrade "pip==${PIP_VERSION}" \
 && /usr/local/lib/nemo-marketing-bot/.venv/bin/pip install --no-cache-dir /usr/local/lib/nemo-marketing-bot \
 && ln -sf /usr/local/lib/nemo-marketing-bot/.venv/bin/nemo-bot /usr/local/bin/nemo-bot

# Seed workspace files (SOUL, IDENTITY, AGENTS, USER, MEMORY).
# NemoClaw mounts /sandbox/.openclaw/workspace as a PVC; these files are
# copied in only if the PVC is empty (first boot).
COPY nemoclaw/workspace/ /opt/nemoclaw-workspace-seed/

# Default schedule config (user can edit inside the sandbox).
COPY schedule.yaml /usr/local/lib/nemo-marketing-bot/schedule.yaml

# Default marketing system prompt (seeded into /sandbox on boot for live edits).
COPY marketing-system-prompt.md /usr/local/lib/nemo-marketing-bot/marketing-system-prompt.md

# Install the skill so the in-sandbox agent auto-discovers it.
COPY nemoclaw/skills/marketing-bot/ /sandbox/.agents/skills/marketing-bot/

# Supervisor entry: start the scheduler alongside the normal agent loop.
COPY nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh /etc/nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh
RUN chmod +x /etc/nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh

USER sandbox
