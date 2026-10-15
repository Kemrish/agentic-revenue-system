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
5. Low-risk work enters the outbox; high-risk work awaits a human decision.
6. A delivery process claims permitted work, rechecks safety/consent, and calls the configured provider.
7. Provider evidence and an `action.delivered` event are committed with sent status.
8. Delivery and verified signature events advance the deal through guarded stages.

Models run before business writes where possible. Expired claims cannot acknowledge a newer owner's work. Failed work has bounded attempts, a persisted error, and exponential retry timing. SLA timers are stored in the same operational database.

## Boundaries

The webhook receiver accepts normalized internal contracts rather than arbitrary native provider payloads. External gateways must verify provider-specific signatures and map identifiers before signing the normalized request. Agents propose content; they do not own approvals or delivery.

Brand and publisher packs supply scoring weights, qualification fields, messaging, contract templates, and stage SLAs. Tests exercise both segments through the same lead-to-signature workflow. Non-live integration modes fail explicitly; test doubles are injected by tests only.

## Verification and deployment

See [README](../README.md) for installation and commands, [architecture](architecture.md) for component boundaries, and [production operations](production.md) for settings, recovery, deployment limitations, and release checks.
