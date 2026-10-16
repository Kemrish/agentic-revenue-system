"""Readiness checks, non-destructive provisioning, and SQLite recovery tools."""

import json
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from .adapters.db import SQLiteStore
from .segments.registry import PackRegistry
from .settings import Settings


def database_path(url: str) -> Path:
    if not url.startswith("sqlite:///") or url == "sqlite:///:memory:":
        raise ValueError("A persistent local SQLite DATABASE_URL is required")
    return Path(url.removeprefix("sqlite:///")).resolve()


def configuration_errors(s: Settings) -> list[str]:
    errors = []
    if s.app_env.lower() != "production":
        errors.append("APP_ENV must be production")
    if len(s.dashboard_password) < 24:
        errors.append("DASHBOARD_PASSWORD must contain at least 24 characters")
    if len(s.webhook_secret) < 32:
        errors.append("WEBHOOK_SECRET must contain at least 32 characters")
    if s.runtime_mode != "live" or s.claude_mode != "live":
        errors.append("Live runner modes are required")
    if s.llm_provider == "openrouter":
        if not s.openrouter_api_key:
            errors.append("OPENROUTER_API_KEY is required")
    elif s.llm_provider in {"claude", "anthropic"}:
        if not s.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required")
    else:
        errors.append("Select a supported live LLM_PROVIDER")
    public = urlsplit(s.public_webhook_url)
    if public.scheme != "https" or not public.hostname or public.query or public.fragment or public.username:
        errors.append("PUBLIC_WEBHOOK_URL must be the canonical HTTPS receiver base URL")
    for mode, fields in (
        (s.hubspot_mode, [("HUBSPOT_ACCESS_TOKEN", s.hubspot_access_token), ("HUBSPOT_CLIENT_SECRET", s.hubspot_client_secret)]),
        (s.fireflies_mode, [("FIREFLIES_API_KEY", s.fireflies_api_key), ("FIREFLIES_WEBHOOK_SECRET", s.fireflies_webhook_secret)]),
        (s.mail_mode, [("MAIL_API_KEY", s.mail_api_key), ("MAIL_FROM_ADDRESS", s.mail_from_address),
                       ("RESEND_WEBHOOK_SECRET", s.resend_webhook_secret), ("MAIL_ALLOWED_RECIPIENTS", s.mail_allowed_recipients),
                       ("MAIL_REPLY_DOMAIN", s.mail_reply_domain), ("MAIL_THREAD_SECRET", s.mail_thread_secret)]),
        (s.esign_mode, [("ESIGN_API_KEY", s.esign_api_key), ("ESIGN_ALLOWED_RECIPIENTS", s.esign_allowed_recipients)]),
    ):
        if mode == "live":
            errors.extend(f"{name} is required for its enabled live integration" for name, value in fields if not value)
    if s.esign_mode == "live" and s.esign_test_mode:
        errors.append("Live production e-sign requires ESIGN_TEST_MODE=false and verified plan access; otherwise disable ESIGN_MODE")
    if s.mail_reply_domain and ("/" in s.mail_reply_domain or "@" in s.mail_reply_domain or any(c.isspace() for c in s.mail_reply_domain)):
        errors.append("MAIL_REPLY_DOMAIN must be a receiving domain, not an address or URL")
    if s.crm_sync_enabled and s.hubspot_mode != "live":
        errors.append("CRM_SYNC_ENABLED requires live HubSpot")
    return errors


def readiness(s: Settings) -> dict:
    """No migrations, database creation, provider calls, or secret values."""
    checks = [{"name": "configuration", "status": "fail" if configuration_errors(s) else "pass",
               "details": configuration_errors(s)}]
    try:
        checks.append({"name": "segment_packs", "status": "pass", "details": [p.segment for p in PackRegistry(s.packs_root).all()]})
    except Exception:
        checks.append({"name": "segment_packs", "status": "fail", "details": ["Missing or invalid packs"]})
    try:
        path = database_path(s.database_url)
        if not path.exists():
            raise ValueError("Database has not been initialized")
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            integrity = db.execute("PRAGMA quick_check").fetchone()[0]
            samples = db.execute("SELECT COUNT(*) FROM deals WHERE id IN ('lead-brand-001','lead-publisher-001') OR id LIKE 'lead-approval-%' OR id LIKE 'lead-deny-%'").fetchone()[0]
        checks.append({"name": "database_integrity", "status": "pass" if integrity == "ok" else "fail", "details": [str(integrity)]})
        checks.append({"name": "production_data", "status": "fail" if samples else "pass", "details": [f"historical_sample_leads={samples}"]})
    except (ValueError, sqlite3.Error):
        checks.append({"name": "database", "status": "fail", "details": ["Initialize a dedicated database and verify its schema/integrity"]})
    checks.append({"name": "external_execution", "status": "warning" if not s.live_side_effects_enabled else "pass",
                   "details": ["Disarmed; enable only after controlled acceptance" if not s.live_side_effects_enabled else "Explicitly enabled; provider acceptance still needs verification"]})
    return {"ready": not any(c["status"] == "fail" for c in checks), "checks": checks,
            "scope": "Local checks only; not proof of vendor entitlements, HTTPS, backups, supervision or live acceptance"}


def initialize_production(source: Path, destination: Path, db_path: Path) -> None:
    """Preserve existing config/data. Create a separate disarmed production profile."""
    source, destination, db_path = source.resolve(), destination.resolve(), db_path.resolve()
    if not source.is_file():
        raise ValueError("Source configuration does not exist")
    if source == destination or destination.exists() or db_path.exists():
        raise ValueError("Production config and database targets must be NEW; existing files are never overwritten")
    values = {key: value for key, value in dotenv_values(source, interpolate=False).items() if value is not None}
    for key in ("PUBLIC_WEBHOOK_URL", "HUBSPOT_CLIENT_SECRET", "RESEND_WEBHOOK_SECRET", "FIREFLIES_WEBHOOK_SECRET", "MAIL_REPLY_DOMAIN", "ESIGN_ALLOWED_RECIPIENTS"):
        values.setdefault(key, "")
    values.update(APP_ENV="production", DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
                  DASHBOARD_PASSWORD=secrets.token_urlsafe(32), WEBHOOK_SECRET=secrets.token_urlsafe(32),
                  MAIL_THREAD_SECRET=secrets.token_urlsafe(32), LIVE_SIDE_EFFECTS_ENABLED="false",
                  CRM_SYNC_ENABLED="false", ESIGN_MODE="test")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={json.dumps(value, ensure_ascii=False)}\n")
    if sys.platform != "win32":
        destination.chmod(0o600)
    store = SQLiteStore(f"sqlite:///{db_path.as_posix()}")
    try:
        store.set_flag("global_kill_switch", True)
        store.audit("human:cli", "production_initialized", "New empty database; external delivery disarmed")
    finally:
        store.connection.close()


def snapshot(source: Path, destination: Path) -> None:
    """SQLite online backup API; restores also require a new destination."""
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file() or source == destination:
        raise ValueError("Source must be an existing database and target must differ")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as origin:
        if origin.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Source database failed integrity verification")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb"):
            pass  # Exclusive creation: no accidental overwrite.
        with sqlite3.connect(destination) as target:
            origin.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Snapshot failed integrity verification")


def operational_status(s: Settings, max_worker_age: int = 600) -> dict:
    path = database_path(s.database_url)
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute("SELECT seen_at FROM service_heartbeats WHERE service='worker'").fetchone()
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row[0])).total_seconds() if row else None
            fresh = age is not None and 0 <= age <= max_worker_age
            dead = db.execute("SELECT COUNT(*) FROM events WHERE status='dead'").fetchone()[0]
            failed = db.execute("SELECT COUNT(*) FROM outbox WHERE status='failed'").fetchone()[0]
    except (sqlite3.Error, ValueError):
        return {"healthy": False, "worker_fresh": False, "reason": "Database is unavailable or needs schema initialization; no changes made"}
    return {"healthy": fresh and dead == 0 and failed == 0, "worker_fresh": fresh, "dead_events": dead, "failed_deliveries": failed}
