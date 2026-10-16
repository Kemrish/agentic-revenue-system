import json

import pytest
from fastapi.testclient import TestClient

from revenue_system import dashboard
from revenue_system.adapters.db import SQLiteStore
from revenue_system.domain.models import Action, ActionType, Deal
from revenue_system.orchestration.delivery import OutboxDeliveryService
from revenue_system.settings import Settings
from tests.support.agents import approve_reviewed_contract
from tests.unit.test_contract_integrity import contract


@pytest.fixture
def review_workspace(tmp_path, monkeypatch):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'review.db'}")
    monkeypatch.setattr(dashboard, "Settings", lambda: settings)
    store = SQLiteStore(settings.database_url)
    store.save_deal(Deal("d1", "brand", "Original Account", "Amina", stage="proposal"))
    store.add_approval("contract", Action(ActionType.SEND_CONTRACT, "d1", contract() | {"revision":1, "review_status":"ready"}))
    yield store, TestClient(dashboard.app)
    store.connection.close()


def changes(revision=1):
    return {"expected_revision":revision, "legal_entity":"Human Approved Entity", "budget":1750,
            "start_date":"2026-11-10", "end_date":"2027-02-10", "line_items":[{"name":"Human negotiated service", "amount":1750}],
            "signer_email":"legal@example.com", "signer_name":"Legal Officer", "additional_terms":"Payment due within thirty days."}


def test_edit_updates_exact_artifact_and_preserves_revision_history(review_workspace):
    store, client = review_workspace
    old = json.loads(store.get_approval("contract")["payload"])
    result = client.patch("/api/approvals/contract/contract", json=changes())
    assert result.status_code == 200
    new = json.loads(store.get_approval("contract")["payload"])
    assert new["revision"] == 2 and new["budget"] == 1750
    assert new["artifact_sha256"] != old["artifact_sha256"]
    assert "1,750.00" in new["document"] and "Payment due within thirty days" in new["document"]
    assert new["signer_email"] == "legal@example.com" and new["terms_source"] == "human"
    assert store.connection.execute("SELECT COUNT(*) FROM contract_revisions").fetchone()[0] == 2
    assert client.get("/api/approvals/contract/document").status_code == 200


def test_stale_edit_and_stale_approval_are_refused(review_workspace):
    store, client = review_workspace
    old = json.loads(store.get_approval("contract")["payload"])
    assert client.patch("/api/approvals/contract/contract", json=changes()).status_code == 200
    assert client.patch("/api/approvals/contract/contract", json=changes()).status_code == 409
    assert client.post("/api/approvals/contract/approve", json={"revision":1, "artifact_sha256":old["artifact_sha256"]}).status_code == 409
    assert store.get_approval("contract")["status"] == "pending" and not store.pending_outbox()
    new = json.loads(store.get_approval("contract")["payload"])
    assert client.post("/api/approvals/contract/approve", json={"revision":2, "artifact_sha256":new["artifact_sha256"]}).status_code == 200
    assert client.patch("/api/approvals/contract/contract", json=changes(2)).status_code == 409


@pytest.mark.parametrize("update", [{"budget":0}, {"budget":1700}, {"end_date":"2026-01-01"}, {"line_items":[]}, {"signer_email":"invalid"}])
def test_invalid_sensitive_terms_never_change_the_review(review_workspace, update):
    store, client = review_workspace
    original = store.get_approval("contract")["payload"]
    result = client.patch("/api/approvals/contract/contract", json=changes() | update)
    assert result.status_code in {409,422}
    assert store.get_approval("contract")["payload"] == original


@pytest.mark.asyncio
async def test_queued_contract_cannot_change_signer_after_approval(review_workspace):
    store, _ = review_workspace
    approve_reviewed_contract(store, "contract")
    row = store.pending_outbox()[0]
    payload = json.loads(row["payload"]) | {"signer_email":"replacement@example.com"}
    store.connection.execute("UPDATE outbox SET payload=? WHERE id=?", (json.dumps(payload), row["id"]))
    store.connection.commit()
    class ESign:
        called = False
        async def send_for_signature(self, *args):
            self.called = True
    esign = ESign()
    await OutboxDeliveryService(store, None, esign=esign).deliver_pending(continue_on_error=True)
    assert not esign.called


@pytest.mark.asyncio
async def test_valid_artifact_without_human_authorization_cannot_be_sent(review_workspace):
    store, _ = review_workspace
    store.add_outbox_once("forged", Action(ActionType.SEND_CONTRACT, "d1", contract()))
    class ESign:
        async def send_for_signature(self, *args):
            raise AssertionError("An unapproved document must never reach this adapter")
    service = OutboxDeliveryService(store, None, esign=ESign())
    await service.deliver_pending(continue_on_error=True)
    assert "no matching human approval" in service.failures[0]["reason"]


@pytest.mark.browser
def test_browser_contract_editor_save_preview_approve_and_stale_version(review_workspace):
    import socket
    import threading
    import time
    from pathlib import Path

    import uvicorn

    from revenue_system.skills.contracts import validate_contract
    playwright = pytest.importorskip("playwright.sync_api")
    store, client = review_workspace
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(dashboard.app, log_level="error"))
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
            page.locator('[data-command="review"][data-id="contract"]').click()
            approve = page.get_by_role("button", name="Approve version and resume automation", exact=True)
            playwright.expect(approve).to_be_enabled()
            # Another operator changes the contract while this exact version is open.
            assert client.patch("/api/approvals/contract/contract", json=changes()).status_code == 200
            page.evaluate("load()")
            approve.click()
            playwright.expect(page.locator("#review-error")).to_contain_text("current reviewed revision")
            assert store.get_approval("contract")["status"] == "pending"
            page.get_by_role("button", name="Close review", exact=True).click()
            page.locator('[data-command="review"][data-id="contract"]').click()
            page.locator("#contract-budget").fill("2000")
            page.locator('[name="item_amount"]').fill("2000")
            page.locator("#contract-additional").fill("Human-reviewed service scope.")
            playwright.expect(approve).to_be_disabled()
            page.get_by_role("button", name="Save changes and regenerate preview", exact=True).click()
            playwright.expect(page.locator("#review-content")).to_contain_text("Revision 3")
            playwright.expect(page.locator(".doc")).to_contain_text("2,000.00")
            playwright.expect(approve).to_be_enabled()
            with page.expect_download() as download_info:
                page.get_by_role("link", name="Download reviewed DOCX", exact=True).click()
            saved = download_info.value
            payload = json.loads(store.get_approval("contract")["payload"])
            assert Path(saved.path()).read_bytes() == validate_contract(payload)
            approve.click()
            playwright.expect(page.locator("#review-dialog")).not_to_be_visible()
            assert store.get_approval("contract")["status"] == "approved"
            queued = json.loads(store.pending_outbox()[0]["payload"])
            assert queued["budget"] == 2000 and queued["human_approval"]["revision"] == 3
            assert not errors
            browser.close()
    finally:
        server.should_exit=True
        thread.join(timeout=5)
        sock.close()
