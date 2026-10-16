# Architecture Decisions and Trade-offs

## Decision 001: Governed pipeline

Chosen over an autonomous supervisor, generalist agent, and event choreography.

Reason: the brief requires an orchestrator that owns state and autonomy enforced in code. A state machine gives deterministic transitions while agents handle language judgment.

Accepted trade-off: a new lifecycle path requires code. The initial lifecycle is fixed and small; segment variation belongs in packs.

## Decision 002: Modular monolith first

Chosen over microservices.

Reason: one codebase is easier to operate and test. Internal ports and module boundaries preserve a future service split.

Accepted trade-off: less independent scaling. This is appropriate for the expected low-volume, long-running revenue workflow.

## Decision 003: SQLite operational store

Chosen for the first implementation; PostgreSQL is the production target.

Reason: durable local state, approvals, timers, outbox, and audit without external setup.

Accepted trade-off: limited concurrency. Repository and event-store ports preserve the migration path.

## Decision 004: Explicit integration activation

Claude and integration adapters are implemented behind ports. Inactive integrations refuse execution explicitly. Provider and model doubles are injected by automated tests and live under `tests/support`.

Reason: an unconfigured provider must never appear to have delivered an action successfully. Tests remain isolated without shipping synthetic runtime behavior.

## Decision 005: Typed proposals, not agent side effects

Chosen over giving agents broad tools.

Reason: agents can read untrusted text and make mistakes. A typed proposal is validated, audited, and authorized by code before any external action.

## Decision 006: Rule-based scoring with model feature extraction

The model extracts evidence from unstructured inputs; pack-defined deterministic rules calculate fit, intent, engagement, tier, and explanation.

Reason: transparent scoring is required and there is no initial win/loss dataset for a trained model.

## Decision 007: Structured lessons

Lessons are evidence-backed records with scope, tags, status, and usage outcomes. New lessons begin as proposed and drafts must report `lessons_used`.

Reason: this makes the knowledge loop visible and prevents raw untrusted text from becoming an instruction.

## Decision 008: Template-based documents

Agents propose typed IO data. Jinja templates render the document and deterministic validators check it. Human approval is always required before signature.

Reason: the model must not invent prices, terms, or legal language.

## Decision 009: Repository and integration ports

All external systems and persistence stores are protocols. Concrete adapters are selected in `container.py`.

Reason: dependency inversion is a core quality criterion and allows live, replay, and test implementations.

## Decision 010: No premature infrastructure

We defer Temporal, Kafka, Redis, microservices, vector databases, and a full frontend.

Reason: the current workload does not justify their operational cost. Introduce them when measured throughput and availability requirements require them.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Duplicate webhook | Unique event idempotency key |
| Worker crash | Transactional event processing and retry |
| Duplicate email or envelope | Unique outbox action key |
| Prompt injection | Untrusted-data wrapping, no tools, flag, approval escalation |
| Invalid model output | Pydantic validation, one retry, human task |
| Human/agent conflict | Property-level CRM writes and source provenance |
| Bad segment pack | Startup validation and pack contract tests |
| Runaway sends | Policy caps and kill switch |
| Vendor outage | Persistent retry backoff, bounded attempts, operator recovery |

## Production-hardening decisions (2026-10-15)

### Canonical commercial inputs, not model authority

All commercial fields are reconstructed from explicit upstream/operator terms, including legal entity and dates even when a model returned nonempty alternatives. Missing terms remain missing; schema/arithmetic validation is still required. This sacrifices model freedom to fill gaps in exchange for preventing invented legal commitments. Corrections to a proposed contract require a new review rather than editing an approved artifact.

### Reproducible DOCX bound to approval

Persist reviewed text, deterministic DOCX bytes, fingerprint and per-deal signer with the action. Revalidate on approval, download and delivery; upload the exact bytes. DOCX preserves Unicode with standard-library generation, avoids a PDF renderer/font/deployment dependency, and removes remote shared-file mutability. Trade-off: basic layout and plain text/Markdown presentation rather than sophisticated legal-document typesetting. Dropbox may append a signature page. Legacy URL-only actions fail closed rather than silently acquiring a different agreement or global signer.

### Native receivers plus deferred provider resolution

Provider-specific signature verification happens before durable enqueueing. Provider fetches, mapping and agent work happen in the leased worker, not inside callback response time. Keep the normalized internal gateway for controlled integrations; do not pretend its HMAC contract is a native vendor webhook. This adds small provider-specific modules but preserves one persistence/retry model. Unsupported legacy signatures and ambiguous mappings are rejected instead of guessed.

### Conservative reply, transcript and signature correlation

Reply-To carries an opaque per-message HMAC alias, and received mail must match the reviewed recipient address. Transcripts require a deal reference or explicit unique link. Signature callbacks must match sent evidence and authenticated remote completion. Ambiguous replies/HTML-only messages and reprocessed transcripts require manual review. These limits reduce automatic coverage but prevent silently attaching external content or renewed commercial actions to the wrong deal.

### CRM write-back is bounded and opt-in

Only configured score/stage properties on the retained HubSpot contact are synchronized through the outbox. Do not claim bidirectional synchronization or overwrite the full CRM object. Retries are safe for property assignment; delivery acknowledgements do not create sync loops. Requires explicit configuration, provider write permissions and the global external-write opt-in. This limits sophistication but keeps the integration understandable and recoverable.

### Ambiguous acceptance is not automatic success or a blind retry

Require actual provider references. Stable local action keys are not proof of provider idempotency. Park ambiguous e-sign transport/server responses for reconciliation; never assume a fabricated reference proves delivery. Exactly-once external execution is not guaranteed across a process crash. Operators must inspect vendor history before retry/restore replay.

### Portable package and isolated dependencies

Ship packs/templates as wheel resources; an explicit PACKS_ROOT may override them. Do not rely on the launch directory. Use a project venv and hash-pinned Python 3.14 runtime lock; the container base is digest-pinned. Source supports additional Python versions only after corresponding validation. This adds an intentional dependency-update process in return for reproducible releases and avoiding global-package conflicts.

### Preserve historical data; provision a separate production profile

Initialization refuses existing config/database targets. Generate operator/internal secrets, create an empty paused database and disable external side effects/e-sign initially. Do not delete or silently migrate the old sample database. Operators must select the production profile explicitly and supply real deployment settings. It is less automatic than reusing a working local .env, but makes the production boundary auditable and reversible.

### Test-only local simulation, never a production fallback

At the operator's request, unavailable domains and callbacks can be simulated in `tests/support/local_sandbox.py`. It binds only to loopback, uses isolated data and test doubles, and is excluded from wheels/container builds. Production preflight stays red for missing real prerequisites. This permits useful local demonstrations without disguising mock acceptance as real provider verification.

### Bounded single-host operations

Provide a non-root container, Compose restart policies, HTTPS proxy template, non-overwriting SQLite online snapshots and a worker/queue monitor. Do not add distributed infrastructure without a workload requirement. Trade-offs remain single-host availability, one configured operator and external responsibility for DNS/TLS, alert delivery, backup schedules and off-host retention. Backups and deployment templates are not evidence that these operational services have actually been installed.

