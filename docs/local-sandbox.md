# Local integration sandbox (not production)

This optional test-only harness replaces the unavailable public HTTPS endpoint, receiving domain, provider accounts and model calls with isolated local doubles. It exercises the actual native signature verifiers, event database, worker, policy, approvals, outbox and operator UI. It does not verify vendor credentials, DNS, real delivery or paid-plan access. Nothing in this harness is included in the production wheel or Docker image.

## Start

From the source checkout after installing `.[dev,browser]`:

```powershell
.venv\Scripts\python.exe -m tests.support.local_sandbox --port 8010
```

Open `http://127.0.0.1:8010`. The provider label explicitly says **SIMULATED - no real sends**. The harness never reads `.env` and uses a separate ignored `.local-sandbox/sandbox.db`. It binds only to localhost. Never expose this unauthenticated test service through a tunnel or reverse proxy.

Two synthetic contacts enter through signed HubSpot-style notifications. By default the sandbox automatically simulates customer replies, call notifications and completed signatures as their stages permit. All of these are synthetic external events; it never fabricates human contract approval. Re-running resumes its own database and does not reset production data. A second instance refuses an occupied port before it can start another worker.

## Exercise the workflow

1. Open Pipeline/Audit. Watch scoring, automatic first-touch sending, simulated reply classification and call qualification. No outreach approval or Outbox delivery click is required. In a few worker cycles the deals reach proposal.
2. Open Approvals -> Review details for Sandbox Brand. This is the sole normal human checkpoint. Missing prices and dates are intentionally left for you, not filled by the model.
3. Enter a legal entity, budget (for example USD 1,000), start/end dates, one matching line item, and a signer. Keep the sandbox signer `contact@sandbox.invalid` to distinguish it from a real address. Optionally enter additional commercial wording.
4. Click Save changes and regenerate preview. Review revision 2, the exact document text and fingerprint. Download the reviewed DOCX if desired. Unsaved edits disable approval; mismatched amounts or invalid dates are rejected.
5. Click Approve version and resume automation. The worker delivers automatically through the test e-sign provider, then the simulator emits a signed completion callback. Watch proposal -> contracting -> closed_won in Audit. There is no separate human delivery action.
6. Optionally reject the publisher's contract with a reason. The rejected card/history and proposed lesson demonstrate that the system does not ignore or auto-reverse a commercial rejection.

Inspect Outbox for `simulated-mail-` and `simulated-signature-` evidence. No real email/signature is sent. Emergency stop still pauses dispatch. The UI polls every ten seconds; Refresh can show the next worker cycle sooner. Do not enter real sensitive customer data into this unauthenticated local test service.

## Optional manual external-event controls

For a slower presentation, start with `--manual-events` to disable automatic simulation of customer replies/calls/signatures. Routine system delivery remains automatic. These controls represent external customer/provider events, not additional internal approval gates.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/sandbox/hubspot-contact-101/reply
```

After automatic first-touch delivery, the command above emits a signed Resend-style reply and moves the deal to engaged.

Then emit a simulated call:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/sandbox/hubspot-contact-101/call
```

The deal reaches proposal. Complete the human contract editor, save, inspect, and approve. No synthetic price is supplied automatically. The worker dispatches the authorized document without a delivery click.

After it reaches contracting, emit the completed signature:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/sandbox/hubspot-contact-101/signed
```

The receiver verifies the Dropbox-style event hash. The worker requires matching sent-contract evidence and simulated completed-provider state before closed_won.

Inspect the audit trail at every step. Refresh after a worker cycle (approximately one second); the dashboard also polls automatically. The global kill switch pauses delivery. Rejections never silently rewrite policy.

## Repeatable automated acceptance

```powershell
.venv\Scripts\python.exe -m pytest tests/test_local_acceptance.py -v -s -p no:cacheprovider --basetemp .pytest-run-local-acceptance
```

This parametrized test runs the full native-notification lifecycle for both segments, without network calls. Passing it establishes local workflow behavior, **not production certification**. The production preflight continues to reject missing real webhook secrets and domains.
