# Threat model

This is a design-review aid, not a security attestation. Controls need validation in the selected account, model, region, and operational context.

| Risk | Implemented boundary | Remaining work |
|---|---|---|
| PR code obtains cloud access | No PR OIDC or credentials | Environment protections and account trust review |
| Excessive IAM | No generated admin policy; runtime boundary required | Deployment policy and permission simulation |
| Prompt injection | Turns serialized as data; strict output schema/allowlist | Broader adversarial set and real-model tests |
| Sensitive logs | Raw input/output omitted; marker-absence test | Retention, access, error-path review |
| API/cost abuse | IAM auth, throttle, concurrency cap, cloud opt-in | Budgets, alerts, quotas, incident process |
| Provider failure | Bounded retries/timeouts; 503 plus review response | Live timeout/load/recovery tests |
| Supply chain | Lockfile, pinned actions, provenance hashes | SBOM, signing, scans, immutable plan promotion |
| State leakage | Secure backend required; state/plans ignored, not uploaded | Policies, lock access, audit, recovery |
| Accidental deletion | Teardown always refuses; bucket not force-deleted | Isolated ephemeral state and cleanup tests |
| Signed-header leakage | API runner refuses redirects | Configuration host allowlist |
| Overstated readiness | Status separates offline from cloud evidence | Refresh evidence after real deployment |

Authentication is not a guarantee that prompts stay within a specific network boundary. No VPC endpoint or data-residency assurance is implemented here.
