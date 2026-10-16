# Automatic execution with one human commercial checkpoint

Decision date: 2026-10-16. Requested scope: automate the existing revenue workflow while reserving sensitive contract decisions, especially pricing, for the operator. This changes workflow autonomy, not provider credentials, consent requirements or the deployment release gates.

## Responsibility split

| Work | Owner |
|---|---|
| Lead intake, deterministic scoring, drafting non-commercial outreach | System/agents |
| Routine first touch for every tier | Automatic policy and outbox delivery |
| Unanswered-message follow-ups | Agent drafts; system enforces stage/consent and pack cap |
| Reply classification, transcript analysis, qualification and tracking | System/agents, driven by real external events |
| Prices, budget, dates, legal entity, line items, signer and additional terms | Human edits/reviews the contract |
| Final contract authority | Human approves the exact revision and fingerprint |
| Sending the approved document, CRM write-back, signature tracking and state progression | Automatic system execution |
| Safety, unsubscribe, unsafe-content denial, recipient allowlists and kill switch | Deterministic controls; never an agent override |

The customer still needs to reply, attend a call and sign in a real deployment. Automation cannot invent those external events or sign on the customer's behalf. Calendar booking, independent lead discovery, full CRM synchronization and arbitrary negotiation are not newly added capabilities.

## Normal flow

```text
Lead -> score -> automatic routine outreach -> reply/call processing
    -> contract draft, with sensitive values supplied or explicitly missing
    -> HUMAN: edit terms -> save/regenerate -> inspect -> approve exact version
    -> automatic signature request -> verified customer completion -> closed_won
```

No human approves routine messages or clicks Outbox delivery after contract approval. Start `python -m revenue_system.cli worker`; delivery is enabled by default. `worker --once` also dispatches permitted work. Explicitly use `worker --no-deliver` or `worker --once --no-deliver` for processing-only maintenance. A separate running worker is still necessary when using the production dashboard; the UI does not impersonate a background service.

Actual external writes still require live integration modes, enabled side effects, permitted recipients and a released kill switch. An unconfigured/disabled e-sign provider cannot produce a genuine completed contract. No credentials or production data are automatically armed by this change.

## Contract editor

Open Approvals -> Review details. Edit legal entity, USD budget, dates, line-item names/amounts, signer name/email, and additional legal/commercial wording. Prices are never chosen to satisfy a missing-field validator. Supplied upstream values are proposals until the human approves them.

Save changes and regenerate preview. The system validates dates and money, renders the segment-specific template, appends the human-supplied additional wording, generates deterministic DOCX bytes, and assigns a new revision/fingerprint. This is deterministic rendering, not an agent rewrite of approved commercial terms. The editor does not offer unrestricted replacement of the canonical template body; sensitive fields and additional terms are editable while structured values stay consistent with the generated document.

Inspect the complete preview or download the exact DOCX. Unsaved edits disable approval. Approve version and resume automation authorizes only the currently reviewed snapshot. It does not cause an agent to alter prices again. The worker uploads the exact authorized bytes and signer without another operator delivery step.

Every saved edit preserves the previous payload in `contract_revisions`, records the operator in audit, and invalidates older review tokens. Concurrent stale edits/approvals are refused. Decided contracts cannot be edited in place. Rejection requires a reason, proposes a lesson, and does not auto-resubmit the same contract.

CLI alternatives:

```powershell
python -m revenue_system.cli approvals edit-contract <approval-id> --file contract-edit.json
python -m revenue_system.cli approvals approve <approval-id> --revision <number> --fingerprint <sha256>
```

The edit JSON uses `expected_revision`, `legal_entity`, `budget`, `start_date`, `end_date`, `line_items`, `signer_email`, `signer_name` and optional `additional_terms`. The authenticated dashboard is the recommended human interface.

## Routine message and follow-up limits

The versioned outreach prompt forbids pricing, budgets, discounts, payment/legal commitments, percentages and guarantees. A conservative deterministic text check also refuses these in both policy and delivery. This is defense in depth, not a guarantee that a keyword rule understands every possible commercial claim. Routine messages must remain factual discovery outreach; negotiation belongs in the human contract checkpoint.

Each pack's `follow_up_limit` defaults to two (configurable zero to five). Stage SLA timers trigger follow-ups only for unanswered outreach. Follow-ups stop after any classified reply, consent/safety flags, leaving outreach, or exhausting the cap. Queued follow-ups recheck the latest deal before sending and cancel when no longer relevant. Delivery acknowledgements do not rewind stages or bypass limits. Timers, attempts, queues and follow-up identities persist across restarts.

## Upgrade behavior and exceptional intervention

Pending legacy routine approval gates are re-evaluated: safe permitted messages are marked `auto_released` and queued once; denied ones are recorded as denied. This never fabricates a human approval, revives a rejected request, duplicates an existing outbox action or changes a pending commercial review. Existing rejection counts/history remain intact.

Emergency pauses, quarantined content, unknown recipients, missing qualifications, ambiguous provider acceptance and exhausted retries still stop execution. These are exceptions requiring investigation or corrected inputs, not routine approval steps removed by this policy. Removing those controls would turn workflow automation into unsafe guessing.

The local sandbox can simulate customer replies/calls/signatures automatically, but it never simulates the human's contract authority. See [local sandbox](local-sandbox.md) for the UI walkthrough and explicit simulation boundary.
