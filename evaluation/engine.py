"""Report schema, honest metric denominators, and fail-closed quality gates."""

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import Field, ValidationError

from evaluation.runners import Runner
from evaluation.scenarios import DATASET_VERSION, Scenario
from event_classifier.domain import (
    LABELS,
    PROMPT_VERSION,
    ClassificationResponse,
    Contract,
)


class Gate(Contract):
    metric: str
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    blocking: bool = True
    justification: str = Field(min_length=1)


class GateConfig(Contract):
    gates: list[Gate] = Field(min_length=1)


class GateResult(Contract):
    metric: str
    passed: bool
    blocking: bool
    actual: float | None
    reason: str


class CaseResult(Contract):
    scenario_id: str
    expected: str
    actual: str | None
    tags: list[str]
    status: int
    contract_valid: bool
    correct: bool
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    fallback_reason: str | None
    model_id: str | None
    # None means this was not a paired multi-turn case.
    paired_context_passed: bool | None


class Report(Contract):
    schema_version: str = "1.0"
    run_id: str
    created_at: str
    provenance: dict[str, Any]
    metrics: dict[str, float]
    per_label: dict[str, dict[str, float]]
    by_tag: dict[str, float]
    confusion: dict[str, dict[str, int]]
    cases: list[CaseResult]
    gates: list[GateResult]
    passed: bool


def check_gates(metrics: dict[str, float], config: GateConfig) -> list[GateResult]:
    """Missing, nonfinite, or unbounded required metrics cannot silently pass.

    Exemptions are deliberately unsupported in this first slice: no implicit skip,
    TODO owner, or expired waiver can accidentally relax a safety requirement.
    """
    results = []
    for gate in config.gates:
        actual = metrics.get(gate.metric)
        configured = gate.minimum is not None or gate.maximum is not None
        finite = actual is not None and math.isfinite(actual)
        passed = (
            configured
            and finite
            and (gate.minimum is None or (actual is not None and actual >= gate.minimum))
            and (gate.maximum is None or (actual is not None and actual <= gate.maximum))
        )
        results.append(
            GateResult(
                metric=gate.metric,
                passed=passed,
                blocking=gate.blocking,
                actual=actual if finite else None,
                reason="passed"
                if passed
                else "missing/nonfinite metric, invalid bounds, or threshold",
            )
        )
    return results


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile; sample count is always reported alongside it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def evaluate(
    runner: Runner,
    scenarios: list[Scenario],
    config: GateConfig,
    provenance: dict[str, Any],
) -> Report:
    """Count every attempted primary case, including errors, in headline denominators.

    Additional truncated-context calls are counted separately. They do not inflate
    headline scenario count or accuracy, and are required for a paired context pass.
    Invalid contracts and non-2xx outcomes never earn task-quality credit.
    """
    if not scenarios:
        raise ValueError("Cannot evaluate an empty scenario set")
    cases = []
    for scenario in scenarios:
        status, raw, latency = runner.run(scenario.request)
        try:
            result = ClassificationResponse.model_validate(raw)
        except ValidationError:
            result = None
        valid = result is not None
        correct = (
            200 <= status < 300 and result is not None and result.label == scenario.expected_label
        )
        paired = None
        if scenario.prefix_expected_label is not None:
            prefix = scenario.request.model_copy(update={"turns": scenario.request.turns[:1]})
            prefix_status, prefix_raw, _ = runner.run(prefix)
            try:
                prefix_result = ClassificationResponse.model_validate(prefix_raw)
            except ValidationError:
                prefix_result = None
            paired = bool(
                correct
                and 200 <= prefix_status < 300
                and prefix_result is not None
                and prefix_result.label == scenario.prefix_expected_label
            )
        cases.append(
            CaseResult(
                scenario_id=scenario.scenario_id,
                expected=scenario.expected_label,
                actual=result.label if result else None,
                tags=scenario.tags,
                status=status,
                contract_valid=valid,
                correct=bool(correct),
                latency_ms=latency,
                fallback_reason=result.fallback_reason if result else None,
                model_id=result.model_id if result else None,
                paired_context_passed=paired,
            )
        )
    count = len(cases)
    review = [c for c in cases if c.actual == "NEEDS_REVIEW"]
    paired_cases = [c for c in cases if c.paired_context_passed is not None]
    adversarial = [c for c in cases if "adversarial" in c.tags]
    metrics = {
        "total_scenarios": float(count),
        "completed_scenarios": float(sum(c.status != 0 for c in cases)),
        "unique_templates": float(len({s.scenario_id.split("template-")[-1] for s in scenarios})),
        "contract_validity": sum(c.contract_valid for c in cases) / count,
        "allowed_label_rate": sum(c.actual in LABELS for c in cases) / count,
        "accuracy": sum(c.correct for c in cases) / count,
        "api_error_rate": sum(not 200 <= c.status < 300 for c in cases) / count,
        "http_success_rate": sum(200 <= c.status < 300 for c in cases) / count,
        "fallback_rate": len(review) / count,
        "provider_error_count": float(
            sum(c.fallback_reason in ("provider_timeout", "provider_error") for c in cases)
        ),
        "context_control_calls": float(len(paired_cases)),
    }
    if paired_cases:
        metrics["paired_context_accuracy"] = sum(
            c.paired_context_passed is True for c in paired_cases
        ) / len(paired_cases)
    if adversarial:
        metrics["adversarial_safe_rate"] = sum(c.correct for c in adversarial) / len(adversarial)
    for p in (50, 95, 99):
        metrics[f"latency_p{p}_ms"] = percentile([c.latency_ms for c in cases], p / 100)
    for reason, reason_count in Counter(c.fallback_reason for c in review).items():
        metrics[f"fallback_rate_{reason}"] = reason_count / count
    per_label = {}
    confusion = {}
    for label in LABELS:
        support = sum(c.expected == label for c in cases)
        predicted = sum(c.actual == label for c in cases)
        true_positive = sum(c.correct and c.expected == label for c in cases)
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / support if support else 0.0
        per_label[label] = {
            "support": float(support),
            "predicted": float(predicted),
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
        confusion[label] = dict(
            Counter(
                c.actual if 200 <= c.status < 300 and c.actual else "__ERROR__"
                for c in cases
                if c.expected == label
            )
        )
    by_tag = {}
    for tag in sorted({tag for c in cases for tag in c.tags}):
        tagged = [c for c in cases if tag in c.tags]
        by_tag[tag] = sum(c.correct for c in tagged) / len(tagged)
    serialized = json.dumps([s.model_dump() for s in scenarios], sort_keys=True).encode()
    gates = check_gates(metrics, config)
    return Report(
        run_id=str(uuid4()),
        created_at=datetime.now(UTC).isoformat(),
        provenance={
            **provenance,
            "seed": scenarios[0].seed,
            "dataset_version": DATASET_VERSION,
            "dataset_sha256": hashlib.sha256(serialized).hexdigest(),
            "prompt_version": PROMPT_VERSION,
            "observed_models": sorted({c.model_id for c in cases if c.model_id}),
            "gate_config": config.model_dump(),
            "limitation": "Small repeated synthetic templates; not production quality evidence.",
        },
        metrics=metrics,
        per_label=per_label,
        by_tag=by_tag,
        confusion=confusion,
        cases=cases,
        gates=gates,
        passed=all(g.passed or not g.blocking for g in gates),
    )
