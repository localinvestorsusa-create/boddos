"""Calendar events, alarms, and a to-do list — one local SQLite file, no
cloud calendar account. Plain synchronous sqlite3 (stdlib): each call is a
single small local-disk query, not worth the ceremony of an async driver.
Timers are deliberately not modeled here — a countdown has nothing worth
persisting past a page reload, so it stays client-side (frontend/src).
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from ..config import PlannerCfg


@dataclass
class Event:
    id: str
    title: str
    start_time: str
    end_time: str
    category: str = "general"
    description: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Alarm:
    id: str
    time: str
    label: str = ""
    enabled: bool = True

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Task:
    id: str
    text: str
    completed: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class PlannerStore:
    def __init__(self, cfg: PlannerCfg):
        self.cfg = cfg
        self._db_path = Path(cfg.db_path).expanduser()
        if cfg.enabled:
            self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    description TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    id TEXT PRIMARY KEY,
                    time TEXT NOT NULL,
                    label TEXT DEFAULT '',
                    enabled INTEGER DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    completed INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    # ------------------------------- events -------------------------------

    def add_event(self, title: str, start_time: str, end_time: str,
                  category: str = "general", description: str = "") -> Event:
        event = Event(id=str(uuid.uuid4()), title=title, start_time=start_time,
                      end_time=end_time, category=category, description=description)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (id, title, start_time, end_time, category, description) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event.id, event.title, event.start_time, event.end_time, event.category, event.description),
            )
        return event

    def list_events(self, date: str | None = None) -> list[Event]:
        """`date` is 'YYYY-MM-DD'; omit it to list every upcoming event."""
        with self._conn() as conn:
            if date:
                rows = conn.execute(
                    "SELECT * FROM events WHERE start_time BETWEEN ? AND ? ORDER BY start_time ASC",
                    (f"{date} 00:00:00", f"{date} 23:59:59"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM events ORDER BY start_time ASC").fetchall()
        return [Event(**dict(r)) for r in rows]

    def delete_event(self, event_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        return cur.rowcount > 0

    # ------------------------------- alarms -------------------------------

    def add_alarm(self, time: str, label: str = "") -> Alarm:
        alarm = Alarm(id=str(uuid.uuid4()), time=time, label=label)
        with self._conn() as conn:
            conn.execute("INSERT INTO alarms (id, time, label) VALUES (?, ?, ?)",
                        (alarm.id, alarm.time, alarm.label))
        return alarm

    def list_alarms(self) -> list[Alarm]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM alarms ORDER BY time ASC").fetchall()
        return [Alarm(id=r["id"], time=r["time"], label=r["label"], enabled=bool(r["enabled"])) for r in rows]

    def delete_alarm(self, alarm_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
        return cur.rowcount > 0

    # ------------------------------- tasks -------------------------------

    def add_task(self, text: str) -> Task:
        task = Task(id=str(uuid.uuid4()), text=text)
        with self._conn() as conn:
            conn.execute("INSERT INTO tasks (id, text, completed) VALUES (?, ?, 0)", (task.id, task.text))
        return task

    def list_tasks(self) -> list[Task]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, text, completed FROM tasks ORDER BY created_at ASC").fetchall()
        return [Task(id=r["id"], text=r["text"], completed=bool(r["completed"])) for r in rows]

    def toggle_task(self, task_id: str, completed: bool) -> bool:
        with self._conn() as conn:
            cur = conn.execute("UPDATE tasks SET completed = ? WHERE id = ?", (int(completed), task_id))
        return cur.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cur.rowcount > 0
