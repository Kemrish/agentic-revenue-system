# Demo Script

## Setup

```text
python -m pip install -e ".[dev]"
python -m revenue_system.cli validate-packs
```

The reliable presentation mode is replay mode. It needs no vendor credentials.

```text
python -m revenue_system.cli demo --mode replay
```

The operator dashboard can be started with:

```text
python -m revenue_system.cli ui
```

Open `http://127.0.0.1:8000`. It displays pipeline metrics, deals, pending approvals, outbox work, audit activity, runtime status, and a policy simulator for `AUTO`, `REQUIRE_APPROVAL`, and `DENY`.

## Walkthrough

1. Show the architecture diagram and explain that the orchestrator owns state.
2. Run the brand lead through enrichment and deterministic scoring.
3. Show the tier A score and human-readable reason.
4. Show the outreach proposal and its `REQUIRE_APPROVAL` policy decision.
5. Approve the action and show that it enters the outbox rather than sending directly from the agent.
6. Classify the interested reply.
7. Submit the prompt-injection fixture and show `suspicious=True`; explain that reply triage has no tools.
8. Digest the call transcript and show qualification fields plus a lesson candidate.
9. Generate an IO from structured data, render the reviewed template, and run deterministic validation.
10. Run the publisher lead and show different pack messaging and scoring inputs with unchanged agent code.

## Operational commands

```text
python -m revenue_system.cli approvals list
python -m revenue_system.cli approvals approve <approval-id>
python -m revenue_system.cli approvals reject <approval-id>
python -m revenue_system.cli approvals deliver
python -m revenue_system.cli kill-switch --enabled
python -m revenue_system.cli kill-switch --disabled
python -m revenue_system.cli audit <deal-id>
```

## Live mode

Use `.env` values for credentials and select live integrations independently. Keep the recipient allowlist enabled for mail. Dropbox Sign is configured with `ESIGN_TEST_MODE=true` for accounts without a paid API plan; it creates an API test request without sending a real signer notification. Use `approvals deliver` only after human approval. Real email delivery remains restricted to `MAIL_ALLOWED_RECIPIENTS`.

