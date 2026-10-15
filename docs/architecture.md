# Agentic Revenue System Architecture

## 1. Purpose

This document defines the architecture for an AI-assisted revenue lifecycle system for Cool AI. It is the source of truth for component boundaries, data ownership, safety guarantees, and runtime behavior.

The system covers:

```text
prospect → enrich → score → outreach → reply → meeting → qualify
→ proposal/IO → approval → signature → handoff
```

The initial implementation is a focused vertical slice. It is intentionally a modular monolith rather than a collection of distributed services.

## 2. Architectural decision

We chose a governed pipeline:

```text
Trigger → durable event → orchestrator → agent or skill
        → typed proposal → policy gate → outbox or approval
```

The orchestrator owns deal state and stage transitions. Agents interpret unstructured information and propose structured results. Python code owns guarantees.

## 3. System diagram

```text
HubSpot / mail / Fireflies / e-sign webhooks
                    │
                    ▼
             FastAPI webhook layer
       verify → normalize → idempotent event
                    │
                    ▼
             SQLite operational store
     events · deals · approvals · timers · outbox
                    │
                    ▼
                 Worker
                    │
                    ▼
              Deal orchestrator
          owns state and valid transitions
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Deterministic skills       Claude agents
  scoring, policy,            research, outreach,
  validation, tracking       triage, calls, deal desk
        └───────────┬───────────┘
                    ▼
              Typed proposal
                    │
                    ▼
              Policy engine
          AUTO / APPROVAL / DENY
             │       │       │
             ▼       ▼       ▼
          outbox  approvals audit
                    │
                    ▼
                Adapters
```

## 4. Component responsibilities

### Domain

Defines entities, value types, lifecycle stages, events, and ports. It must not depend on vendor SDKs, FastAPI, or Claude.

### Orchestration

Consumes events, invokes the correct skill or agent, applies validated results, creates timers and approvals, and emits outbox work. It does not contain vendor-specific code.

### Agents

Perform judgment-heavy tasks:

- Research: enrichment and evidence extraction
- Outreach: first-touch and follow-up drafts
- Reply triage: reply classification and safety flags
- Call intelligence: transcript digest and lesson candidates
- Deal desk: structured IO data
- Pipeline analyst: stalls and pipeline digests

Agents cannot directly send, sign, price, or move stages.

### Skills

Deterministic, reusable business capabilities: scoring, lesson curation/retrieval, templating, IO validation, and SLA tracking.

### Governance

Centralizes policy decisions, approvals, kill switches, content-safety checks, rate limits, and audit records.

### Adapters

Implement ports for HubSpot, mail, Fireflies, e-signature, Claude, and persistence. The application depends on ports, never concrete adapters.

## 5. Lifecycle and state ownership

The initial shared lifecycle is:

```text
NEW → ENRICHED → SCORED → OUTREACH → ENGAGED → MEETING
→ QUALIFIED → PROPOSAL → CONTRACTING → CLOSED_WON
                                      └→ CLOSED_LOST
```

The state machine owns guards and exit criteria. Agents return facts or proposals; only the orchestrator may transition a deal.

Segment packs may vary qualification fields, templates, scoring, and SLAs. They do not contain Python branches and do not define a separate agent hierarchy.

## 6. Durability and idempotency

Every inbound trigger becomes an event with a unique source idempotency key. Events, state changes, timers, approvals, outbox rows, and processing status are committed transactionally.

External side effects use an outbox. The outbox has a unique action key, retries failed delivery, and marks delivery only after the adapter succeeds. Provider-level idempotency is used when supported but is not assumed.

Timers are database rows. A due timer becomes a normal event, so webhooks and SLA work use the same processing path.

## 7. Data ownership

HubSpot owns CRM objects visible to revenue users: companies, contacts, and deals. The operational database owns events, timers, approvals, outbox work, scores, drafts, lessons, digests, and audit history.

HubSpot updates are property-level and record the source. Human edits win over agent edits; the resulting webhook is logged and exit criteria are rechecked.

## 8. Segment packs

Each segment is a validated folder under `packs/`. A pack defines ICP data, personas, scoring rules and thresholds, qualification fields, messaging, templates, SLA durations, contract settings, and autonomy tightening rules.

Adding a segment means adding YAML and templates, plus fixtures/tests. Existing agent and orchestrator code must not change.

## 9. Agent safety

Each agent receives only its own tools through an in-process MCP server. Reply triage and transcript processing read untrusted content and receive no side-effecting tools. Inbound content is delimited and labeled as data.

The policy engine is the authoritative safety boundary. SDK tool restrictions are defense in depth, not the only control.

## 10. Runtime modes

The container enables integrations independently through explicit live modes. Disabled integrations refuse execution; tests inject their own doubles under `tests/support`. Recording/replay primitives support controlled evaluation of actual saved agent responses; the runtime contains no canned response dataset.

## 11. Scaling path

The first version uses one worker and SQLite. The ports allow migration to PostgreSQL and multiple workers. Temporal is a later runtime option if workflow volume, compensation, or timer complexity exceeds the database worker model. Agents, packs, policy, and audit design remain unchanged.

