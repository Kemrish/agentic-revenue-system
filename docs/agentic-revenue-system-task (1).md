# Agentic Revenue System — Design and Demo

## Context

The COOL Company is an AI-powered advertising platform, Cool AI. It covers three stages:

- **Create**: creative automation and dynamic creative optimization
- **Activate**: media activation, franchise and location, publisher experiences, and a supply-side platform
- **Optimize**: measurement, attribution, insights and reporting

It sells to several customer segments:

- **Brands**, including franchise and multi-location brands
- **Agencies**
- **Publishers**
- **Demand partners**

Each segment moves leads from first outreach to a signed IO or contract. Today much of that work is manual.

## Objective

Design an AI agent system that automates the revenue lifecycle end to end, then build and demo a working vertical slice of it.

The lifecycle runs: prospect → enrich → score → outreach → reply handling → meeting → qualify → proposal / IO → signature → handoff.

## Requirements

Your design must cover:

1. **Agents.** Single-responsibility agents coordinated by an orchestrator that owns deal state.
2. **Skills.** Reusable core skills, plus a per-segment config pack (ICP, messaging, scoring weights, templates). Adding a new segment must not require agent code changes.
3. **Triggers.** Event-driven workflows (webhooks, schedules, SLA timers) that are durable and idempotent.
4. **Lead scoring.** Fit, intent and engagement sub-scores, a tier, and a human-readable reason for each score.
5. **Autonomy policy.** Low-risk actions auto-execute. High-risk actions wait for human approval. High-risk includes first touch to top-tier leads, pricing, and IOs/contracts.
6. **Knowledge loop.** Call transcripts (Fireflies) and replies become structured insights and lessons. Those lessons feed later outreach and call briefs, across all segments.
7. **Tracking.** Stage exit criteria, reminders, stall detection, flags and digests.
8. **IO / contract automation.** Generate the document from deal data, validate it, route it for approval, send it for e-signature, and close the deal when it is signed.
9. **Guardrails.** Scoped tools per agent, inbound content treated as untrusted data, an audit log, and a kill switch.

## Constraints

- **System of record:** HubSpot. Mocking it is fine.
- **Agent runtime:** Claude Agent SDK.
- **Language:** Python. The code must be modular and follow SOLID principles.
- **Data:** Mock data is fine, including sample leads, emails, call transcripts and an IO template.

## Deliverables

1. **Design doc** (max 4 pages). Include:
    - an architecture diagram
    - each agent's responsibilities and tools
    - the skills and segment packs
    - the trigger map
    - the data model
    - the autonomy policy
    - a phased rollout
2. **Working vertical slice.** It must run end to end for one segment and show:
    - a new lead being enriched, scored and tiered
    - outreach drafted, with high-risk sends going to an approval queue
    - a reply classified and flagged
    - a call transcript digested into deal fields and a lesson
    - an IO draft generated from the deal data
3. **Second segment demo.** Show a second segment working by adding only a config pack, with no agent code changes.
4. **Repo** containing a README, setup steps and tests for the core skills.

## Demo (30 min)

| Part | Time |
| --- | --- |
| Architecture walkthrough and key trade-offs | 10 min |
| Live run of the vertical slice | 15 min |
| Q&A: scaling, failure modes, evaluation | 5 min |

## Evaluation

| Area | What we look for |
| --- | --- |
| Architecture | Clear agent boundaries, orchestration, durability |
| Extensibility | New customer segment through config only |
| Safety | Autonomy policy enforced in code, not in prompts |
| Learning loop | Lessons captured, retrieved and visibly used |
| Code quality | Modular, SOLID, tested, readable |
| Communication | Clear doc and demo, honest about trade-offs |
