"""APScheduler-based scheduler for recurring campaigns and RSS polling."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import settings
from .ingest import brief_from_cli, briefs_from_rss
from .models import Platform
from .pipeline import ALL_PLATFORMS, run_once

logger = logging.getLogger(__name__)

STATE_FILE = Path(".schedule.json")


def _job_from_rss(feed_url: str, platforms: list[Platform], limit: int, auto_publish: bool) -> None:
    since = _load_last_run(feed_url)
    now = datetime.now(UTC)
    briefs = briefs_from_rss(feed_url, limit=limit, since=since)
    if not briefs:
        logger.info("RSS job: no new entries for %s", feed_url)
        _save_last_run(feed_url, now)
        return
    for brief in briefs:
        logger.info("RSS job: processing '%s' (auto_publish=%s)", brief.topic, auto_publish)
        run_once(brief, platforms, auto_publish=auto_publish)
    _save_last_run(feed_url, now)


def _job_from_topic(topic: str, details: str, platforms: list[Platform], auto_publish: bool) -> None:
    brief = brief_from_cli(topic=topic, details=details)
    run_once(brief, platforms, auto_publish=auto_publish)


def _load_last_run(key: str) -> datetime | None:
    import json

    if not STATE_FILE.exists():
        return None
    data = json.loads(STATE_FILE.read_text())
    ts = data.get(key)
    return datetime.fromisoformat(ts) if ts else None


def _save_last_run(key: str, when: datetime) -> None:
    import json

    data = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    data[key] = when.isoformat()
    STATE_FILE.write_text(json.dumps(data, indent=2))


def run_scheduler(config_path: Path) -> None:
    """Run the scheduler until interrupted.

    Example schedule.yaml:
        jobs:
          - name: weekly-product-update
            cron: "0 9 * * MON"
            type: topic
            topic: "New Nemotron features"
            details: "Highlight our integration wins."
            platforms: [linkedin, x]
          - name: blog-rss
            cron: "*/30 * * * *"
            type: rss
            feed: "https://example.com/feed.xml"
            limit: 2
            platforms: [linkedin, x, instagram]
    """
    config = yaml.safe_load(config_path.read_text())
    scheduler = BlockingScheduler(timezone=settings.timezone)

    for job in config.get("jobs", []):
        _register_job(scheduler, job)

    logger.info("Scheduler starting (%d jobs, timezone=%s)", len(scheduler.get_jobs()), settings.timezone)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


def _register_job(scheduler: BlockingScheduler, job: dict[str, Any]) -> None:
    name = job["name"]
    trigger = CronTrigger.from_crontab(job["cron"], timezone=settings.timezone)
    platforms: list[Platform] = job.get("platforms") or ALL_PLATFORMS
    job_type = job["type"]
    auto_publish = bool(job.get("auto_publish", False))

    if job_type == "rss":
        scheduler.add_job(
            _job_from_rss,
            trigger=trigger,
            args=[job["feed"], platforms, int(job.get("limit", 2)), auto_publish],
            id=name,
            name=name,
            max_instances=1,
            coalesce=True,
        )
    elif job_type == "topic":
        scheduler.add_job(
            _job_from_topic,
            trigger=trigger,
            args=[job["topic"], job.get("details", ""), platforms, auto_publish],
            id=name,
            name=name,
            max_instances=1,
            coalesce=True,
        )
    else:
        raise ValueError(f"Unknown job type: {job_type}")

    logger.info(
        "Registered job '%s' (%s) cron=%s platforms=%s auto_publish=%s",
        name, job_type, job["cron"], platforms, auto_publish,
    )
