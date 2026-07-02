"""Unit tests for deterministic scale-fixture generation."""

import json
from pathlib import Path

import pytest

from ai_data_harness.cli import main
from ai_data_harness.contracts import load_contract, validate_rows
from ai_data_harness.io import read_rows
from ai_data_harness.synthetic import generate_scale_fixture

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "support_ticket_output_contract.json"


def test_generation_writes_expected_row_counts(tmp_path: Path) -> None:
    """Verify generated files match requested population and sample sizes."""
    paths = generate_scale_fixture(tmp_path, rows=500, golden_rows=50)

    golden_rows = read_rows(paths.golden_path)
    baseline_rows = read_rows(paths.baseline_output_path)
    candidate_rows = read_rows(paths.candidate_output_path)

    assert len(golden_rows) == 50
    assert len(baseline_rows) == 500
    assert len(candidate_rows) == 500


def test_generation_is_deterministic(tmp_path: Path) -> None:
    """Verify the same seed produces identical rows across runs."""
    first = generate_scale_fixture(tmp_path / "first", rows=300, golden_rows=30)
    second = generate_scale_fixture(tmp_path / "second", rows=300, golden_rows=30)

    assert read_rows(first.golden_path) == read_rows(second.golden_path)
    assert read_rows(first.candidate_output_path) == read_rows(
        second.candidate_output_path
    )
    assert read_rows(first.baseline_output_path) == read_rows(
        second.baseline_output_path
    )


def test_different_seeds_produce_different_outputs(tmp_path: Path) -> None:
    """Verify the seed changes the generated sample."""
    first = generate_scale_fixture(tmp_path / "first", rows=300, golden_rows=30)
    second = generate_scale_fixture(
        tmp_path / "second", rows=300, golden_rows=30, seed=7
    )

    assert read_rows(first.golden_path) != read_rows(second.golden_path)


def test_golden_ids_are_covered_by_outputs(tmp_path: Path) -> None:
    """Verify the golden sample is a subset of the generated population."""
    paths = generate_scale_fixture(tmp_path, rows=400, golden_rows=40)

    golden_ids = {row["record_id"] for row in read_rows(paths.golden_path)}
    candidate_ids = {row["record_id"] for row in read_rows(paths.candidate_output_path)}

    assert len(golden_ids) == 40
    assert golden_ids <= candidate_ids


def test_generated_outputs_pass_contract_validation(tmp_path: Path) -> None:
    """Verify generated outputs satisfy the committed support-ticket contract."""
    paths = generate_scale_fixture(tmp_path, rows=400, golden_rows=40)
    contract = load_contract(CONTRACT_PATH)

    baseline = validate_rows(read_rows(paths.baseline_output_path), contract)
    candidate = validate_rows(read_rows(paths.candidate_output_path), contract)

    assert baseline.passed
    assert candidate.passed


def test_generation_rejects_invalid_sizes(tmp_path: Path) -> None:
    """Verify out-of-range row counts raise clear errors."""
    with pytest.raises(ValueError, match="rows must be at least 1"):
        generate_scale_fixture(tmp_path, rows=0, golden_rows=1)
    with pytest.raises(ValueError, match="golden_rows must be between"):
        generate_scale_fixture(tmp_path, rows=10, golden_rows=11)


def test_cli_generates_and_evaluates_scale_fixture(tmp_path: Path) -> None:
    """Verify the CLI generates a fixture that evaluates end to end."""
    fixture_dir = tmp_path / "fixture"
    exit_code = main(
        [
            "generate-scale-fixture",
            "--output-dir",
            str(fixture_dir),
            "--rows",
            "800",
            "--golden-rows",
            "200",
        ]
    )
    assert exit_code == 0

    config_path = tmp_path / "evaluation.json"
    config_path.write_text(
        json.dumps(
            {
                "paths": {
                    "contract": str(CONTRACT_PATH),
                    "golden": str(fixture_dir / "support_ticket_scale_golden.csv"),
                    "baseline_output": str(
                        fixture_dir / "support_ticket_scale_baseline.parquet"
                    ),
                    "candidate_output": str(
                        fixture_dir / "support_ticket_scale_candidate.parquet"
                    ),
                    "report": str(tmp_path / "report.md"),
                    "summary": str(tmp_path / "summary.json"),
                },
                "record_id_column": "record_id",
                "abstention_column": "abstained",
                "attributes": {
                    "urgency": {
                        "expected_column": "expected_urgency",
                        "predicted_column": "predicted_urgency",
                    },
                    "should_escalate": {
                        "expected_column": "expected_should_escalate",
                        "predicted_column": "predicted_should_escalate",
                    },
                },
                "regression_gates": [
                    {"attribute": "urgency", "max_accuracy_drop": 0.05}
                ],
                "max_candidate_abstention_rate": 0.1,
                "max_false_acceptance_rate": 0.1,
            }
        )
    )

    exit_code = main(["evaluate", "--config", str(config_path)])
    summary = json.loads((tmp_path / "summary.json").read_text())

    assert exit_code == 1
    assert summary["status"] == "NEEDS_REVIEW"
    totals = {
        metric["attribute"]: metric["total"]
        for metric in summary["metrics"]["candidate_attributes"]
    }
    assert totals["urgency"] == 200


def test_cli_rejects_invalid_generation_sizes(tmp_path: Path) -> None:
    """Verify CLI generation returns exit code 2 for invalid sizes."""
    exit_code = main(
        [
            "generate-scale-fixture",
            "--output-dir",
            str(tmp_path),
            "--rows",
            "10",
            "--golden-rows",
            "20",
        ]
    )
    assert exit_code == 2
