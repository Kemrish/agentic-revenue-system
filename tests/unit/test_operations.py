import sqlite3

import pytest

from revenue_system.adapters.db import SQLiteStore
from revenue_system.operations import initialize_production, readiness, snapshot
from revenue_system.settings import Settings


def test_production_init_preserves_source_and_refuses_overwrites(tmp_path):
    source = tmp_path / ".env"
    source.write_text("OPENROUTER_API_KEY=test-key\nDASHBOARD_PASSWORD=old\n", encoding="utf-8")
    original = source.read_bytes()
    target, database = tmp_path / ".env.production", tmp_path / "data" / "production.db"
    initialize_production(source, target, database)
    assert source.read_bytes() == original
    settings = Settings(_env_file=target, dashboard_password="x" * 32, webhook_secret="w" * 32)
    assert settings.openrouter_api_key == "test-key"
    values = target.read_text()
    assert '"production"' in values and 'LIVE_SIDE_EFFECTS_ENABLED="false"' in values
    store = SQLiteStore(f"sqlite:///{database}")
    assert store.flag_enabled("global_kill_switch") and store.connection.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0
    store.connection.close()
    with pytest.raises(ValueError, match="never overwritten"):
        initialize_production(source, target, database)


def test_snapshot_and_restore_use_new_targets_and_preserve_source(tmp_path):
    source, backup, restored = [tmp_path / name for name in ("source.db", "backup.db", "restored.db")]
    store = SQLiteStore(f"sqlite:///{source}")
    store.add_event_once("retained", "event", {"value": 1})
    snapshot(source, backup)
    snapshot(backup, restored)
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT id FROM events").fetchone()[0] == "retained"
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with pytest.raises(FileExistsError):
        snapshot(source, backup)
    assert store.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    store.connection.close()


def test_preflight_is_read_only_and_never_discloses_credentials(tmp_path):
    missing = tmp_path / "not-created.db"
    s = Settings(database_url=f"sqlite:///{missing}", dashboard_password="private-password", openrouter_api_key="private-key")
    report = readiness(s)
    assert not report["ready"] and not missing.exists()
    assert "private-password" not in str(report) and "private-key" not in str(report)


def test_preflight_detects_old_sample_data(tmp_path):
    from revenue_system.domain.models import Deal
    s = Settings(database_url=f"sqlite:///{tmp_path / 'old.db'}")
    store = SQLiteStore(s.database_url)
    store.save_deal(Deal("lead-brand-001", "brand", "Sample", "Contact"))
    store.connection.close()
    checks = {check["name"]: check for check in readiness(s)["checks"]}
    assert checks["database_integrity"]["status"] == "pass"
    assert checks["production_data"]["status"] == "fail"


def test_monitor_detects_missing_worker_and_dead_events(tmp_path):
    from revenue_system.operations import operational_status
    s = Settings(database_url=f"sqlite:///{tmp_path / 'monitor.db'}")
    store = SQLiteStore(s.database_url)
    assert not operational_status(s)["healthy"]
    store.heartbeat()
    assert operational_status(s)["healthy"]
    store.add_event_once("dead", "event", {})
    store.connection.execute("UPDATE events SET status='dead'")
    store.connection.commit()
    assert not operational_status(s)["healthy"]
    store.connection.close()


def test_monitor_refuses_to_create_a_missing_database(tmp_path):
    from revenue_system.operations import operational_status
    missing = tmp_path / "missing.db"
    result = operational_status(Settings(database_url=f"sqlite:///{missing}"))
    assert not result["healthy"] and not missing.exists()


def test_cli_emergency_pause_needs_no_working_provider_configuration(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from revenue_system.cli import app
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    database = tmp_path / "emergency.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    result = CliRunner().invoke(app, ["kill-switch", "--enabled"])
    assert result.exit_code == 0, result.output
    store = SQLiteStore(f"sqlite:///{database}")
    assert store.flag_enabled("global_kill_switch")
    store.connection.close()
