# Release verification record

Date: 2026-10-15. Scope: implementation, local verification and isolated simulated acceptance. This is not a claim of deployed or vendor-certified production readiness.

## Audit findings and disposition

| Original finding | Implemented correction | Evidence |
|---|---|---|
| Nonempty model legal entity/dates could override canonical terms | Every commercial field is reconstructed from explicitly supplied terms and revalidated; absent data stays missing | Contract-integrity and lifecycle regression tests |
| Approved agreement differed from configured signing URL | Per-deal deterministic DOCX, SHA-256 fingerprint, reviewed signer, authenticated download, identical multipart upload | Artifact tampering, upload-argument and approval/delivery tests |
| Missing provider IDs could be reported as successful | Require real provider references; park ambiguous acceptance for reconciliation | Adapter and outbox regression tests |
| Native integration ingress missing | Provider-native verification plus durable notifications and worker-side fetch/correlation | Signature forgery/replay/idempotence tests and both-segment local acceptance |
| Fireflies endpoint incorrect | GraphQL query with variables, transcript identity and error checks | Request contract test |
| No connected CRM write-back | Explicitly enabled property-level score/stage outbox delivery, without acknowledgement loops | Durable provider workflow regression |
| Wheel omitted packs; working-directory coupling | Bundled packs/templates plus resource-based lookup and optional override | Outside-checkout/container package checks |
| Shared environment dependency conflicts | Project-specific .venv and hash-pinned runtime lock | Isolated pip check and runtime dependency audit |
| Development settings and sample database | Separate ignored production profile, generated operator/internal secrets, dedicated empty paused database | Provisioning/preservation tests, read-only preflight |
| Deployment/recovery not supplied | Non-root digest-pinned image, Compose supervision, HTTPS template, online SQLite backup/restore and worker/queue monitor | Image build, isolated container smoke checks and restore tests |

## Verified locally

Autonomy update (2026-10-16): routine first-touch and bounded follow-ups now execute automatically. The human edits sensitive contract fields in a versioned UI and approves the regenerated exact document. New checks cover stale edits/approvals, post-approval signer mutation, missing human authorization, commercial claims in routine emails, follow-up caps/cancellation, legacy routine-gate migration and a continuous-worker E2E with exactly one commercial approval. Production and provider release gates below still apply.

- Automated suite includes actual Edge navigation/review/rejection/delivery behavior, both-segment workflows, consent/guardrails, durable retries/leases, native signature checks, exact artifacts, isolated package paths, backup/restore and readiness checks.
- The native-callback local acceptance test reaches closed_won for brand and publisher using test-only providers and model responses. It makes no external sends.
- Production Docker image builds successfully with hash-checked runtime dependencies. An isolated network-disabled, read-only container validates both bundled segment packs and passes `pip check`.
- Runtime dependency audit reports no known vulnerabilities at the time checked. This is time-specific, not a guarantee of absence.
- Dedicated production database contains no historical sample leads. Backup and restore were exercised to new ignored files, preserving original databases.

Use the actual command output/CI for the current test count; this document intentionally does not freeze a count that changes as coverage grows.

## Not verified / launch gates

The operator currently has no public HTTPS receiver or verified receiving domain. Provider signing secrets and native app configuration are not supplied. Consequently production preflight must remain blocked on those real requirements. Local mocks use `.invalid` addresses and test secrets; they are not copied into production configuration or packaged into runtime artifacts.

Still required: external DNS/TLS validation, native app subscriptions/scopes, credential acceptance, actual email receipt/reply, real transcript retrieval, optional paid-plan signature completion, off-host backup scheduling and alert delivery. Production e-sign remains disabled by default because no paid production API plan is assumed. No real messages, signatures, DNS changes, provider-account changes or public deployment are performed by these verification steps.

The implementation deliberately retains SQLite's single-host boundary, single-operator Basic authentication behind HTTPS, explicit recipient allowlists, at-least-once external execution, and manual reconciliation for ambiguous provider outcomes. See [Deployment](deployment.md) for operating procedures and the live acceptance checklist.
