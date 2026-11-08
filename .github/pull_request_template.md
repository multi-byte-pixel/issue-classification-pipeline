## Scope and evidence

- What is implemented versus intentionally deferred?
- Which local and CI checks passed?
- Does this change affect costs, IAM, data handling, or cloud execution?

## Review checklist

- [ ] Synthetic data only; no secrets, plan/state files, or raw customer data.
- [ ] Credential-free tests and evaluation pass.
- [ ] Deliberate contract failure returns exit code 1.
- [ ] Fake-provider metrics are not presented as model-quality evidence.
- [ ] Cloud/deployment changes remain opt-in and reviewed.
