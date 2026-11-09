# Bootstrap is a reviewed prerequisite, not an automatic admin grant

This project deliberately does not fabricate a universally safe deployment IAM policy. Before a dev plan or deployment, an account administrator must provision or select the following resources and review their policies.

- **State backend:** a private, encrypted, versioned S3 bucket, TLS-only access, and a state key dedicated to this project. Configure S3 locking with the checked-in backend example; do not reuse dev application artifacts as state.
- **GitHub OIDC:** use the existing account provider if present. Restrict audience to `sts.amazonaws.com` and subject to `repo:multi-byte-pixel/issue-classification-pipeline:environment:dev`; create separate deployment and evaluation roles.
- **Deployment role:** scope state and lock operations to the chosen key, resource mutation to this project's names, `iam:PassRole` to the runtime role, and role creation to the required boundary. Do not grant AdministratorAccess or trust pull-request refs.
- **Runtime boundary:** permit only the reviewed model/inference-profile resources and this Lambda log group. Account policy and model choice can require additional review; the dev stack intentionally requires an explicit boundary ARN.
- **Evaluation role:** allow invocation of the deployed API and optional report writes under the approved bucket's `evaluation/` prefix, not infrastructure mutation.
- **Protected dev environment:** allow only the main branch, require a human reviewer where supported, and prevent self-review where available. If the account plan cannot enforce required approval controls, keep cloud workflows disabled and use a separately reviewed manual process.

Set `CLOUD_ENABLED=true` only after reviewing the plan, account, spend controls, and environment restrictions. This file is an explicit incomplete bootstrap step, not a runnable bootstrap stack.
