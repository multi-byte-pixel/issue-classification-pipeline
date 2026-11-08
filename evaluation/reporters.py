"""Machine-readable and human-readable artifacts; no customer conversation text."""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path

from evaluation.engine import Report


def write_reports(report: Report, output: Path) -> None:
    """Validate before writing; one run directory should be archived as an atomic unit."""
    Report.model_validate_json(report.model_dump_json())
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    lines = [
        "# Evaluation summary",
        "",
        f"Run: `{report.run_id}`. Target: `{report.provenance['target']}`.",
        f"Blocking gates: {'PASS' if report.passed else 'FAIL'}.",
        "Synthetic fixtures only; fake-provider scores are not model-quality evidence.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        *[f"| {key} | {value:.4f} |" for key, value in sorted(report.metrics.items())],
        "",
        "## Gates",
        "",
        *[
            f"- `{g.metric}`: {'PASS' if g.passed else 'FAIL'} "
            f"({'blocking' if g.blocking else 'warning'})."
            for g in report.gates
        ],
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n")
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["metric", "value"])
        writer.writerows(sorted(report.metrics.items()))
    suite = ET.Element(
        "testsuite",
        name="synthetic-evaluation",
        tests=str(len(report.cases)),
        failures=str(sum(not c.correct for c in report.cases)),
    )
    for case in report.cases:
        element = ET.SubElement(
            suite, "testcase", name=case.scenario_id, time=str(case.latency_ms / 1000)
        )
        if not case.correct:
            ET.SubElement(
                element, "failure", message="classification or contract failed"
            ).text = f"expected={case.expected}; actual={case.actual}; status={case.status}"
    ET.ElementTree(suite).write(output / "junit.xml", encoding="utf-8", xml_declaration=True)
