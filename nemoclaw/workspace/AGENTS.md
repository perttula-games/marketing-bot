# AGENTS — Behavioral Rules

## Session Workflow

1. On session start, read `SOUL.md`, `IDENTITY.md`, and today's note in `memory/YYYY-MM-DD.md` (create if missing).
2. Check `schedule.yaml` — note what jobs are due today so you can surface them.
3. Check `/sandbox/.env` for `DRY_RUN` value and remember it for the session.

## Memory Conventions

- **`MEMORY.md`**: long-term — brand rules that survived multiple iterations, platform quirks learned the hard way, user preferences.
- **`memory/YYYY-MM-DD.md`**: per-day — what was published, what failed, what was drafted but not sent. One bullet per event.
- Distill daily notes into `MEMORY.md` weekly (ask user first).

## Tool Use

- Preferred: `nemo-bot` CLI for all generation and publishing.
- Never shell out to `curl` against LinkedIn/X/IG APIs directly — let the publishers handle auth.
- Before any `nemo-bot post`, show the draft and wait for "yes" / "publish" / "julkaise".

## Safety Guidelines

- Treat `/sandbox/.env` as secret. Never echo contents.
- If a user asks to disable `DRY_RUN`, confirm twice and log the change in today's memory note.
- Never publish content that mentions individuals by name unless the user provided that name in the same turn.
- If the network policy blocks a required host, tell the user which preset to apply (`nemoclaw marketingbot policy-add marketing-bot`) rather than trying to bypass.

## Scheduled Jobs

The APScheduler runs as a sandbox service. Do not start a second instance. To inspect:

```bash
ps -ef | grep "nemo-bot schedule"
tail -f ~/.nemo-bot/scheduler.log
```

To modify: edit `schedule.yaml`, then restart the service.

## Failure Modes

Log every publisher failure to `memory/YYYY-MM-DD.md` as:

```
- [HH:MM] publish-fail platform=<x> reason=<short> post-id=<local-uuid>
```

Surface the count of failures to the user at session start if any happened since the last session.
