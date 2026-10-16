# Implementation

## Runtime layout

| Package | Responsibility |
|---|---|
| `domain` | Typed actions, deal data, ports, and stage transitions |
| `orchestration` | Durable event processing, lifecycle handlers, timers, outbox delivery |
| `governance` | Autonomy policy, approvals, consent/safety checks, ingress validation |
| `agents` | Typed reasoning tasks, versioned prompts, runner/recording boundaries |
| `skills` | Deterministic scoring, IO validation, rendering, tracking, lessons |
| `segments` | Validated YAML packs for each segment |
| `adapters` | SQLite persistence and live provider boundaries |
| `static` | Operator dashboard assets |
| `tests/support` | Isolated model and provider test doubles |

## Execution

1. CLI import or the signed gateway records an idempotent event.
2. A worker acquires a database lease for the event.
3. The orchestrator invokes the applicable agent and deterministic skills.
4. State changes, action routing, audit records, and event acknowledgement commit together.
5. Routine outreach enters the outbox automatically. Contract drafts, including drafts missing sensitive terms, enter the single human edit/review checkpoint.
6. The worker delivers automatically by default, rechecking safety/consent and immutable human authorization for contracts. Processing-only maintenance uses `--no-deliver`.
7. Provider evidence and an `action.delivered` event are committed with sent status.
8. Delivery and verified signature events advance the deal through guarded stages.

Models run before business writes where possible. Expired claims cannot acknowledge a newer owner's work. Failed work has bounded attempts, a persisted error, and exponential retry timing. SLA timers are stored in the same operational database.

## Boundaries

Native `/providers/*` endpoints verify supported vendor signature schemes and durably enqueue notifications for worker-side fetching/correlation. The `/webhooks/*` interface remains a separately signed normalized contract for trusted gateways. Agents propose content; they never own approvals, pricing authority or external delivery.

`governance/contract_review.py` owns structured human edits, deterministic document regeneration, immutable revision snapshots and stale-edit/approval protection. A contract outbox payload carries authorization for its exact reviewed version; delivery checks it against the persisted approved record. Routine messages cannot carry commercial negotiations. Bounded follow-ups stop after a reply. Pending legacy routine reviews are re-evaluated under current policy without fabricating human approval; actual rejections are never revived.

Brand and publisher packs supply scoring weights, qualification fields, messaging, contract templates, and stage SLAs. Tests exercise both segments through the same lead-to-signature workflow. Non-live integration modes fail explicitly; test doubles are injected by tests only.

## Verification and deployment

See [README](../README.md) for installation and commands, [architecture](architecture.md) for component boundaries, and [production operations](production.md) for settings, recovery, deployment limitations, and release checks.
