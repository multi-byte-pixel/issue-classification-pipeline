# Contributing

Read README.md and docs/status.md before making changes. Work on review branches and keep pull requests small.

- Use synthetic data only. Never commit credentials, Terraform state, plan files, customer text, or generated reports.
- Credential-free CI must remain runnable without AWS or model access.
- Run `uv sync --frozen --extra dev`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src evaluation`, and `uv run pytest` before marking a change ready.
- Keep reported fake-provider results clearly separate from Bedrock or deployed-API results.
- Do not provision AWS, enable schedules, invoke paid inference, or destroy resources without explicit authorization.
- Do not claim production readiness from scaffold validation or a passing synthetic fixture.
- Document deferred controls, metric denominators, and failure modes.
