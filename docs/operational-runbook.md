# Operational runbook

Local commands need no AWS access. Cloud steps are for a future explicitly authorized deployment and may incur charges.

## Credential-free verification

```bash
make setup lint test evaluate-local gate-demo
make package
terraform fmt -check -recursive infra
terraform -chdir=infra/environments/dev init -backend=false -lockfile=readonly
terraform -chdir=infra/environments/dev validate
```

Packaging exports locked dependencies, selects Linux x86-64/Python 3.12 wheels, and creates a sorted zip with fixed metadata. Build twice and compare `sha256sum dist/lambda.zip` when changing packaging.

## Before cloud execution

Complete the [bootstrap review](../infra/environments/bootstrap/README.md). Confirm model access/Converse support, region, inference resource ARNs, IAM boundaries, state storage, quotas, and costs.

Configure repository variable `CLOUD_ENABLED` only after approval. Set these non-secret variables in the protected `dev` environment; identity comes from OIDC, not stored access keys:

| Variable | Purpose |
|---|---|
| `AWS_REGION` | Reviewed region |
| `AWS_DEPLOY_ROLE_ARN` | Restricted deployment role |
| `AWS_EVAL_ROLE_ARN` | Separate API evaluation role |
| `TF_STATE_BUCKET` | Existing secure state bucket |
| `DEV_TFVARS_JSON` | Dev variable JSON; no secrets |
| `DEV_API_URL` | Authenticated API URL from deployment |

Do not let `dev` accept arbitrary branches. Main-only workflow checks supplement environment restrictions and OIDC trust rather than replace them.

## Reviewed plan and apply

Use a separately authorized AWS profile and never put credentials in configuration:

```bash
make package
cp infra/environments/dev/backend.hcl.example infra/environments/dev/backend.hcl
cp infra/environments/dev/terraform.tfvars.example infra/environments/dev/terraform.tfvars
# Edit ignored local files with approved values.
terraform -chdir=infra/environments/dev init -backend-config=backend.hcl
terraform -chdir=infra/environments/dev plan -out=reviewed.tfplan
# STOP: approve the exact plan, account, cost, and IAM changes.
terraform -chdir=infra/environments/dev apply reviewed.tfplan
export API_URL="$(terraform -chdir=infra/environments/dev output -raw api_url)"
uv run python scripts/smoke.py
```

The manual workflow offers only plan/apply. Its apply path creates a fresh plan during the approved run; immutable plan promotion and per-plan approval are deferred and required before production.

## Explicit evaluation

```bash
uv run python -m evaluation.cli run \
  --target-url "$API_URL" --region "$AWS_REGION" --allow-cloud \
  --seed 42 --scenario-count 50 --output-dir artifacts/dev-evaluation
```

These calls invoke Bedrock and may incur costs. Use the separate evaluation role with API invoke permission, not infrastructure mutation privileges.

The optional live pytest test requires `ALLOW_CLOUD_TESTS=true`, `API_URL`, and `AWS_REGION`. Never set that flag in normal CI.

## Cost and incident boundaries

Potential costs include Bedrock, Lambda, API Gateway, S3 storage/requests, CloudWatch logs/alarms, and GitHub Actions. Obtain account- and region-specific prices before enabling execution; no numerical cost estimate is implied.

On suspected exposure, disable cloud workflows, revoke affected role access, preserve audit evidence, and follow the account's incident process. For wrong classifications, preserve synthetic report/configuration provenance rather than silently lowering thresholds.

## Cleanup and rollback

There is no automatic dev/prod destroy path. The ephemeral workflow refuses all requests until isolated state and protection tests exist.

For authorized cleanup, inventory resources, preserve reports/state, review a destroy plan, and obtain explicit approval before applying it. Rollback rehearsal, alarm routing, and post-teardown verification remain acceptance work, not demonstrated capabilities.
