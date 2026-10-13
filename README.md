# Agentic Revenue System

An AI-assisted revenue lifecycle system that turns leads, replies, and call transcripts into governed revenue actions. Agents propose typed outputs; deterministic Python code owns state, policy, validation, approvals, delivery, and auditability.

```text
lead → score → outreach proposal → human approval → email delivery
                         ↓
reply triage → call intelligence → lesson loop → validated IO
                         ↓
                 approved e-sign request
```

The demo supports `brand` and `publisher` segments through the same orchestration and agent code.

## Architecture

This is a governed modular monolith:

- deterministic orchestration owns deal state and valid transitions;
- LLM agents return typed proposals rather than executing business actions;
- policy routes actions to `AUTO`, `REQUIRE_APPROVAL`, or `DENY`;
- approvals, outbox delivery, idempotency, kill switch, and audit records are durable;
- integrations are behind adapters and support live, replay, record, and test modes;
- YAML segment packs change messaging and qualification rules without code changes;
- SQLite is the local operational store for the demo.

Read the [architecture](docs/architecture.md), [decisions and trade-offs](docs/decisions.md), and [implementation plan](docs/implementation.md).

## Quick start

Requires Python 3.11+.

```powershell
python -m pip install -e ".[dev]"
python -m revenue_system.cli validate-packs
python -m pytest -q
python -m revenue_system.cli demo --mode replay
python -m revenue_system.cli ui
```

Replay mode is deterministic, requires no credentials, and is the recommended presentation fallback.

## Configuration

Copy `.env.example` to `.env`. Never commit `.env`, API keys, generated databases, or sensitive provider responses.

```env
RUNTIME_MODE=live
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=anthropic/claude-haiku-5.5

MAIL_MODE=live
MAIL_API_KEY=...
MAIL_FROM_ADDRESS=demo@your-verified-domain.com
MAIL_ALLOWED_RECIPIENTS=your-own-test-address@example.com
LIVE_SIDE_EFFECTS_ENABLED=true

ESIGN_MODE=live
ESIGN_API_KEY=...
ESIGN_BASE_URL=https://api.hellosign.com
ESIGN_DOCUMENT_URL=https://...
ESIGN_SIGNER_EMAIL=your-own-test-address@example.com
ESIGN_SIGNER_NAME=Your Name
ESIGN_TEST_MODE=true
```

Live mail is refused unless the recipient is in `MAIL_ALLOWED_RECIPIENTS`. Email and e-signature also require explicit `LIVE_SIDE_EFFECTS_ENABLED=true`.

### Dropbox Sign without a paid plan

Keep `ESIGN_TEST_MODE=true`. This creates a Dropbox Sign test request and records its provider ID, but does not send a real signer notification. The included [fictional demo agreement](fixtures/demo-agreement.pdf) is for testing only.

```powershell
python scripts/create_demo_pdf.py
```

## Live production-style demo

The workflow is approval-gated:

```powershell
python -m revenue_system.cli demo --mode live
python -m revenue_system.cli approvals list
python -m revenue_system.cli approvals approve <approval-id>
python -m revenue_system.cli approvals deliver
python -m revenue_system.cli audit <deal-id>
```

Agents never send approval-gated actions directly. `approvals deliver` sends only approved outbox items and marks them sent only after provider success.

### Operator dashboard

Start `python -m revenue_system.cli ui` and open `http://127.0.0.1:8000`.
Overview, Pipeline, Approvals, Outbox, and Audit trail have dedicated views; their URL hashes restore the current page after reload.
All five metric cards are permanent, including rejected approvals. Background refresh updates values without replacing an open review dialog or a draft rejection reason.

In Approvals, choose **Review details** to inspect the company, contact, recipient, subject, complete message, score, and policy reason.
**Approve and queue** persists that reviewed action. **Reject with reason** opens an in-app form; its explanation is stored with the decision, audit event, and proposed lesson.
Decision history retains approved and rejected proposals. Decisions cannot be reversed by a stale browser request.

In Outbox, review each pending action. If an older mail action has no recipient, open its details and explicitly save an allowlisted recipient.
Delivery does not silently choose the first address from the environment. A recipient already attached to a queued action cannot be changed after review.
Choose **Review delivery batch**, inspect the destinations, then **Deliver approved work**.
Successful actions are marked sent and retained in delivery history; failures remain pending with visible per-action errors and audit records.
The kill switch is checked immediately before each delivery, and contract actions use the e-signature adapter.

The dashboard is a local operator application. Authentication, roles, multi-process delivery coordination, and remote deployment hardening remain separate deployment work.
No new live provider calls are needed to verify the UI: the automated browser workflow uses an isolated database and test mail adapter.

```powershell
# Core and API regression tests
python -m pytest -q -m "not browser" -p no:cacheprovider --basetemp .pytest-run-core

# Browser workflow: requires installed Microsoft Edge
python -m pip install -e ".[dev,browser]"
python -m pytest -q -m browser -p no:cacheprovider --basetemp .pytest-run-browser
```

The fixture command `demo --mode replay` uses an in-memory store and does not populate the dashboard database.
For a live fixture run and UI presentation, select the same database for both commands:

```powershell
$env:DATABASE_URL="sqlite:///./presentation_demo.db"
python -m revenue_system.cli demo --mode live
python -m revenue_system.cli ui
```

```powershell
python -m revenue_system.cli approvals reject <approval-id>
python -m revenue_system.cli kill-switch --enabled
python -m revenue_system.cli kill-switch --disabled
```

Keep the mail allowlist limited to an address you control.

## Runtime modes

| Mode | Purpose |
|---|---|
| `test` | fake runners and isolated tests |
| `replay` | deterministic recorded responses, no network |
| `record` | capture live responses for later replay |
| `live` | configured LLM and integration adapters |

Modes can be selected independently per integration. Live OpenRouter plus replay integrations is a safe model-quality demo; live email requires an allowlist and explicit side-effect opt-in.

## Safety guarantees

- top-tier outreach and contracts require human approval;
- prompt-injection content is untrusted and cannot invoke tools;
- typed schemas and deterministic validators reject malformed agent output;
- duplicate events and deliveries use idempotency keys;
- provider failures remain pending and are audited;
- live mail is recipient-allowlisted;
- live e-sign is opt-in and Dropbox test mode is the no-paid-plan default;
- audit records capture policy, approval, delivery, and failure events;
- the kill switch can disable action processing.

## Testing

```powershell
python -m pytest -q
python -m revenue_system.cli validate-packs
python -m revenue_system.cli demo --mode replay
```

The suite covers scoring, transitions, policy, approvals, outbox delivery, mail/e-sign safety, prompt injection, replay integrity, IO validation, segment packs, and both vertical-slice segments.

## Production deployment notes

The current repository is demo-ready and intentionally simple. Before operating at production scale:

1. replace SQLite with PostgreSQL;
2. run the outbox worker as a supervised process;
3. use a secrets manager instead of local `.env` files;
4. configure signed provider webhooks;
5. add monitoring, alerting, rate limits, backups, and credential rotation;
6. use real recipient/domain governance instead of demo allowlists;
7. upgrade Dropbox Sign and disable test mode only when a paid plan and real legal workflow are approved.

## Documentation

- [Architecture](docs/architecture.md)
- [Decisions and trade-offs](docs/decisions.md)
- [Implementation plan](docs/implementation.md)
- [Demo script](docs/demo-script.md)
