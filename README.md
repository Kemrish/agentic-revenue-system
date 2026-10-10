# Agentic Revenue System

An agentic revenue lifecycle system for Cool AI. The project automates the path from prospecting through qualification, outreach, reply handling, call intelligence, proposal/IO generation, approval, signature, and handoff.

## Current implementation decision

The system is a governed modular monolith:

- a deterministic orchestrator owns deal state;
- narrowly scoped Claude agents return typed proposals;
- policy, stage transitions, scoring arithmetic, validation, and idempotency are enforced in Python;
- external systems are accessed through ports and adapters;
- SQLite provides local operational durability;
- YAML segment packs provide configuration-only segment extension;
- live, replay, and test runtime modes keep the demo reliable.

See [the architecture document](docs/architecture.md), [the implementation plan](docs/implementation.md), and [the decision record](docs/decisions.md).

The presentation walkthrough is in [the demo script](docs/demo-script.md).

## Planned runtime modes

```text
test   Fake agents and in-memory fakes
replay Recorded agent and integration responses
record Live Claude calls with recordings
live   Configured external adapters
```

## Development

The repository is being built in vertical slices. The first slice will cover brands and publishers, approval enforcement, reply safety, the lesson loop, and IO validation.

