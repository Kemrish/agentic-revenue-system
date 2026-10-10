# Implementation Plan

## Principles

1. Build the deterministic core before live integrations.
2. Keep all external dependencies behind ports.
3. Make the happy path and safety path visible in the CLI.
4. Prove both segments with the same end-to-end test.
5. Do not allow credentials or generated databases into Git.

## Build phases

### Phase 0: Repository foundation

- package configuration and tooling;
- folder structure;
- settings and dependency container;
- domain models and ports;
- pack schema and registry;
- documentation.

### Phase 1: Durable deterministic core

- SQLite schema and repositories;
- event ingestion and idempotency;
- state machine and guards;
- worker and timers;
- policy engine;
- approvals, outbox, audit, kill switch;
- scoring and IO validation.

### Phase 2: Fixture/replay vertical slice

- fixture adapters in production code;
- fake and replay agent runners;
- brand and publisher packs;
- lead, reply, transcript, and IO fixtures;
- full CLI demo;
- end-to-end test for both segments.

### Phase 3: Claude Agent SDK

- scoped MCP tools;
- versioned prompts;
- asynchronous Claude runner;
- schema validation, retry, recording, and replay hash checks.

### Phase 4: Live adapters

- HubSpot sandbox adapter;
- sandbox email adapter with recipient allowlist;
- Fireflies webhook and fetch adapter;
- e-signature adapter and signed webhook handler.

## Demo acceptance criteria

- A new brand lead is enriched and scored.
- The score includes fit, intent, engagement, tier, and a human-readable reason.
- A top-tier first touch enters approval rather than sending immediately.
- Approval resumes the paused workflow.
- A reply is classified, including a prompt-injection fixture that cannot trigger tools.
- A transcript updates qualification fields and creates a proposed lesson.
- A later draft cites the lesson.
- An IO is generated from typed deal data and passes validation.
- A publisher run uses a different pack without agent code changes.
- Duplicate events do not duplicate work.
- The demo can run in replay mode without network access.

## Commands planned

```text
python -m revenue_system.cli validate-packs
python -m revenue_system.cli ingest lead --file fixtures/leads.json
python -m revenue_system.cli run
python -m revenue_system.cli approvals list
python -m revenue_system.cli approvals approve <approval-id>
python -m revenue_system.cli approvals deliver
python -m revenue_system.cli kill-switch on
python -m revenue_system.cli demo --mode replay
python -m pytest
```

## Live integration boundary

The first live integrations implement only the operations required by the use cases. They do not attempt to wrap entire vendor APIs. Each adapter normalizes vendor payloads into domain objects and translates domain commands back into vendor requests.

