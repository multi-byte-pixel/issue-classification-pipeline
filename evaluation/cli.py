"""Run local or explicitly authorized SigV4-authenticated deployed evaluation."""

import argparse
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from evaluation.engine import GateConfig, evaluate
from evaluation.reporters import write_reports
from evaluation.runners import ApiRunner, LocalRunner, Runner
from evaluation.scenarios import generate
from event_classifier.adapters import FakeClassifier
from event_classifier.domain import ClassificationRequest
from event_classifier.service import ClassificationService

logger = logging.getLogger(__name__)


class BrokenContractRunner:
    """Deliberate fault injection proves required gates fail rather than silently pass."""

    def run(self, request: ClassificationRequest) -> tuple[int, Any, float]:
        return 200, {"label": "NOT_ALLOWED"}, 0.0


def revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--scenario-count", type=int, default=50)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evaluation"))
    parser.add_argument(
        "--quality-gates", type=Path, default=Path("evaluation/quality_gates.dev.yaml")
    )
    parser.add_argument("--target-url")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION"))
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument("--inject-failure", action="store_true")
    args = parser.parse_args(argv)
    if args.target_url and (not args.allow_cloud or not args.region):
        parser.error("Cloud runs require --allow-cloud and --region; they may incur costs")
    if args.inject_failure and args.target_url:
        parser.error("Fault-injection demo is local only")
    config = GateConfig.model_validate(yaml.safe_load(args.quality_gates.read_text()))
    runner: Runner = LocalRunner(ClassificationService(FakeClassifier()))
    if args.target_url:
        runner = ApiRunner(args.target_url, args.region)
    elif args.inject_failure:
        runner = BrokenContractRunner()
    report = evaluate(
        runner,
        generate(args.seed, args.scenario_count),
        config,
        {
            "target": args.target_url
            or ("local-fault-injection" if args.inject_failure else "local-fake"),
            "git_sha": revision(),
            "environment": "dev" if args.target_url else "offline",
            "inference_settings": {"temperature": 0, "max_tokens": 128}
            if args.target_url
            else {"provider": "deterministic fake, no inference"},
        },
    )
    write_reports(report, args.output_dir)
    logger.info("Evaluation complete: run_id=%s passed=%s", report.run_id, report.passed)
    return 0 if report.passed else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
