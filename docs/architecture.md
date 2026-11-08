# Architecture and boundaries

The quality platform is the project; event classification is replaceable sample content. Workflow and infrastructure boundaries come first, then a narrow runtime contract, then independent evaluation.

## Planes and trust

- **CI/control plane:** PR code gets no AWS identity. Offline checks use a read-only GitHub token; trusted main-branch manual cloud workflows additionally require `CLOUD_ENABLED=true` and a configured `dev` environment.
- **Runtime/data plane:** API Gateway requires IAM signatures before Lambda. Input validation rejects invalid data; Bedrock proposes a label; deterministic code validates untrusted output and enforces the review policy.
- **Evaluation plane:** offline tests inject a fake; deployed runs use the public contract through SigV4 HTTPS. Expected labels remain in the evaluator, never in the SUT prompt.
- **Artifact boundary:** reports contain synthetic IDs, labels, metrics, and provenance, not conversation text. GitHub artifacts retain 14 days; S3 writes are deferred.

## HTTP semantics

| Condition | HTTP result | Meaning |
|---|---|---|
| Invalid request | 400 error object | Do not invoke provider |
| Valid classification | 200 classification response | Allowed label |
| Ambiguous | 200 `NEEDS_REVIEW` | Valid review outcome |
| Invalid model JSON/label | 200 review, `invalid_model_output` | Deterministic enforcement |
| Known provider timeout/error | 503 with review response | Safe policy, operational failure |
| Programming bug | Unhandled error | Not disguised as success |

The API integration timeout is 30 seconds and Lambda is limited to 25 seconds. Bedrock permits two total attempts with 2-second connection and 8-second read timeouts; verify these budgets against real service behavior.

## Architecture reference

Use the [AWS Generative AI Application Builder reference](https://docs.aws.amazon.com/solutions/latest/generative-ai-application-builder-on-aws/architecture-overview.html) as conceptual background, not equivalent controls or features. This starter omits RAG, dashboards, agents, MCP, and multi-agent orchestration.

The provider interface accepts validated requests and returns untrusted text. Confidence is omitted rather than treated as a probability, and production semantic decisions remain out of scope.
