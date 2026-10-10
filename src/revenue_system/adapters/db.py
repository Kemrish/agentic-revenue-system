"""Small SQLite persistence adapter for the first durable workflow slice."""

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Any

from revenue_system.domain.models import Action, Deal, Score, Tier


class SQLiteStore:
    def __init__(self, url: str = "sqlite:///./revenue_system.db") -> None:
        self.path = url.removeprefix("sqlite:///")
        # Webhook frameworks may dispatch requests on worker threads. SQLite is
        # still serialized by the application worker; allow the connection to
        # be shared for this small local adapter.
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS deals (
                id TEXT PRIMARY KEY, segment TEXT NOT NULL, company_name TEXT NOT NULL,
                contact_name TEXT NOT NULL, stage TEXT NOT NULL, payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, event_type TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, action_type TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, action_type TEXT NOT NULL, deal_id TEXT NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, deal_id TEXT, actor TEXT NOT NULL,
                action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY, segment TEXT NOT NULL, statement TEXT NOT NULL,
                evidence TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'proposed', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS system_flags (
                name TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        self.connection.commit()

    def save_deal(self, deal: Deal) -> None:
        payload = asdict(deal)
        if deal.score:
            payload["score"]["tier"] = deal.score.tier.value
        payload["created_at"] = deal.created_at.isoformat()
        payload["updated_at"] = deal.updated_at.isoformat()
        self.connection.execute(
            "INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET stage=excluded.stage, payload=excluded.payload, updated_at=excluded.updated_at",
            (deal.id, deal.segment, deal.company_name, deal.contact_name, deal.stage, json.dumps(payload), deal.updated_at.isoformat()),
        )
        self.connection.commit()

    def get_deal(self, deal_id: str) -> Deal | None:
        row = self.connection.execute("SELECT payload FROM deals WHERE id = ?", (deal_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["payload"])
        score_data = data.get("score")
        score = Score(**{**score_data, "tier": Tier(score_data["tier"])}) if score_data else None
        return Deal(
            id=data["id"], segment=data["segment"], company_name=data["company_name"],
            contact_name=data["contact_name"], stage=data["stage"], fields=data["fields"],
            score=score, flags=data["flags"],
            created_at=datetime.fromisoformat(data["created_at"]), updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    def add_event_once(self, event_id: str, event_type: str, payload: dict[str, Any]) -> bool:
        try:
            self.connection.execute("INSERT INTO events(id,event_type,payload,created_at) VALUES(?,?,?,datetime('now'))", (event_id, event_type, json.dumps(payload)))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def pending_events(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM events WHERE status='pending' ORDER BY created_at"))

    def mark_event_processed(self, event_id: str) -> None:
        self.connection.execute("UPDATE events SET status='processed' WHERE id=?", (event_id,))
        self.connection.commit()

    def add_approval(self, approval_id: str, action: Action) -> None:
        self.connection.execute("INSERT OR IGNORE INTO approvals VALUES (?, ?, ?, ?, 'pending', datetime('now'))", (approval_id, action.deal_id, action.action_type.value, json.dumps(action.payload)))
        self.connection.commit()

    def add_outbox_once(self, outbox_id: str, action: Action) -> bool:
        try:
            self.connection.execute("INSERT INTO outbox VALUES (?, ?, ?, ?, 'pending', datetime('now'))", (outbox_id, action.action_type.value, action.deal_id, json.dumps(action.payload)))
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def audit(self, actor: str, action: str, detail: str, deal_id: str | None = None) -> None:
        self.connection.execute("INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(?,?,?,?,datetime('now'))", (deal_id, actor, action, detail))
        self.connection.commit()

    def save_lesson(self, lesson_id: str, segment: str, statement: str, evidence: list[str], status: str = "proposed") -> None:
        self.connection.execute("INSERT OR REPLACE INTO lessons VALUES (?, ?, ?, ?, ?, datetime('now'))", (lesson_id, segment, statement, json.dumps(evidence), status))
        self.connection.commit()

    def active_lessons(self, segment: str) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM lessons WHERE status='active' AND segment IN (?, 'global')", (segment,)))

    def set_flag(self, name: str, enabled: bool) -> None:
        self.connection.execute("INSERT OR REPLACE INTO system_flags VALUES (?, ?)", (name, int(enabled)))
        self.connection.commit()

    def flag_enabled(self, name: str) -> bool:
        row = self.connection.execute("SELECT enabled FROM system_flags WHERE name=?", (name,)).fetchone()
        return bool(row and row["enabled"])

