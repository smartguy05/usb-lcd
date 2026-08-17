"""Persistent human action items shared by the panel, editor, and agents."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import config_home

PRIORITIES = ("urgent", "high", "normal", "low")
_PRIORITY_RANK = {value: index for index, value in enumerate(PRIORITIES)}


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_database_path() -> Path:
    return config_home() / "usb-lcd-dashboard/todos.sqlite3"


def _due(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("due_date must be YYYY-MM-DD or empty") from exc
    if parsed.isoformat() != text:
        raise ValueError("due_date must be YYYY-MM-DD or empty")
    return text


def _priority(value: Any) -> str:
    text = str(value or "normal").lower()
    if text not in PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
    return text


def _title(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("title is required")
    if len(text) > 240:
        raise ValueError("title must be 240 characters or fewer")
    return text


def _details(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > 4000:
        raise ValueError("details must be 4000 characters or fewer")
    return text


@dataclass(frozen=True, slots=True)
class TodoItem:
    id: str
    title: str
    details: str
    priority: str
    due_date: str | None
    status: str
    position: int
    created_at: str
    updated_at: str
    completed_at: str | None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TodoSnapshot:
    items: tuple[TodoItem, ...] = ()
    updated_at: str | None = None


def rank_items(items: Iterable[TodoItem], today: date) -> list[TodoItem]:
    """Urgent dates first, then priority; manual position breaks equal tiers."""

    def key(item: TodoItem):
        due = date.fromisoformat(item.due_date) if item.due_date else None
        days = (due - today).days if due else None
        if days is not None and days < 0:
            tier, detail = 0, days
        elif days == 0:
            tier, detail = 1, 0
        elif days is not None and days <= 7:
            tier, detail = 2, days
        else:
            tier, detail = 3 + _PRIORITY_RANK[item.priority], days or 999999
        return (tier, detail, item.position, item.created_at, item.id)

    return sorted(items, key=key)


class TodoStore:
    """Small SQLite repository; each operation owns its connection.

    Separate connections make the daemon thread, admin threads, and MCP child
    processes cooperate through SQLite's locking instead of shared Python state.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or default_database_path()
        self._cache_lock = threading.Lock()
        self._cached = TodoSnapshot()
        self._next_refresh = 0.0
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS todos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    due_date TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    position INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS todos_status_position ON todos(status, position)")
            db.execute("PRAGMA user_version = 1")

    @staticmethod
    def _item(row: sqlite3.Row) -> TodoItem:
        return TodoItem(**dict(row))

    def list(self, include_completed: bool = False) -> list[TodoItem]:
        sql = "SELECT * FROM todos"
        params: tuple[Any, ...] = ()
        if not include_completed:
            sql += " WHERE status = ?"
            params = ("open",)
        sql += " ORDER BY status DESC, position, created_at, id"
        with self._connect() as db:
            return [self._item(row) for row in db.execute(sql, params)]

    def get(self, item_id: str) -> TodoItem:
        with self._connect() as db:
            row = db.execute("SELECT * FROM todos WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return self._item(row)

    def create(self, title: Any, details: Any = "", priority: Any = "normal", due_date: Any = None) -> TodoItem:
        now = utc_now_text()
        item_id = str(uuid.uuid4())
        with self._connect() as db:
            position = db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM todos WHERE status = 'open'"
            ).fetchone()[0]
            db.execute(
                "INSERT INTO todos VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, NULL)",
                (item_id, _title(title), _details(details), _priority(priority), _due(due_date), position, now, now),
            )
        self.invalidate()
        return self.get(item_id)

    def update(self, item_id: str, **changes: Any) -> TodoItem:
        allowed = {"title", "details", "priority", "due_date"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown todo fields: {', '.join(sorted(unknown))}")
        self.get(item_id)
        values: dict[str, Any] = {}
        if "title" in changes:
            values["title"] = _title(changes["title"])
        if "details" in changes:
            values["details"] = _details(changes["details"])
        if "priority" in changes:
            values["priority"] = _priority(changes["priority"])
        if "due_date" in changes:
            values["due_date"] = _due(changes["due_date"])
        if not values:
            return self.get(item_id)
        values["updated_at"] = utc_now_text()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as db:
            db.execute(
                f"UPDATE todos SET {assignments} WHERE id = ?",  # fields are allowlisted above
                (*values.values(), item_id),
            )
        self.invalidate()
        return self.get(item_id)

    def set_completed(self, item_id: str, completed: bool = True) -> TodoItem:
        self.get(item_id)
        now = utc_now_text()
        status = "completed" if completed else "open"
        completed_at = now if completed else None
        with self._connect() as db:
            if not completed:
                position = db.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM todos WHERE status = 'open'"
                ).fetchone()[0]
                db.execute(
                    "UPDATE todos SET status=?, completed_at=?, updated_at=?, position=? WHERE id=?",
                    (status, completed_at, now, position, item_id),
                )
            else:
                db.execute(
                    "UPDATE todos SET status=?, completed_at=?, updated_at=? WHERE id=?",
                    (status, completed_at, now, item_id),
                )
        self.invalidate()
        return self.get(item_id)

    def reorder(self, ordered_ids: Iterable[str]) -> list[TodoItem]:
        ids = [str(value) for value in ordered_ids]
        open_ids = [item.id for item in self.list()]
        if len(ids) != len(set(ids)) or set(ids) != set(open_ids):
            raise ValueError("ordered_ids must contain every open todo exactly once")
        now = utc_now_text()
        with self._connect() as db:
            db.executemany(
                "UPDATE todos SET position=?, updated_at=? WHERE id=?",
                ((position, now, item_id) for position, item_id in enumerate(ids)),
            )
        self.invalidate()
        return self.list()

    def delete(self, item_id: str) -> None:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM todos WHERE id = ?", (item_id,))
            if cursor.rowcount == 0:
                raise KeyError(item_id)
        self.invalidate()

    def invalidate(self) -> None:
        with self._cache_lock:
            self._next_refresh = 0.0

    def snapshot(self) -> TodoSnapshot:
        now = time.monotonic()
        with self._cache_lock:
            if now < self._next_refresh:
                return self._cached
            items = tuple(rank_items(self.list(), date.today()))
            updated = max((item.updated_at for item in items), default=None)
            self._cached = TodoSnapshot(items, updated)
            self._next_refresh = now + 0.5
            return self._cached
