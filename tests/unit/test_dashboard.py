from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from revenue_system import dashboard
from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType, Deal, Score, Tier
from revenue_system.settings import Settings

app = dashboard.app


@pytest.fixture
def operator_workspace(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'operators.db'}"
    settings = Settings(_env_file=None, database_url=url, runtime_mode="test", llm_provider="test",
                        mail_mode="test", live_side_effects_enabled=False, mail_allowed_recipients="review@example.com")
    monkeypatch.setattr(dashboard, "Settings", lambda: settings)

    class Mail:
        calls = []

        async def send(self, recipient, subject, body, key):
            self.calls.append((recipient, subject, body, key))
            return "mail-proof-1"

    mail = Mail()
    monkeypatch.setattr(dashboard, "build_container", lambda _: SimpleNamespace(
        store=SQLiteStore(url), mail=mail, esign=None))
    store = SQLiteStore(url)
    store.save_deal(Deal("d1", "brand", "Review Account", "Amina", score=Score(90,80,0,86,Tier.A,"Fit evidence")))
    store.add_approval("a1", Action(ActionType.SEND_FIRST_TOUCH, "d1",
                       {"subject": "Campaign proposal", "body": "Exact message for review", "recipient": "review@example.com"}))
    yield TestClient(app), store, mail
    store.connection.close()


def test_dashboard_renders_and_exposes_policy_scenarios(operator_workspace):
    client, _, _ = operator_workspace
    assert client.get("/").status_code == 200
    payload = client.get("/api/overview").json()
    assert {item["decision"] for item in payload["scenarios"]} == {"AUTO", "REQUIRE_APPROVAL", "DENY", "KILL_SWITCH"}


def test_review_contains_message_and_policy_evidence(operator_workspace):
    client, _, _ = operator_workspace
    item = client.get("/api/overview").json()["approvals"][0]
    assert item["company"] == "Review Account"
    assert item["payload"]["body"] == "Exact message for review"
    assert item["payload"]["recipient"] == "review@example.com"
    assert "tier A" in item["policy_reason"]
    assert client.get("/static/dashboard.js").status_code == 200


def test_rejection_requires_reason_and_retains_history(operator_workspace):
    client, store, _ = operator_workspace
    assert client.post("/api/approvals/a1/reject", json={"reason": "   "}).status_code == 400
    assert store.get_approval("a1")["status"] == "pending"
    assert client.post("/api/approvals/a1/reject", json={"reason": "Need customer-specific evidence"}).status_code == 200
    data = client.get("/api/overview").json()
    assert data["metrics"]["rejected_approvals"] == 1
    assert not data["approvals"]
    assert data["approval_history"][0]["rejection_reason"] == "Need customer-specific evidence"
    assert any(a["action"] == "approval_rejected" and a["deal_id"] == "d1" for a in data["audit"])
    assert store.connection.execute("SELECT status FROM lessons").fetchone()[0] == "proposed"
    assert client.post("/api/approvals/a1/approve").status_code == 409
    assert not store.pending_outbox()


def test_review_to_delivery_is_durable_and_single_decision(operator_workspace):
    client, store, mail = operator_workspace
    assert client.post("/api/approvals/a1/approve").status_code == 200
    assert client.post("/api/approvals/a1/approve").status_code == 409
    assert len(store.pending_outbox()) == 1
    assert client.post("/api/outbox/deliver").json()["delivered"] == ["approved:a1"]
    assert len(mail.calls) == 1
    assert client.post("/api/outbox/deliver").json()["delivered"] == []
    assert len(mail.calls) == 1
    assert client.get("/api/overview").json()["outbox"][0]["status"] == "sent"


def test_missing_recipient_is_explicitly_repaired(operator_workspace):
    client, store, mail = operator_workspace
    store.add_outbox_once("legacy", Action(ActionType.SEND_FIRST_TOUCH, "d1", {"subject":"Legacy", "body":"Draft"}))
    failed = client.post("/api/outbox/deliver").json()
    assert "missing recipient" in failed["failures"][0]["reason"]
    assert not mail.calls
    assert client.patch("/api/outbox/legacy/recipient", json={"recipient":"review@example.com"}).status_code == 200
    assert client.patch("/api/outbox/legacy/recipient", json={"recipient":"other@example.com"}).status_code == 409
    assert client.post("/api/outbox/deliver").json()["delivered"] == ["legacy"]
    assert mail.calls[0][0] == "review@example.com"


def test_emergency_stop_preserves_queue(operator_workspace):
    client, store, mail = operator_workspace
    client.post("/api/approvals/a1/approve")
    store.set_flag("global_kill_switch", True)
    assert client.post("/api/outbox/deliver").status_code == 409
    assert not mail.calls
    assert len(store.pending_outbox()) == 1


def test_live_recipient_validation(operator_workspace, monkeypatch):
    client, _, _ = operator_workspace
    settings = dashboard.Settings()
    monkeypatch.setattr(dashboard, "Settings", lambda: settings.model_copy(update={"runtime_mode":"live", "mail_mode":"live"}))
    assert client.patch("/api/approvals/a1/recipient", json={"recipient":"unapproved@example.com"}).status_code == 400


@pytest.mark.browser
def test_browser_navigation_refresh_review_rejection_and_delivery(operator_workspace, tmp_path):
    """Exercise actual browser events against an isolated database and fake mail."""
    import socket
    import threading
    import time

    import uvicorn

    playwright = pytest.importorskip("playwright.sync_api")
    _, store, mail = operator_workspace
    store.add_approval("a2", Action(ActionType.SEND_FIRST_TOUCH, "d1",
                       {"subject":"Second proposal", "body":"Message to deliver", "recipient":"review@example.com"}))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(.02)
        assert server.started
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width":1500,"height":1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{port}/#approvals")
            playwright.expect(page.locator("#page-title")).to_have_text("Approval center")
            playwright.expect(page.locator("[data-metric=pending_approvals]")).to_have_text("2")
            page.clock.install()
            for view, title in [("pipeline","Pipeline workspace"),("outbox","Outbox operations"),
                                ("audit","Audit trail"),("overview","Revenue command center")]:
                page.locator(f'nav [data-view="{view}"]').click()
                playwright.expect(page.locator("#page-title")).to_have_text(title)
                playwright.expect(page.locator(f'nav [data-view="{view}"]')).to_have_attribute("aria-current","page")
                page.clock.fast_forward(11000)
                playwright.expect(page.locator("#metrics .metric-card")).to_have_count(5)
                playwright.expect(page.locator("#page-title")).to_have_text(title)
            page.goto(f"http://127.0.0.1:{port}/#approvals")
            page.reload()
            page.locator('[data-command="review"][data-id="a1"]').click()
            playwright.expect(page.locator("#review-dialog")).to_be_visible()
            playwright.expect(page.locator("#review-content")).to_contain_text("Exact message for review")
            playwright.expect(page.locator("#review-content")).to_contain_text("review@example.com")
            page.get_by_role("button",name="Reject with reason",exact=True).click()
            page.locator("#rejection-reason").fill("Needs stronger account evidence")
            page.clock.install()
            page.clock.fast_forward(12000)
            playwright.expect(page.locator("#rejection-reason")).to_have_value("Needs stronger account evidence")
            page.get_by_role("button",name="Confirm rejection",exact=True).click()
            playwright.expect(page.locator("#review-dialog")).not_to_be_visible()
            playwright.expect(page.locator("[data-metric=rejected_approvals]")).to_have_text("1")
            page.locator('[data-command="review"][data-id="a2"]').click()
            page.get_by_role("button",name="Approve and queue",exact=True).click()
            playwright.expect(page.locator("#review-dialog")).not_to_be_visible()
            page.locator('nav [data-view="outbox"]').click()
            page.get_by_role("button",name="Review delivery batch",exact=True).click()
            playwright.expect(page.locator("#review-content")).to_contain_text("review@example.com")
            page.get_by_role("button",name="Deliver approved work",exact=True).click()
            playwright.expect(page.locator("[data-metric=outbox_pending]")).to_have_text("0")
            assert len(mail.calls) == 1
            page.locator('nav [data-view="audit"]').click()
            playwright.expect(page.locator("#page-view .metric-card")).to_have_count(0)
            playwright.expect(page.locator("#page-view")).to_contain_text("Needs stronger account evidence")
            page.clock.fast_forward(11000)
            playwright.expect(page.locator("[data-metric=rejected_approvals]")).to_have_text("1")
            positions=page.locator("#metrics .metric-card").evaluate_all("els => els.map(el => el.getBoundingClientRect().top)")
            assert len(set(positions)) == 1
            page.screenshot(path=str(tmp_path / "audit-desktop.png"), full_page=True)
            page.set_viewport_size({"width":390,"height":844})
            page.locator('nav [data-view="pipeline"]').click()
            playwright.expect(page.locator("#page-title")).to_have_text("Pipeline workspace")
            assert not errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def test_kill_switch_and_lesson_curation_are_audited(operator_workspace):
    client, store, _ = operator_workspace
    client.post("/api/kill-switch", json={"enabled": True})
    assert client.get("/api/overview").json()["runtime"]["kill_switch"]
    lesson_id = client.post("/api/lessons", json={"statement": "Lead with measurement proof"}).json()["id"]
    assert client.post(f"/api/lessons/{lesson_id}/status", json={"status": "active"}).status_code == 200
    assert store.active_lessons("brand")[0]["id"] == lesson_id
    actions = {row["action"] for row in store.connection.execute("SELECT action FROM audit_log")}
    assert {"KILL_SWITCH", "lesson_proposed", "lesson_active"} <= actions


def test_dashboard_sign_in_and_operator_attribution(operator_workspace, monkeypatch):
    client, store, _ = operator_workspace
    settings = dashboard.Settings().model_copy(update={"dashboard_password": "s3cret", "dashboard_username": "amina"})
    monkeypatch.setattr(dashboard, "Settings", lambda: settings)
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/overview", auth=("amina", "wrong")).status_code == 401
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.post("/api/approvals/a1/approve", auth=("amina", "s3cret")).status_code == 200
    actor = store.connection.execute("SELECT actor FROM audit_log WHERE action='approval_approved'").fetchone()["actor"]
    assert actor == "human:amina"


def test_production_dashboard_fails_closed_without_password(operator_workspace, monkeypatch):
    client, _, _ = operator_workspace
    settings = dashboard.Settings().model_copy(update={"app_env":"production", "dashboard_password":""})
    monkeypatch.setattr(dashboard, "Settings", lambda: settings)
    assert client.get("/api/overview").status_code == 503
    assert client.get("/healthz").status_code == 200


def test_cross_origin_mutations_are_refused(operator_workspace):
    client, store, _ = operator_workspace
    response = client.post("/api/approvals/a1/approve", headers={"Origin":"https://untrusted.example"})
    assert response.status_code == 403
    assert store.get_approval("a1")["status"] == "pending"
    assert client.post("/api/approvals/a1/approve", headers={"Origin":"http://testserver"}).status_code == 200


def test_presentation_routes_are_not_exposed(operator_workspace):
    client, store, _ = operator_workspace
    assert client.post("/api/demo/reset", json={"confirm":"RESET"}).status_code == 404
    assert client.post("/api/demo/run").status_code == 404
    assert client.get("/api/system").status_code == 404
    assert client.post("/api/lab/score", json={}).status_code == 404
    assert store.get_approval("a1") is not None


def test_failed_queue_recovery_is_audited(operator_workspace):
    client, store, _ = operator_workspace
    store.add_event_once("dead-event", "unknown", {})
    store.connection.execute("UPDATE events SET status='dead',attempts=5,last_error='bad payload'")
    store.connection.commit()
    response = client.post("/api/queues/events/dead-event/retry")
    assert response.status_code == 200
    assert client.post("/api/queues/events/dead-event/retry").status_code == 409
    assert store.connection.execute("SELECT action FROM audit_log ORDER BY id DESC").fetchone()[0] == "queue_retried"
