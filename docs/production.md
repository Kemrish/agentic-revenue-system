# Production hardening and operations

This runbook describes the implemented service boundaries and the work still required for a real deployment. The application remains a modular Python application with SQLite persistence; this work does not add a distributed broker or microservices.

For the production profile, native provider endpoints, exact-document e-signature, container/HTTPS setup and the release checklist, read [Deployment and native integrations](deployment.md). Optional local mocks are documented separately in [Local sandbox](local-sandbox.md); they are excluded from production builds.

## Processes and ownership

| Process | Command | Responsibility |
|---|---|---|
| Operator UI/API | `python -m revenue_system.cli ui` | Review exact messages/documents, approve or reject, curate lessons, inspect queues and audit records |
| Signed event receiver | `python -m revenue_system.cli webhooks` | Authenticate normalized webhook JSON, validate it, and durably insert an event |
| Automatic event/delivery worker | `python -m revenue_system.cli worker` | Consume events, call agents, apply transitions, process bounded follow-ups/timers, deliver permitted actions and retry failures |
| Processing-only maintenance | `python -m revenue_system.cli worker --no-deliver` | Process events without dispatching external actions |

Use the same `DATABASE_URL` and segment packs in all processes. The webhook receiver acknowledges persistence, not completion of the agent workflow. The worker must run for events to progress.

`worker --once` processes events, runs a delivery cycle and applies delivery acknowledgements before exiting. `worker --once --no-deliver` never dispatches actions. `--deliver` remains an explicit synonym for the default. The continuous worker resumes after the single contract review checkpoint without another operator delivery step. `approvals deliver` remains an optional maintenance command.

## Configuration

Copy the variable names in `.env.example` into your deployment's secret/configuration mechanism. Do not commit credentials. Existing local `.env` values are not modified by the hardening implementation.

```env
APP_ENV=production
DATABASE_URL=sqlite:///./data/production.db
DASHBOARD_USERNAME=operator
DASHBOARD_PASSWORD=<strong unique operator password>
WEBHOOK_SECRET=<separate random shared secret for your ingress gateway>
WORKER_POLL_SECONDS=5
MAX_EVENT_ATTEMPTS=5
MAX_DELIVERY_ATTEMPTS=5
RETRY_BASE_SECONDS=5
QUEUE_LEASE_SECONDS=300
WEBHOOK_MAX_BYTES=1048576
```

The production dashboard refuses access when no password is configured. Operator APIs use HTTP Basic authentication and attribute approvals, rejections, lesson changes, recipient corrections, kill-switch changes, and manual queue retries to the authenticated operator. Use HTTPS at a trusted reverse proxy; Basic authentication is not transport encryption. Mutating browser requests with a different Origin are refused.

The runtime exposes operational endpoints only. It contains no fixture seeding, workspace reset, presentation pages, or interactive agent playground. Test doubles and canned responses belong exclusively to the automated test suite.

For live LLM execution set `RUNTIME_MODE=live`, `CLAUDE_MODE=live`, `LLM_PROVIDER=openrouter` or `claude`/`anthropic`, and the appropriate API key. All entry points use the same runner selection. Live runners load the versioned agent prompt and pass the actual structured context. Non-live integration modes refuse execution instead of returning synthetic results.

Email and e-signature still require their own live modes and `LIVE_SIDE_EFFECTS_ENABLED=true`. Mail must have an explicit allowlisted destination. Credentials being present does not prove provider acceptance or activate every integration automatically.

## Real lead intake

Import a JSON object or array with this shape:

```json
{
  "lead_id": "crm-contact-1001",
  "segment": "brand",
  "company_name": "Your permitted account",
  "contact_name": "Authorized contact",
  "email": "your-controlled-mailbox@example.com",
  "fit": 88,
  "intent": 70,
  "engagement": 0
}
```

```powershell
python -m revenue_system.cli ingest --file leads.json
python -m revenue_system.cli worker --once
python -m revenue_system.cli ui
```

Import validates every record and segment before inserting any event. Reimporting the same lead ID returns a duplicate. The worker scores the lead, retrieves active lessons, drafts non-commercial first-touch outreach, and automatically queues/delivers it for every tier when policy permits. Imported metadata never selects the action type or bypasses the autonomy rules. Prices, discounts, budgets and commitments are forbidden in unattended routine messages by prompt plus conservative deterministic checks; this is a backstop, not a semantic/legal classifier guarantee.

A second `lead.created` event for an existing lead does not rewind its stage, reset its consent flags, or send another first-touch draft. A future CRM-update event should have a separate, explicit update contract.

## Webhook contract

The receiver accepts **normalized internal JSON**, authenticated by a gateway using HMAC-SHA256. The routes are not native HubSpot, Resend, Fireflies, or Dropbox Sign webhook implementations. A provider gateway must verify that provider's native signature and event type, map its payload and contact identifiers, then sign this internal request.

Compute the lowercase hexadecimal SHA-256 HMAC over the exact HTTP body bytes using `WEBHOOK_SECRET`. Send it as `X-Signature: sha256=<digest>` and supply a stable provider event identifier in `X-Event-Id`. Changing whitespace after signing invalidates the signature. The receiver supports the established body event-ID fields as alternatives.

| Route | Internal event | Required normalized payload |
|---|---|---|
| `/webhooks/hubspot` | `lead.created` | `lead_id` (or `objectId`), `segment`, `company_name`, `contact_name`; optional email and 0–100 scoring features |
| `/webhooks/mail` | `reply.received` | `deal_id`, `text` |
| `/webhooks/fireflies` | `transcript.ready` | `deal_id`, `transcript`; optional transcript ID and explicit commercial terms |
| `/webhooks/esign` | `contract.signed` | `deal_id` and `provider_id` matching the delivered signature request |

Missing/invalid signatures are refused; an unconfigured secret returns 503. Invalid object shapes, unsupported segments, invalid scoring values, and over-limit bodies are refused before persistence. Duplicate event IDs return `duplicate`. Store the original provider event ID for auditing and do not generate a new ID on redelivery.

Signature events close only a deal in contracting with a recorded sent contract and a matching provider reference. The trusted internal gateway must forward only a verified completed-signature event. Native providers instead use `/providers/{provider}`; the e-sign resolver additionally queries the provider for completed state.

## Durability, retries, and recovery

Schema changes are additive: original records are retained, while retry fields, queue leases, provider references, indexes, and the timers table are added on store initialization. Back up before applying an upgrade to a valuable database.

Each worker claims a queued item using a database compare-and-set. Another process cannot process the same active claim. The claim has an owner and expiration; interrupted work becomes eligible again after expiry. Attempts are counted at claim time, including interrupted attempts. Exhausted events become `dead`; exhausted delivery actions become `failed`.

Event business writes and the processed marker commit together. Failed handlers roll back their business writes. Model execution is bounded within the lease; stale owners are prevented from acknowledging a newer owner's work. Queue leases are at least 60 seconds, with a 300-second default.

Failures retain `last_error` and a persisted retry timestamp. Delay is `RETRY_BASE_SECONDS * 2^(attempt - 1)`, capped at one hour. The worker polling interval does not bypass this delay. The kill switch pauses delivery without consuming its retry budget. Clearing it resumes permitted work; it does not resurrect dead/failed items.

The dashboard's Audit and Outbox views show queue health and recovery controls. Operators can also use:

```powershell
python -m revenue_system.cli health
python -m revenue_system.cli queues failed
python -m revenue_system.cli queues retry events <event-id>
python -m revenue_system.cli queues retry outbox <outbox-id>
```

Fix the cause first. Retry resets the exhausted budget, retains the original item/idempotency key, and records the operator action. It does not override consent, unsafe-content checks, or the mail allowlist.

A successful delivery stores the provider reference and an `action.delivered` event atomically with the sent status. The worker advances mail to outreach and signature requests to contracting. A queued message alone does not prove delivery; replies, transcripts, and signatures must enter through their verified event sources.

External delivery is **at least once**, not a universal exactly-once guarantee. A provider can accept a request before the process records its response. Stable request keys help only where the provider supports them. Inspect provider logs before recovering an ambiguous signature request or an interrupted send.

## Consent, safety, and learning

Unsubscribe classification sets `do_not_contact`. Policy refuses future contact actions; delivery also checks the current persisted flag to block previously queued messages. Human approval cannot override unsafe flags or unsubscribe state.

Replies are wrapped as untrusted content and suspicious replies do not move the deal. Active lessons include their reviewed statement and evidence in outreach context; proposed lessons are not retrieved. Lesson promotion supplies drafting guidance and does not rewrite autonomy rules.

The kill switch gates routing and delivery; inbound events can still be stored and classified. SLA timers survive restarts, become normal events when due, and flag stalled deals. Stage changes replace the prior stage's timer.

## Validation

```powershell
python -m revenue_system.cli validate-packs
python -m pytest -q -m "not browser" -p no:cacheprovider --basetemp .pytest-run-production
python -m pytest -q -m browser -p no:cacheprovider --basetemp .pytest-run-production-browser
```

Browser verification requires Playwright and Microsoft Edge (`pip install -e ".[dev,browser]"`). Tests force isolated databases and test integration modes rather than inheriting the operator's live settings. Coverage includes signed intake through the real worker, competing consumers, retry backoff, crash recovery, stale claims, rollback, consent, operator attribution, and browser review/delivery behavior. Test adapters do not verify live vendor credentials or paid-plan entitlements.

## Release limitations and remaining deployment work

- SQLite is suitable for a bounded deployment sharing one local database. Use PostgreSQL and an appropriate job queue for sustained concurrent writes or multiple application hosts; do not share a SQLite file through an arbitrary network filesystem.
- Native HubSpot V3, Resend, Fireflies V2 and Dropbox Sign verification/mapping is implemented alongside the trusted normalized gateway. Provider account configuration, scopes and actual live acceptance remain deployment responsibilities. Optional CRM write-back updates configured score/stage properties, not full bidirectional synchronization.
- Dropbox Sign uploads the exact reviewed per-deal DOCX after fingerprint/signer validation. Legacy URL-only contracts fail closed. Keep the integration disabled without appropriate production plan access; confirm actual signing and callbacks before commercial use.
- Basic authentication supplies one operator identity, not SSO, role-based authorization, or a multi-user permission system. API documentation endpoints are disabled. Compose restart policies, a reverse-proxy template, non-overwriting backup/restore commands and a heartbeat/queue monitor are supplied; install, configure and verify the actual TLS service, scheduled/off-host backups and alert routing before public exposure.
- Lead research/feature extraction and CRM write-back remain explicit integration work. Imported scoring features must come from an identified evidence source; the application does not independently research external companies.

These boundaries prevent the local hardening tests from being mistaken for a completed vendor-certified production deployment.
