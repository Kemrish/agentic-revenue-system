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

