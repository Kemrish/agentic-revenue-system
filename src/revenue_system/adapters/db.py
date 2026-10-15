"""Small SQLite persistence adapter for the first durable workflow slice."""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from revenue_system.domain.models import Action, Deal, Score, Tier


class LeaseLostError(RuntimeError):
    """An expired owner must not acknowledge or overwrite another worker's item."""


class SQLiteStore:
    def __init__(self, url: str = "sqlite:///./revenue_system.db") -> None:
        self.path = url.removeprefix("sqlite:///")
        # Webhook frameworks may dispatch requests on worker threads. SQLite is
        # still serialized by the application worker; allow the connection to
        # be shared for this small local adapter.
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self._tx_depth = 0
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
            CREATE TABLE IF NOT EXISTS service_heartbeats (
                service TEXT PRIMARY KEY, seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS timers (
                id TEXT PRIMARY KEY, deal_id TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL,
                due_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'scheduled', created_at TEXT NOT NULL
            );
            """
        )
        self._add_column("approvals", "rejection_reason", "TEXT")
        for table in ("events", "outbox"):
            self._add_column(table, "attempts", "INTEGER NOT NULL DEFAULT 0")
            self._add_column(table, "last_error", "TEXT")
            self._add_column(table, "claimed_by", "TEXT")
            self._add_column(table, "lease_until", "TEXT")
            self._add_column(table, "next_attempt_at", "TEXT")
        self._add_column("outbox", "provider_id", "TEXT")
        self.connection.executescript("""
            CREATE INDEX IF NOT EXISTS events_queue ON events(status, next_attempt_at);
            CREATE INDEX IF NOT EXISTS outbox_queue ON outbox(status, next_attempt_at);
            CREATE INDEX IF NOT EXISTS timers_due ON timers(status, due_at);
        """)
        self.connection.commit()

    def _add_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _commit(self) -> None:
        if not self._tx_depth:
            self.connection.commit()

    @contextmanager
    def transaction(self):
        """Group store writes into one atomic unit; nested calls join the outer one."""
        self._tx_depth += 1
        try:
            yield self
        except BaseException:
            self._tx_depth -= 1
            if not self._tx_depth:
                self.connection.rollback()
            raise
        self._tx_depth -= 1
        if not self._tx_depth:
            self.connection.commit()

    def save_deal(self, deal: Deal) -> None:
        payload = asdict(deal)
        if deal.score:
            payload["score"]["tier"] = deal.score.tier.value
        payload["created_at"] = deal.created_at.isoformat()
        payload["updated_at"] = deal.updated_at.isoformat()
        self.connection.execute(
            "INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET company_name=excluded.company_name, contact_name=excluded.contact_name, segment=excluded.segment, stage=excluded.stage, payload=excluded.payload, updated_at=excluded.updated_at",
            (deal.id, deal.segment, deal.company_name, deal.contact_name, deal.stage, json.dumps(payload), deal.updated_at.isoformat()),
        )
        self._commit()

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
            self._commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def pending_events(self) -> list[sqlite3.Row]:
        return self._available("events", "processing")

    def mark_event_processed(self, event_id: str) -> None:
        self.connection.execute("UPDATE events SET status='processed', claimed_by=NULL, lease_until=NULL, next_attempt_at=NULL, last_error=NULL WHERE id=?", (event_id,))
        self._commit()

    def add_approval(self, approval_id: str, action: Action) -> None:
        self.connection.execute("INSERT OR IGNORE INTO approvals(id,deal_id,action_type,payload,status,created_at,rejection_reason) VALUES (?, ?, ?, ?, 'pending', datetime('now'), NULL)", (approval_id, action.deal_id, action.action_type.value, json.dumps(action.payload)))
        self._commit()

    def pending_approvals(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"))

    def get_approval(self, approval_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()

    def rejected_approvals_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM approvals WHERE status='rejected'").fetchone()[0])

    def pending_outbox(self) -> list[sqlite3.Row]:
        return self._available("outbox", "delivering")

    def mark_outbox_sent(self, outbox_id: str, provider_id: str | None = None) -> None:
        self.connection.execute("UPDATE outbox SET status='sent', provider_id=?, claimed_by=NULL, lease_until=NULL, next_attempt_at=NULL, last_error=NULL WHERE id=?", (provider_id, outbox_id))
        self._commit()

    def add_outbox_once(self, outbox_id: str, action: Action) -> bool:
        try:
            self.connection.execute("INSERT INTO outbox(id,action_type,deal_id,payload,status,created_at) VALUES (?, ?, ?, ?, 'pending', datetime('now'))", (outbox_id, action.action_type.value, action.deal_id, json.dumps(action.payload)))
            self._commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def audit(self, actor: str, action: str, detail: str, deal_id: str | None = None) -> None:
        self.connection.execute("INSERT INTO audit_log(deal_id,actor,action,detail,created_at) VALUES(?,?,?,?,datetime('now'))", (deal_id, actor, action, detail))
        self._commit()

    def save_lesson(self, lesson_id: str, segment: str, statement: str, evidence: list[str], status: str = "proposed") -> None:
        self.connection.execute("INSERT OR REPLACE INTO lessons VALUES (?, ?, ?, ?, ?, datetime('now'))", (lesson_id, segment, statement, json.dumps(evidence), status))
        self._commit()

    def active_lessons(self, segment: str) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM lessons WHERE status='active' AND segment IN (?, 'global')", (segment,)))

    def set_flag(self, name: str, enabled: bool) -> None:
        self.connection.execute("INSERT OR REPLACE INTO system_flags VALUES (?, ?)", (name, int(enabled)))
        self._commit()

    def flag_enabled(self, name: str) -> bool:
        row = self.connection.execute("SELECT enabled FROM system_flags WHERE name=?", (name,)).fetchone()
        return bool(row and row["enabled"])


    def record_event_failure(self, event_id: str, error: str, max_attempts: int, retry_base_seconds: float = 0) -> str:
        """Count a failed attempt; park the event as dead once retries are exhausted."""
        return self._record_failure("events", event_id, error, max_attempts, retry_base_seconds)

    def record_outbox_failure(self, outbox_id: str, error: str, max_attempts: int, retry_base_seconds: float = 0) -> str:
        return self._record_failure("outbox", outbox_id, error, max_attempts, retry_base_seconds)

    def _available(self, table: str, active: str) -> list[sqlite3.Row]:
        now = datetime.now(timezone.utc).isoformat()
        return list(self.connection.execute(
            f"SELECT * FROM {table} WHERE (status='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=?)) OR (status=? AND lease_until<=?) ORDER BY created_at, rowid",
            (now, active, now)))

    def claim(self, table: str, item_id: str, owner: str, lease_seconds: int, max_attempts: int) -> bool:
        """Atomic compare-and-set shared by separate dashboard/worker processes."""
        if table not in {"events", "outbox"}:
            raise ValueError("Unknown queue")
        active = "processing" if table == "events" else "delivering"
        terminal = "dead" if table == "events" else "failed"
        now = datetime.now(timezone.utc)
        with self.connection:
            self.connection.execute(
                f"UPDATE {table} SET status=?, claimed_by=NULL, lease_until=NULL, last_error=COALESCE(last_error,'Retry budget exhausted after interrupted work') WHERE id=? AND attempts>=? AND (status='pending' OR (status=? AND lease_until<=?))",
                (terminal, item_id, max_attempts, active, now.isoformat()))
            updated = self.connection.execute(
                f"UPDATE {table} SET status=?, claimed_by=?, lease_until=?, attempts=attempts+1 WHERE id=? AND attempts<? AND ((status='pending' AND (next_attempt_at IS NULL OR next_attempt_at<=?)) OR (status=? AND lease_until<=?))",
                (active, owner, (now + timedelta(seconds=lease_seconds)).isoformat(), item_id, max_attempts, now.isoformat(), active, now.isoformat()))
        return updated.rowcount == 1

    def release_claim(self, table: str, item_id: str, owner: str) -> None:
        if table not in {"events", "outbox"}:
            raise ValueError("Unknown queue")
        self.connection.execute(
            f"UPDATE {table} SET status='pending', claimed_by=NULL, lease_until=NULL, attempts=MAX(0,attempts-1) WHERE id=? AND claimed_by=?",
            (item_id, owner))
        self._commit()

    def assert_claim(self, table: str, item_id: str, owner: str) -> None:
        if table not in {"events", "outbox"}:
            raise ValueError("Unknown queue")
        active = "processing" if table == "events" else "delivering"
        updated = self.connection.execute(
            f"UPDATE {table} SET claimed_by=claimed_by WHERE id=? AND claimed_by=? AND status=? AND lease_until>?",
            (item_id, owner, active, datetime.now(timezone.utc).isoformat()))
        if updated.rowcount != 1:
            raise LeaseLostError("Queue lease expired or ownership changed")

    def _record_failure(self, table: str, item_id: str, error: str, max_attempts: int, retry_base_seconds: float) -> str:
        row = self.connection.execute(f"SELECT attempts FROM {table} WHERE id=?", (item_id,)).fetchone()
        attempts = row["attempts"]
        terminal = "dead" if table == "events" else "failed"
        status = terminal if attempts >= max_attempts else "pending"
        delay = min(3600, retry_base_seconds * 2 ** min(max(attempts - 1, 0), 16))
        next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.connection.execute(
            f"UPDATE {table} SET last_error=?, status=?, claimed_by=NULL, lease_until=NULL, next_attempt_at=? WHERE id=?",
            (error[:2000], status, next_attempt, item_id))
        self._commit()
        return status

    def retry_failed(self, queue: str, item_id: str, actor: str) -> bool:
        if queue not in {"events", "outbox"}:
            raise ValueError("Unknown queue")
        terminal = "dead" if queue == "events" else "failed"
        with self.transaction():
            updated = self.connection.execute(
                f"UPDATE {queue} SET status='pending', attempts=0, last_error=NULL, next_attempt_at=NULL, claimed_by=NULL, lease_until=NULL WHERE id=? AND status=?",
                (item_id, terminal))
            if updated.rowcount:
                self.audit(actor, "queue_retried", f"{queue}:{item_id}")
        return updated.rowcount == 1

    def schedule_timer(self, timer_id: str, deal_id: str, event_type: str, due_at: datetime, payload: dict[str, Any]) -> None:
        """One live timer per id: rescheduling replaces the previous one."""
        self.connection.execute(
            "INSERT OR REPLACE INTO timers(id,deal_id,event_type,payload,due_at,status,created_at) VALUES(?,?,?,?,?,'scheduled',datetime('now'))",
            (timer_id, deal_id, event_type, json.dumps(payload), due_at.astimezone(timezone.utc).isoformat()))
        self._commit()

    def cancel_timer(self, timer_id: str) -> None:
        self.connection.execute("UPDATE timers SET status='cancelled' WHERE id=? AND status='scheduled'", (timer_id,))
        self._commit()

    def due_timers(self, now: datetime) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM timers WHERE status='scheduled' AND due_at<=? ORDER BY due_at", (now.astimezone(timezone.utc).isoformat(),)))

    def fire_timer(self, row: sqlite3.Row) -> None:
        """Turn a due timer into a normal event, atomically."""
        with self.transaction():
            self.add_event_once(f"timer:{row['id']}:{row['due_at']}", row["event_type"], json.loads(row["payload"]))
            self.connection.execute("UPDATE timers SET status='fired' WHERE id=?", (row["id"],))

    def health(self) -> dict[str, int]:
        def one(query):
            return int(self.connection.execute(query).fetchone()[0])
        return {
            "events_pending": one("SELECT COUNT(*) FROM events WHERE status='pending'"),
            "events_dead": one("SELECT COUNT(*) FROM events WHERE status='dead'"),
            "events_processing": one("SELECT COUNT(*) FROM events WHERE status='processing'"),
            "outbox_pending": one("SELECT COUNT(*) FROM outbox WHERE status='pending'"),
            "outbox_failed": one("SELECT COUNT(*) FROM outbox WHERE status='failed'"),
            "outbox_delivering": one("SELECT COUNT(*) FROM outbox WHERE status='delivering'"),
            "approvals_pending": one("SELECT COUNT(*) FROM approvals WHERE status='pending'"),
            "timers_scheduled": one("SELECT COUNT(*) FROM timers WHERE status='scheduled'"),
        }

    def heartbeat(self, service: str = "worker") -> None:
        self.connection.execute("INSERT INTO service_heartbeats(service,seen_at) VALUES(?,?) ON CONFLICT(service) DO UPDATE SET seen_at=excluded.seen_at",
                                (service, datetime.now(timezone.utc).isoformat()))
        self._commit()
