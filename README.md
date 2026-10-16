# Agentic Revenue System

An AI-assisted revenue operations application. Agents interpret leads, replies, and call transcripts and return typed proposals. Python code owns scoring, stage transitions, approvals, delivery, consent checks, and audit records.

```text
Import / verified provider → durable event → worker → agent / deterministic skill
                                                ↓
                              policy → approval or outbox → provider
                                                ↓
                           delivery / signature event → deal progression
```

The application supports brand and publisher workflows through YAML segment packs. The runtime contains operator tools and integration boundaries; automated test doubles live under `tests/support`.

## Requirements and installation

Python 3.12 or later is required. The locked production environment and container use Python 3.14.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
Copy-Item .env.example .env
python -m revenue_system.cli validate-packs
```

If `.env` already exists, preserve it. `production init` creates a separate ignored `.env.production`, generates operator/internal secrets, and initializes an empty paused database without overwriting existing data. Secrets, databases and runtime artifacts must not be committed.

```powershell
.venv\Scripts\python.exe -m revenue_system.cli production init
$env:ARS_ENV_FILE=".env.production"
.venv\Scripts\python.exe -m revenue_system.cli production preflight
```

Review `.env.production` privately, supply the missing deployment/provider settings, and select it in every new service terminal. Existing process environment variables override file values. Preflight is deliberately red until the real requirements are met; it makes no provider calls. See [deployment and integrations](docs/deployment.md).

No public domain yet? The optional [local sandbox](docs/local-sandbox.md) exercises signed callbacks and the UI using isolated test doubles. It never sends real messages and is excluded from production builds.

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

E-signature uploads the exact reviewed per-deal DOCX, not a shared document URL. Approval and delivery verify its SHA-256 fingerprint and signer; `ESIGN_ALLOWED_RECIPIENTS` restricts destinations. Legacy URL/global signer settings are not used as substitutes. Leave `ESIGN_MODE=test` to disable the integration when you do not have a paid production API plan. Production live e-sign requires `ESIGN_TEST_MODE=false` and verified provider access.

## Running the system

Run each process with the same selected configuration and database. Installed wheels include both packs, their templates, prompts and UI assets; launching from the repository root is not required.

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

Real lead data enters through JSON import, an explicit HubSpot contact import, or a verified native HubSpot contact-creation webhook. The worker fetches the contact and maps configured CRM properties. A lead needs a stable `lead_id`, configured `segment`, `company_name`, and `contact_name`; supply `email` and fit/intent/engagement evidence for outreach and scoring. The system does not scrape or discover companies independently.

```powershell
python -m revenue_system.cli ingest --file leads.json
python -m revenue_system.cli import-contact <numeric-hubspot-contact-id>
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

Native HubSpot V3, Resend, Fireflies V2 and Dropbox Sign ingress is implemented. The worker retries provider lookups, correlates replies and transcripts to deals, and verifies signature completion against provider state. Optional CRM write-back updates configured score/stage properties through the outbox; it is not bidirectional CRM synchronization. Ambiguous provider acceptance is parked for operator reconciliation rather than silently treated as success.

The [deployment guide](docs/deployment.md) covers the non-root container, process supervision, HTTPS template, backups, monitoring and the live acceptance checklist. Local tests and mock callbacks do not prove vendor credentials, real DNS/TLS, delivery, or paid-plan access. SQLite supports a bounded single-host deployment; multi-host scale needs a database and queue migration.

## Documentation

- [Architecture](docs/architecture.md)
- [Architecture decisions and trade-offs](docs/decisions.md)
- [Implementation](docs/implementation.md)
- [System overview](docs/system-overview.md)
- [Production operations](docs/production.md)
- [Deployment and native integrations](docs/deployment.md)
- [Local-only sandbox](docs/local-sandbox.md)
