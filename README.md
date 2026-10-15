# Agentic Revenue System

An AI-assisted revenue operations application. Agents interpret leads, replies, and call transcripts and return typed proposals. Python code owns scoring, stage transitions, approvals, delivery, consent checks, and audit records.

```text
Import / signed gateway → durable event → worker → agent / deterministic skill
                                                ↓
                              policy → approval or outbox → provider
                                                ↓
                           delivery / signature event → deal progression
```

The application supports brand and publisher workflows through YAML segment packs. The runtime contains operator tools and integration boundaries; automated test doubles live under `tests/support`.

## Requirements and installation

Python 3.12 or later is required.

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m revenue_system.cli validate-packs
```

If `.env` already exists, preserve its values and add only missing settings. Fill the credentials and operator password before starting live services. Secrets, databases, generated documents, and runtime artifacts must not be committed.

## Configuration

The full configuration reference is [`.env.example`](.env.example). Typical operator settings:

```env
APP_ENV=production
DATABASE_URL=sqlite:///./revenue_system.db
DASHBOARD_USERNAME=operator
DASHBOARD_PASSWORD=<strong unique password>
WEBHOOK_SECRET=<separate random gateway secret>
RUNTIME_MODE=live
CLAUDE_MODE=live
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<secret>
MAIL_MODE=live
MAIL_API_KEY=<secret>
MAIL_FROM_ADDRESS=<verified sender>
MAIL_ALLOWED_RECIPIENTS=<permitted destinations, comma separated>
LIVE_SIDE_EFFECTS_ENABLED=false
```

`CLAUDE_MODE` is the existing runner-mode setting for both supported LLM providers. Set `LLM_PROVIDER=claude` or `anthropic` and `ANTHROPIC_API_KEY` to use the Claude Agent SDK instead of OpenRouter.

Integrations must be individually enabled. Non-live settings disable the corresponding operation and return an explicit error; they do not return synthetic delivery IDs or canned model results. `LIVE_SIDE_EFFECTS_ENABLED=true` explicitly permits configured live mail/e-signature calls. Mail remains restricted to `MAIL_ALLOWED_RECIPIENTS`.

E-signature uses `ESIGN_DOCUMENT_URL`, signer settings, and its own API key. Keep `ESIGN_TEST_MODE=true` until the real commercial workflow and provider plan have been verified. Ensure the exact approved document is the artifact sent for signature; see the release limitations in the operations runbook.

## Running the system

Run each process from the project root, using the same database configuration:

```powershell
# Terminal 1: operator dashboard (http://127.0.0.1:8000)
python -m revenue_system.cli ui

# Terminal 2: signed event receiver (http://127.0.0.1:8001)
python -m revenue_system.cli webhooks

# Terminal 3: durable event processing
python -m revenue_system.cli worker
```

Add `--deliver` to the worker command to deliver permitted queued actions automatically. Human approval remains required where policy demands it. Without that option, an operator can review the delivery batch from Outbox or invoke `approvals deliver`.

Production dashboard access requires a configured password. Use HTTPS at a trusted reverse proxy for remote deployment. The current authentication supports one configured operator, not multi-user roles or SSO.

## Lead intake and operation

Real lead data enters through a JSON import or a signed, normalized webhook. A lead needs a stable `lead_id`, configured `segment`, `company_name`, and `contact_name`; supply `email` and fit/intent/engagement evidence for outreach and scoring.

```powershell
python -m revenue_system.cli ingest --file leads.json
python -m revenue_system.cli worker --once
```

The worker persists a score and tier, retrieves active lesson statements, drafts outreach, and evaluates policy. The dashboard provides:

- **Command center:** stable operational totals and actual policy decisions.
- **Pipeline:** account details, scoring evidence, stages, and audit history.
- **Approvals:** exact recipient/message or document, policy reason, and approve/reject decisions. Rejection requires a reason and proposes a lesson.
- **Outbox:** reviewed destinations, explicit delivery, provider results, and failure recovery.
- **Lessons:** review and promotion of proposed learning records.
- **Audit trail:** operator attribution, stage transitions, denials, delivery evidence, and queue recovery.

`AUTO` permits an action without human review. `REQUIRE_APPROVAL` pauses it for an operator. `DENY` blocks an unsafe or unsubscribed-contact action. `KILL_SWITCH` pauses routing and delivery. Agents cannot override these decisions.

## Operations and recovery

```powershell
python -m revenue_system.cli health
python -m revenue_system.cli approvals list
python -m revenue_system.cli approvals approve <approval-id>
python -m revenue_system.cli approvals reject <approval-id> --reason "Explain the rejection"
python -m revenue_system.cli approvals deliver
python -m revenue_system.cli queues failed
python -m revenue_system.cli queues retry events <event-id>
python -m revenue_system.cli queues retry outbox <outbox-id>
python -m revenue_system.cli kill-switch --enabled
python -m revenue_system.cli kill-switch --disabled
```

Queue claims prevent concurrent consumers from processing the same active item. Expiring leases recover interrupted work; bounded retries use persistent backoff. Exhausted events and deliveries remain visible for explicit operator recovery. Delivery is at least once: reconcile ambiguous provider acceptance before retrying.

## Tests

```powershell
python -m pytest -q -m "not browser" -p no:cacheprovider --basetemp .pytest-run-core
python -m pip install -e ".[dev,browser]"
python -m pytest -q -m browser -p no:cacheprovider --basetemp .pytest-run-browser
```

Browser tests require installed Microsoft Edge. Tests use isolated databases and provider/model doubles under `tests/`; they never inherit live sending modes or the operator's configured database.

## Deployment scope

The [production runbook](docs/production.md) documents configuration, webhook payloads, retries, recovery, backups, and remaining release work. Native provider webhook verification/mapping, full CRM synchronization, exact-document signature delivery, HTTPS, supervision, and monitoring must be verified for the deployment. SQLite supports a bounded deployment sharing one local database; multi-host scale needs a database and queue migration.

## Documentation

- [Architecture](docs/architecture.md)
- [Architecture decisions and trade-offs](docs/decisions.md)
- [Implementation](docs/implementation.md)
- [System overview](docs/system-overview.md)
- [Production operations](docs/production.md)
