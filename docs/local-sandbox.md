# Local integration sandbox (not production)

This optional test-only harness replaces the unavailable public HTTPS endpoint, receiving domain, provider accounts and model calls with isolated local doubles. It exercises the actual native signature verifiers, event database, worker, policy, approvals, outbox and operator UI. It does not verify vendor credentials, DNS, real delivery or paid-plan access. Nothing in this harness is included in the production wheel or Docker image.

## Start

From the source checkout after installing `.[dev,browser]`:

```powershell
.venv\Scripts\python.exe -m tests.support.local_sandbox --port 8010
```

Open `http://127.0.0.1:8010`. The provider label explicitly says **SIMULATED - no real sends**. The harness never reads `.env` and uses a separate ignored `.local-sandbox/sandbox.db`. It binds only to localhost. Never expose this unauthenticated test service through a tunnel or reverse proxy.

Two synthetic contacts enter through signed HubSpot-style notifications. They are processed into the brand and publisher pipelines. Re-running the harness resumes its own database; it never resets production data.

## Exercise the workflow

1. Open Approvals. Review the first-touch subject, body, contact and policy reason. Approve the brand contact; optionally reject the publisher contact with a reason to inspect the rejection count and proposed lesson.
2. Open Outbox, review the delivery batch, then deliver. The provider ID begins with `simulated-mail-`; no email is sent.
3. Emit a simulated reply from another PowerShell window:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/sandbox/hubspot-contact-101/reply
```

The receiver verifies a Resend-style signed notification; the worker fetches the synthetic email, correlates its opaque reply address and moves the deal to engaged.

4. Emit a simulated call:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8010/sandbox/hubspot-contact-101/call
```

This test scenario supplies explicit commercial terms, verifies a Fireflies V2-style notification and fetches a synthetic transcript. The deal reaches proposal. Review the contract's exact text, signer and SHA-256 fingerprint; download its DOCX. Approve and deliver it through the simulated e-sign adapter.

5. Emit the completed signature:

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
