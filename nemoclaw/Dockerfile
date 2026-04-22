# Sandbox image for the marketing-bot NemoClaw deployment.
# Build implicitly via: nemoclaw onboard --from nemoclaw/Dockerfile
#
# Extends the default NemoClaw sandbox base by installing the
# nemo-marketing-bot package and pre-seeding the workspace files.

ARG NEMOCLAW_BASE=ghcr.io/nvidia/nemoclaw-sandbox:latest
FROM ${NEMOCLAW_BASE}

USER root

# System deps for feedparser + tweepy + pillow (in case image utils get added)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install the marketing bot package itself.
# Copy source from the repo so rebuilds pick up local changes.
COPY pyproject.toml /opt/nemo-marketing-bot/pyproject.toml
COPY src/ /opt/nemo-marketing-bot/src/
RUN pip install --no-cache-dir /opt/nemo-marketing-bot

# Seed workspace files (SOUL, IDENTITY, AGENTS, USER, MEMORY).
# NemoClaw mounts /sandbox/.openclaw/workspace as a PVC; these files are
# copied in only if the PVC is empty (first boot).
COPY nemoclaw/workspace/ /opt/nemoclaw-workspace-seed/

# Default schedule config (user can edit inside the sandbox).
COPY schedule.yaml /opt/nemo-marketing-bot/schedule.yaml

# Install the skill so the in-sandbox agent auto-discovers it.
COPY nemoclaw/skills/marketing-bot/ /sandbox/.agents/skills/marketing-bot/

# Supervisor entry: start the scheduler alongside the normal agent loop.
COPY nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh /etc/nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh
RUN chmod +x /etc/nemoclaw/entrypoint.d/10-nemo-bot-scheduler.sh

USER sandbox
