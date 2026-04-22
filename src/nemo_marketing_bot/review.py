"""SQLite-backed review queue for draft posts.

Flow:
    generated → pending → (edited)* → approved → published
                       ↘ rejected

Every draft is stored with the original brief, the generated text/hashtags
for one platform, and a history of edits. Publishing happens from an explicit
CLI command that reads an `approved` row, calls the platform publisher, and
marks the row `published` (or `publish_failed`).

The store is intentionally small: no ORM, no migrations framework. One table
for drafts, one for the edit log. Upgrades = additive columns only.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator, Literal

from .models import Brief, GeneratedPost, Platform, PostBundle

logger = logging.getLogger(__name__)

Status = Literal["pending", "approved", "rejected", "published", "publish_failed"]

DEFAULT_DB_PATH = Path.home() / ".nemo-bot" / "state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id           TEXT PRIMARY KEY,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    status       TEXT NOT NULL,
    platform     TEXT NOT NULL,
    brief_json   TEXT NOT NULL,
    text         TEXT NOT NULL,
    hashtags     TEXT NOT NULL,  -- JSON array
    image_prompt TEXT,
    publish_id   TEXT,
    publish_error TEXT,
    notified_at  TEXT,           -- when a notifier (e.g. Telegram) pushed this draft
    notifier_ref TEXT            -- opaque ref (e.g. "chat_id:message_id")
);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_created ON drafts(created_at);
CREATE INDEX IF NOT EXISTS idx_drafts_notified ON drafts(notified_at);

CREATE TABLE IF NOT EXISTS edits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id   TEXT NOT NULL REFERENCES drafts(id),
    edited_at  TEXT NOT NULL,
    field      TEXT NOT NULL,       -- 'text' | 'hashtags' | 'image_prompt'
    old_value  TEXT,
    new_value  TEXT
);
"""


@dataclass
class DraftRecord:
    id: str
    created_at: datetime
    updated_at: datetime
    status: Status
    platform: Platform
    brief: Brief
    text: str
    hashtags: list[str]
    image_prompt: str | None
    publish_id: str | None = None
    publish_error: str | None = None

    def to_post(self) -> GeneratedPost:
        return GeneratedPost(
            platform=self.platform,
            text=self.text,
            hashtags=self.hashtags,
            image_prompt=self.image_prompt,
        )


class ReviewStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Additive migrations for older databases.
            for col, typ in (("notified_at", "TEXT"), ("notifier_ref", "TEXT")):
                try:
                    conn.execute(f"ALTER TABLE drafts ADD COLUMN {col} {typ}")
                except sqlite3.OperationalError:
                    pass  # column already exists

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            yield conn
        finally:
            conn.close()

    # --- writes ---------------------------------------------------------

    def enqueue_bundle(self, bundle: PostBundle) -> list[str]:
        """Insert every post in the bundle as a `pending` draft. Returns ids."""
        ids: list[str] = []
        now = _now_iso()
        brief_json = bundle.brief.model_dump_json()
        with self._conn() as conn:
            for post in bundle.posts:
                draft_id = uuid.uuid4().hex[:10]
                conn.execute(
                    """
                    INSERT INTO drafts
                        (id, created_at, updated_at, status, platform, brief_json,
                         text, hashtags, image_prompt)
                    VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                    """,
                    (
                        draft_id,
                        now,
                        now,
                        post.platform,
                        brief_json,
                        post.text,
                        json.dumps(post.hashtags),
                        post.image_prompt,
                    ),
                )
                ids.append(draft_id)
        logger.info("Enqueued %d drafts for review: %s", len(ids), ids)
        return ids

    def edit(
        self,
        draft_id: str,
        *,
        text: str | None = None,
        hashtags: list[str] | None = None,
        image_prompt: str | None = None,
    ) -> DraftRecord:
        """Mutate a `pending` draft. Rejected/approved/published drafts are immutable."""
        current = self.get(draft_id)
        if current.status not in ("pending",):
            raise ValueError(
                f"Draft {draft_id} is {current.status}; only pending drafts can be edited. "
                f"Use `review reopen` first."
            )
        changes: list[tuple[str, str | None, str | None]] = []
        new_text = current.text
        new_tags = current.hashtags
        new_img = current.image_prompt
        if text is not None and text != current.text:
            changes.append(("text", current.text, text))
            new_text = text
        if hashtags is not None and hashtags != current.hashtags:
            changes.append(("hashtags", json.dumps(current.hashtags), json.dumps(hashtags)))
            new_tags = hashtags
        if image_prompt is not None and image_prompt != current.image_prompt:
            changes.append(("image_prompt", current.image_prompt, image_prompt))
            new_img = image_prompt
        if not changes:
            return current
        now = _now_iso()
        with self._conn() as conn:
            conn.execute(
                "UPDATE drafts SET text=?, hashtags=?, image_prompt=?, updated_at=? WHERE id=?",
                (new_text, json.dumps(new_tags), new_img, now, draft_id),
            )
            for field, old, new in changes:
                conn.execute(
                    "INSERT INTO edits (draft_id, edited_at, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (draft_id, now, field, old, new),
                )
        return self.get(draft_id)

    def set_status(self, draft_id: str, status: Status, *, publish_id: str | None = None, publish_error: str | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE drafts SET status=?, updated_at=?, publish_id=?, publish_error=? WHERE id=?",
                (status, _now_iso(), publish_id, publish_error, draft_id),
            )

    def approve(self, draft_id: str) -> DraftRecord:
        d = self.get(draft_id)
        if d.status != "pending":
            raise ValueError(f"Draft {draft_id} is {d.status}; only pending drafts can be approved.")
        self.set_status(draft_id, "approved")
        return self.get(draft_id)

    def reject(self, draft_id: str) -> DraftRecord:
        d = self.get(draft_id)
        if d.status not in ("pending", "approved"):
            raise ValueError(f"Draft {draft_id} is already {d.status}.")
        self.set_status(draft_id, "rejected")
        return self.get(draft_id)

    def reopen(self, draft_id: str) -> DraftRecord:
        d = self.get(draft_id)
        if d.status not in ("approved", "rejected", "publish_failed"):
            raise ValueError(f"Draft {draft_id} is {d.status}; nothing to reopen.")
        self.set_status(draft_id, "pending")
        return self.get(draft_id)

    # --- reads ----------------------------------------------------------

    def get(self, draft_id: str) -> DraftRecord:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            raise KeyError(f"No draft with id {draft_id}")
        return _row_to_record(row)

    def list(self, status: Status | None = None, limit: int = 50) -> list[DraftRecord]:
        query = "SELECT * FROM drafts"
        params: tuple = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def edit_history(self, draft_id: str) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return list(
                conn.execute(
                    "SELECT edited_at, field, old_value, new_value FROM edits "
                    "WHERE draft_id=? ORDER BY id ASC",
                    (draft_id,),
                )
            )

    # --- notifier helpers ----------------------------------------------

    def list_unnotified_pending(self, limit: int = 20) -> list[DraftRecord]:
        """Pending drafts that have not yet been pushed to a notifier."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE status='pending' AND notified_at IS NULL "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def mark_notified(self, draft_id: str, ref: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE drafts SET notified_at=?, notifier_ref=? WHERE id=?",
                (_now_iso(), ref, draft_id),
            )

    def get_notifier_ref(self, draft_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT notifier_ref FROM drafts WHERE id=?", (draft_id,)
            ).fetchone()
        return row["notifier_ref"] if row else None


def _row_to_record(row: sqlite3.Row) -> DraftRecord:
    return DraftRecord(
        id=row["id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        status=row["status"],
        platform=row["platform"],
        brief=Brief.model_validate_json(row["brief_json"]),
        text=row["text"],
        hashtags=json.loads(row["hashtags"]),
        image_prompt=row["image_prompt"],
        publish_id=row["publish_id"],
        publish_error=row["publish_error"],
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
