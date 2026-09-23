.PHONY: setup lint test evaluate-local gate-demo terraform-fmt terraform-validate package
setup:
	uv sync --frozen --extra dev
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy src evaluation
test:
	uv run pytest --cov=event_classifier --cov=evaluation --junitxml=artifacts/tests.xml
evaluate-local:
	uv run python -m evaluation.cli run --seed 42 --scenario-count 50 --output-dir artifacts/evaluation
gate-demo:
	@uv run python -m evaluation.cli run --seed 42 --scenario-count 16 --inject-failure --output-dir artifacts/gate-demo; code=$$?; test $$code -eq 1
terraform-fmt:
	terraform fmt -check -recursive infra
terraform-validate:
	terraform -chdir=infra/environments/dev init -backend=false
	terraform -chdir=infra/environments/dev validate
package:
	uv run python scripts/package_lambda.py
