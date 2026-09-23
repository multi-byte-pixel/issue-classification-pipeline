# Starter verification record

The following checks were run locally while preparing the starter PR on September 20, 2026, America/Indianapolis. They establish offline software and static configuration evidence, not cloud deployment evidence.

| Check | Observed result |
|---|---|
| Ruff lint / format | Passed |
| Mypy strict checks | Passed, 11 source modules |
| Pytest | 52 passed, 1 live integration test skipped |
| Coverage | 97% statement coverage across SUT and evaluation modules |
| Seed-42 local evaluation | 50 primary scenarios, 10 unique templates, 9 extra prefix-control calls; all required gates passed |
| Deliberate invalid-output evaluation | Required gates failed; CLI exit 1, verified by `make gate-demo` |
| Terraform 1.12.2 | Format and validate passed; backend disabled, AWS provider 6.65.0 locked |
| Actionlint 1.7.12 | All five workflows passed; optional shellcheck was disabled in this local invocation |
| Linux Lambda packaging | Two builds produced identical SHA-256; packaged handler imported and local health contract passed |

The package SHA-256 at this point was `1b95ca34d562328f8a6130802232d520380ec99382db32b206b755db1dc85178`. Rebuild after any source/dependency change rather than treating this hash as permanent.

The fake provider achieved the expected labels on a deliberately limited fixture; this is not Bedrock model accuracy. Hosted CI evidence is tracked on the PR, while actual deployment, OIDC/IAM behavior, real-model integration, and operational controls remain unverified.
