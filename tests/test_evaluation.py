import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from evaluation.cli import BrokenContractRunner, main
from evaluation.engine import GateConfig, Report, check_gates, evaluate, percentile
from evaluation.runners import ApiRunner, LocalRunner
from evaluation.scenarios import generate
from event_classifier.adapters import FakeClassifier
from event_classifier.service import ClassificationService


def gates():
    return GateConfig.model_validate(
        yaml.safe_load(Path("evaluation/quality_gates.dev.yaml").read_text())
    )


def runner():
    return LocalRunner(ClassificationService(FakeClassifier()))


def test_generation_is_seeded_and_contains_pairs():
    assert generate(42, 30) == generate(42, 30)
    assert generate(42, 30) != generate(43, 30)
    assert sum(s.prefix_expected_label is not None for s in generate(42, 10)) == 2


@pytest.mark.parametrize("seed,count", [(-1, 10), (42, 0), (42, 9)])
def test_insufficient_fixture_coverage_is_rejected(seed, count):
    with pytest.raises(ValueError):
        generate(seed, count)


def test_local_metrics_are_transparent():
    report = evaluate(runner(), generate(42, 10), gates(), {"target": "local-fake"})
    assert report.passed
    assert report.metrics["accuracy"] == 1
    assert report.metrics["paired_context_accuracy"] == 1
    assert report.metrics["context_control_calls"] == 2
    assert report.metrics["total_scenarios"] == 10
    assert report.metrics["fallback_rate"] == 0.3
    assert report.per_label["NEEDS_REVIEW"]["support"] == 3
    assert report.provenance["observed_models"] == ["fake-rules-v1"]
    assert len(report.provenance["dataset_sha256"]) == 64
    Report.model_validate_json(report.model_dump_json())


def test_invalid_contracts_fail_not_drop():
    report = evaluate(BrokenContractRunner(), generate(42, 10), gates(), {"target": "fault"})
    assert not report.passed
    assert report.metrics["total_scenarios"] == 10
    assert report.metrics["contract_validity"] == 0
    assert report.metrics["accuracy"] == 0
    assert report.metrics["paired_context_accuracy"] == 0
    assert report.confusion["ACCOUNT_ACCESS"]["__ERROR__"] == 2


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 0.99])
def test_required_gate_fails_closed(value):
    metrics = {} if value is None else {"contract_validity": value}
    assert not check_gates(metrics, gates())[0].passed


def test_warn_only_quality_gate_does_not_override_safety():
    report = evaluate(runner(), generate(42, 10), gates(), {"target": "local"})
    report.metrics["accuracy"] = 0.1
    results = check_gates(report.metrics, gates())
    assert any(not g.passed and not g.blocking for g in results)
    assert all(g.passed for g in results if g.blocking)


def test_malformed_report_rejected():
    with pytest.raises(ValidationError):
        Report.model_validate({"schema_version": "1.0"})


def test_cli_artifacts_and_failure_exit(tmp_path):
    assert main(["run", "--seed", "42", "--output-dir", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["passed"]
    assert (tmp_path / "metrics.csv").read_text().startswith("metric,value")
    assert ET.parse(tmp_path / "junit.xml").getroot().get("failures") == "0"
    assert main(["run", "--seed", "42", "--inject-failure", "--output-dir", str(tmp_path)]) == 1
    assert not json.loads((tmp_path / "report.json").read_text())["passed"]


def test_cloud_opt_in_required():
    with pytest.raises(SystemExit) as error:
        main(["run", "--seed", "42", "--target-url", "https://example.test"])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test",
        "https://user:secret@example.test",
        "https://example.test?token=secret",
        "https://example.test#fragment",
    ],
)
def test_api_runner_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        ApiRunner(url, "us-east-1")


def test_percentile_definition():
    assert percentile(list(range(1, 101)), 0.95) == 95
