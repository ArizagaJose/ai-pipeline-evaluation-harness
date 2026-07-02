"""Command line interface for the local evaluation harness."""

import argparse
import sys

from ai_data_harness.adjudication import write_adjudication_json
from ai_data_harness.config import load_evaluation_config
from ai_data_harness.evaluation import run_evaluation
from ai_data_harness.reporting import write_markdown_report, write_run_summary_json
from ai_data_harness.synthetic import generate_scale_fixture


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface and return a process exit code.

    Args:
        argv: Optional argument list. Defaults to ``sys.argv`` when omitted.

    Returns:
        Process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        return _evaluate(args.config)
    if args.command == "generate-scale-fixture":
        return _generate_scale_fixture(
            args.output_dir,
            rows=args.rows,
            golden_rows=args.golden_rows,
            seed=args.seed,
        )

    parser.print_help(sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(prog="ai-data-harness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    evaluate = subparsers.add_parser("evaluate", help="run a configured evaluation")
    evaluate.add_argument("--config", required=True, help="path to evaluation JSON")
    generate = subparsers.add_parser(
        "generate-scale-fixture",
        help="generate a deterministic population-scale synthetic fixture",
    )
    generate.add_argument(
        "--output-dir",
        default="data/generated/scale",
        help="directory for the generated files",
    )
    generate.add_argument(
        "--rows",
        type=int,
        default=1_000_000,
        help="population row count for baseline and candidate outputs",
    )
    generate.add_argument(
        "--golden-rows",
        type=int,
        default=2_000,
        help="golden sample size drawn from the population",
    )
    generate.add_argument(
        "--seed",
        type=int,
        default=20260702,
        help="seed for the deterministic generator",
    )
    return parser


def _generate_scale_fixture(
    output_dir: str, *, rows: int, golden_rows: int, seed: int
) -> int:
    """Run scale-fixture generation from the CLI."""
    try:
        paths = generate_scale_fixture(
            output_dir,
            rows=rows,
            golden_rows=golden_rows,
            seed=seed,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"golden: {paths.golden_path}")
    print(f"baseline: {paths.baseline_output_path}")
    print(f"candidate: {paths.candidate_output_path}")
    return 0


def _evaluate(config_path: str) -> int:
    """Run a configured evaluation from the CLI."""
    try:
        config = load_evaluation_config(config_path)
        result = run_evaluation(config)
        write_markdown_report(result, config.report_path)
        if config.adjudication_path is not None and result.adjudication is not None:
            write_adjudication_json(result.adjudication, config.adjudication_path)
        if config.summary_path is not None:
            write_run_summary_json(result, config.summary_path)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"status: {result.status}")
    print(f"report: {config.report_path}")
    if config.adjudication_path is not None and result.adjudication is not None:
        print(f"adjudication: {config.adjudication_path}")
    if config.summary_path is not None:
        print(f"summary: {config.summary_path}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
