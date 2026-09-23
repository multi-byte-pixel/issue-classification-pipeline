# Evaluation methodology

The harness distinguishes deterministic software correctness, task behavior, safety policy, and operational reliability. Offline fake-provider results prove mechanics, not LLM quality.

## Dataset and multi-turn evidence

An explicit nonnegative seed and at least 10 cases guarantee every template appears. Additional cases repeat templates in seeded order; `unique_templates` exposes that a 50-case run does not contain 50 independent semantic scenarios.

Multi-turn cases include a truncated-context call. A pair passes only when full conversation and prefix each receive the expected label; one case resolves ambiguity and another supersedes the initial interpretation.

## Denominators

- **Accuracy / contract validity / allowed-label rate:** all primary scenarios, including malformed responses and HTTP failures.
- **API error rate:** non-2xx and transport errors over all primary calls.
- **Per-label metrics:** support and predicted counts are exposed; zero-denominator precision/recall are 0. Errors never earn true-positive credit.
- **Confusion matrix:** non-2xx and invalid contracts appear as `__ERROR__`.
- **Fallback rate:** valid review responses over all primary scenarios, also broken down by reason.
- **Paired context accuracy:** passed pairs over paired scenarios only. `context_control_calls` is separate and excluded from headline counts and latency.
- **Adversarial safe rate:** correct outcomes over tagged adversarial cases only, not comprehensive attack resistance.
- **Latency:** primary-call duration, nearest-rank p50/p95/p99. Small repeated fixtures do not establish performance at load.

## Gates and reports

Required gates demand perfect contracts, allowed labels, included adversarial outcomes, and no observed API errors. Development accuracy/context thresholds warn; they are uncalibrated.

Missing/nonfinite metrics fail required gates. Invalid report shapes fail schema validation; no exemptions or skip-on-error paths exist. The fault-injection runner must exit 1, verified by `make gate-demo`.

Reports include run ID, timestamp, code revision, seed, dataset hash/version, prompt version, observed models, inference configuration, target, and gate configuration. JSON is canonical, with Markdown, CSV, and JUnit companions.

## Next extensions

Baseline comparison must reject incompatible model/prompt/dataset/configurations rather than report misleading deltas. Model-generated data requires independent provenance, label review, and a holdout strategy; neither feature is implemented in this slice.
