# Deployment, native integrations and release acceptance

## Release boundary

There are three distinct claims: automated/local correctness, configured deployment readiness, and successful live provider acceptance. None implies the others. `production preflight` checks local configuration, packaged packs and database integrity/sample data. It never validates credentials, sends mail, changes CRM records or creates signature requests. Sandbox callbacks do not turn missing production secrets into valid configuration.

The application is a bounded single-host SQLite deployment with one operator identity. It is not a multi-tenant SaaS, a distributed job system, SSO/RBAC implementation, or independently certified compliance product.

## Isolated installation and configuration

Use Python 3.14 for the supplied hashed lock file. Python >=3.12 is supported by the source dependency declarations, but other Python/platform combinations must be validated separately. Runtime dependencies are in `requirements.lock`; test/build tools are not runtime requirements. Regenerate the lock intentionally with pip-tools and rerun the dependency audit and cross-platform CI. OpenRouter requires no optional Claude SDK; install `.[live]` and revalidate that environment if selecting Claude.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m revenue_system.cli production init
$env:ARS_ENV_FILE=".env.production"
.venv\Scripts\python.exe -m revenue_system.cli production preflight
```

`production init` refuses existing destination files. It copies existing credentials into a separate ignored profile, generates a strong dashboard password, an internal gateway secret and a mail-thread secret, and creates `data/production.db` with no leads and the kill switch enabled. It disables external side effects and production e-sign by default. The legacy database is preserved, not silently migrated or erased. Review and protect the generated file privately; Windows operators should restrict its ACL to the service account. Do not paste credentials into logs or tickets.

`ARS_ENV_FILE` is selected when the Settings module is imported: set it before starting a new process, in every terminal/service. Environment variables override file values. For remote deployment use an appropriate secret store; do not bake `.env` into images. Packs can be overridden with `PACKS_ROOT`, otherwise the wheel supplies both packs and templates. Use an absolute database path consistently across native host processes.

## Native webhook endpoints

Set `PUBLIC_WEBHOOK_URL` to the exact externally visible receiver base URL, such as `https://hooks.your-company.example`. Do not add `/providers/hubspot` to the base. Host/proxy headers cannot select the canonical signature URL.

| Provider endpoint | Verification | Accepted event | Worker responsibility |
|---|---|---|---|
| `/providers/hubspot` | V3 HMAC-SHA256/base64, canonical URI and timestamp within five minutes | `contact.creation` in a bounded batch | Fetch contact, validate mapped lead data, score and propose outreach |
| `/providers/resend` | Svix message ID/timestamp/body HMAC; five-minute tolerance | `email.received` | Retrieve plain-text body and correlate opaque reply address plus expected sender |
| `/providers/fireflies` | Body HMAC-SHA256 and fresh V2 delivery timestamp | `meeting.transcribed` | Resolve deal link, retrieve transcript through GraphQL, run call intelligence |
| `/providers/dropbox-sign` | Multipart/urlencoded JSON event hash using the API key | `signature_request_all_signed` | Match persisted sent request, query provider for completed state, then close the deal |

Receivers authenticate and persist; they do not run agents or fetch provider resources. Stable provider event identities deduplicate redelivery. Provider fetch failures consume the worker's bounded retry budget and then become dead letters. Unsupported event types are acknowledged without applying business transitions. Configure only supported subscriptions. Request bodies are bounded. Unconfigured verifier secrets fail closed.

`/webhooks/{source}` remains the normalized internal HMAC interface for a trusted gateway. Do not register that internal endpoint directly with a native provider. An internal signature event requires both `deal_id` and `provider_id`; the trusted gateway is responsible for native completion verification.

### HubSpot

Supply `HUBSPOT_ACCESS_TOKEN` for contact read access and `HUBSPOT_CLIENT_SECRET` from the app that signs V3 callbacks. They are not interchangeable. This receiver deliberately does not accept legacy V1/V2 signatures. App subscriptions/plan capabilities must support the configured V3 contract. A numeric contact can also be queued explicitly with `import-contact`.

Create/populate the mapped properties:

| Setting | Default | Use |
|---|---|---|
| `HUBSPOT_SEGMENT_PROPERTY` | `ars_segment` | Exact configured pack key: brand or publisher |
| `HUBSPOT_FIT_PROPERTY` | `ars_fit` | Evidence-backed 0–100 fit input |
| `HUBSPOT_INTENT_PROPERTY` | `ars_intent` | Evidence-backed 0–100 intent input |
| `HUBSPOT_SCORE_PROPERTY` | `ars_score` | Optional numeric output |
| `HUBSPOT_STAGE_PROPERTY` | `ars_stage` | Optional stage output supporting application stage names |

Standard contact fields `company`, `firstname`, `lastname`, `email` provide identity. Missing company/contact/segment fields fail validation; missing numeric evidence defaults to zero, not a model-invented high score. CRM source IDs are retained. This system does not independently research the evidence.

`CRM_SYNC_ENABLED=true` plus live HubSpot and `LIVE_SIDE_EFFECTS_ENABLED=true` enables durable property-level score/stage write-back. Give the token the required write scope and create the output properties first. It does not overwrite the complete contact or alter HubSpot pipeline stage IDs. CRM acknowledgements cannot recursively enqueue another synchronization. The kill switch pauses CRM writes too. Imported JSON leads without a HubSpot contact ID do not create CRM updates.

### Resend

Configure a verified outbound sender, permitted destinations, a receiving domain/MX records, and an `email.received` webhook. Set `RESEND_WEBHOOK_SECRET` to that endpoint's `whsec_...` signing secret, not the sending API key. The API key must permit received-email retrieval, not only sending.

`MAIL_REPLY_DOMAIN` is the receiving domain, without scheme or `@`. Outbound messages include `reply+<opaque-token>@domain` as Reply-To. `MAIL_THREAD_SECRET` creates the token from the persisted outbox action ID. Replies must target that alias and match the reviewed outbound recipient address. Do not rotate the thread secret while old threads still need correlation without planning a migration. Sender-address matching is correlation, not a substitute for provider spam/SPF/DKIM controls. Keep the receiving provider's anti-spoofing controls enabled.

HTML-only, unmatched or ambiguous replies are not silently attached to an arbitrary deal; they become failures for manual review. Historical messages sent before opaque reply aliases were configured do not gain automatic correlation retroactively.

### Fireflies

Create a V2 webhook subscribed to `meeting.transcribed`, set its signing secret and provide `FIREFLIES_WEBHOOK_SECRET`. Retrieval uses `POST https://api.fireflies.ai/graphql` with an ID variable and sentences. GraphQL errors, unavailable transcripts and empty text are failures, not successful empty calls.

Use the local deal ID as `client_reference_id` on uploads, or register an existing transcript explicitly:

```powershell
python -m revenue_system.cli deals link-transcript <deal-id> <transcript-id>
python -m revenue_system.cli deals terms <deal-id> --file commercial-terms.json
```

Commercial terms must explicitly contain `legal_entity`, positive `budget`, ISO `start_date`/`end_date`, and positive line-item amounts summing to the budget. They are validated and audited before use; the LLM cannot replace these values. Set terms before the transcript is processed. Existing proposals/contracts cannot be changed by this command. Reprocessed transcript notifications require manual review and cannot silently replace previously proposed commercial actions.

### Dropbox Sign

No paid API plan is required to use the rest of the system. Keep `ESIGN_MODE=test` to disable production signature sending. When enabled for real commercial use, set `ESIGN_MODE=live`, `ESIGN_TEST_MODE=false`, verified API credentials, `ESIGN_ALLOWED_RECIPIENTS`, and confirmed plan access.

The generated agreement is stored as reproducible DOCX bytes alongside the reviewed text, SHA-256 fingerprint, and per-deal signer email/name. Both approval and delivery validate it. The authenticated UI can download those bytes; the adapter uploads exactly them as multipart `files[0]`. A provider may append its signature page. Remote document URLs and global signer settings cannot replace reviewed content. Legacy queued contracts without artifact evidence fail closed and must be regenerated/reviewed.

A missing provider delivery ID is never replaced with a local idempotency key. Ambiguous e-sign transport/server responses are parked as failed for reconciliation, because this API is not assumed to support exactly-once idempotency. A callback's time/type hash alone does not cover its entire signature-request body; the worker additionally looks up the sent reference and verifies completion through the authenticated provider API.

## Process supervision and HTTPS

`deploy/Dockerfile` builds a wheel and installs hash-pinned runtime dependencies into a non-root image. The Python base is digest-pinned. Test doubles, sandbox code, credentials and databases are excluded. OpenRouter is the default deployment path; this image does not include the optional Claude SDK.

`deploy/compose.yaml` runs UI, receiver and worker with restart policies, shared local SQLite storage, read-only root filesystems and bounded logs. Ports are published only on loopback. A fresh named data volume is distinct from the host's `data/production.db`. Initialize/check it before accepting events. Never copy a live SQLite file by ordinary filesystem copy.

```powershell
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml run --rm ui python -m revenue_system.cli health
docker compose -f deploy/compose.yaml run --rm ui python -m revenue_system.cli kill-switch --enabled
docker compose -f deploy/compose.yaml run --rm ui python -m revenue_system.cli production preflight
docker compose -f deploy/compose.yaml up -d
```

All services must use the same production profile. Do not use `docker compose config` without `--quiet` in shared logs: rendered configuration contains secrets. Review effective variables privately.

`deploy/Caddyfile` is a host reverse-proxy template. Replace both hostnames, configure DNS, install/run Caddy under the host's service manager, and verify actual TLS issuance and renewal. UI and webhook services are loopback-only behind that proxy. Only webhook ingress routes are exposed on the hook hostname; health and API documentation are not public provider routes. This file is not evidence of an already deployed HTTPS service.

## Backups, restore and alerting

```powershell
python -m revenue_system.cli production backup --destination backups/production-2026-10-15.db
python -m revenue_system.cli production restore --source backups/production-2026-10-15.db --destination data/restored-production.db
python -m revenue_system.cli production monitor --max-worker-age 600
```

Backup and restore use the SQLite online backup API, integrity-check the result, and refuse existing targets. Protect backups like production data. To recover, stop all services, restore to a new path, select it explicitly, verify integrity/queues, and resume with delivery paused. Inspect ambiguous provider acceptance before enabling delivery or retrying failed sends. Never automatically replay an unreviewed signature request after restore.

Schedule daily backups with Windows Task Scheduler or the host scheduler, copy encrypted backups off-host, define retention/RPO/RTO, and perform restore drills. The repository does not register host scheduled tasks or create remote backup accounts. Container operators can invoke the same commands with `docker compose run --rm ui ...` and `/backups/<unique-name>.db`; copy snapshots off the named volume.

The continuous worker updates a heartbeat. `production monitor` exits nonzero for stale/missing worker heartbeat, dead events or failed deliveries. Connect it to your alerting scheduler and escalation destination; this does not itself send alerts. `/healthz` is liveness, not proof of worker progress or vendor health. Container restart policies do not automatically restart a merely unhealthy but still-running process. Monitor disk space, overdue approvals, queue age and backup freshness externally.

## Live acceptance before enabling delivery

1. Use the dedicated empty production database and real secrets/domains, not sandbox values. Run local preflight, dependency checks and the automated suite.
2. Verify HTTPS externally and check that unsigned/tampered callbacks are rejected. Register only the native callback URLs documented above.
3. Import one owned/authorized CRM contact with evidence-backed scoring fields. Confirm its score, proposal, review details and audit trail.
4. Review the recipient/message, permit only your controlled destination, then explicitly arm side effects and clear the kill switch. Verify provider ID and actual inbox receipt.
5. Reply through the verified receiving domain and confirm native webhook intake, correlation and engagement.
6. Supply commercial terms and link a real Fireflies transcript. Confirm the exact contract fields, signer, DOCX and fingerprint. If no production e-sign plan exists, stop that path at reviewed proposal; do not mark it signed.
7. If e-sign is enabled, sign the actual document and verify remote completed state plus the matching callback before closed_won.
8. Exercise denial/unsubscribe, rejection with a reason, emergency pause, provider failure/retry, and restore/restart recovery. Capture evidence without exposing customer data or secrets.

## Primary provider references

- [HubSpot request validation](https://developers.hubspot.com/docs/apps/legacy-apps/authentication/validating-requests)
- [Resend webhook verification](https://resend.com/docs/webhooks/verify-webhooks-requests)
- [Fireflies V2 webhook contract](https://docs.fireflies.ai/graphql-api/webhooks-v2)
- [Dropbox Sign send API](https://developers.hellosign.com/api/signature-request/send)
- [Dropbox Sign callback walkthrough](https://developers.hellosign.com/docs/guides/events-and-callbacks/walkthrough)
