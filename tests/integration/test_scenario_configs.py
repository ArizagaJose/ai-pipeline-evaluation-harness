"""Integration tests for bundled scenario configs."""

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ai_data_harness.cli import main
from ai_data_harness.io import read_csv_rows

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_CONFIG_DIR = ROOT / "examples" / "scenarios"


@pytest.mark.parametrize(
    ("scenario", "expected_exit_code", "expected_status", "expected_failed_gates"),
    [
        ("passes_all_gates", 0, "PASSED", []),
        ("contract_validation_failure", 1, "FAILED", []),
        (
            "coverage_improves_false_acceptance_fails",
            1,
            "FAILED",
            ["max_false_acceptance_rate"],
        ),
        (
            "global_improves_segment_regresses",
            1,
            "FAILED",
            ["segment_max_accuracy_drop"],
        ),
        ("coverage_improves_critical_review", 1, "NEEDS_REVIEW", []),
        ("severity_override_requires_review", 1, "NEEDS_REVIEW", []),
        (
            "severity_override_gate_fails",
            1,
            "FAILED",
            ["max_severity_review_count"],
        ),
    ],
)
def test_support_ticket_scenario_config(
    tmp_path: Path,
    scenario: str,
    expected_exit_code: int,
    expected_status: str,
    expected_failed_gates: list[str],
) -> None:
    """Verify support ticket scenario config."""
    config_path = _write_tmp_config(SCENARIO_CONFIG_DIR / f"{scenario}.json", tmp_path)

    exit_code = main(["evaluate", "--config", str(config_path)])

    report = (tmp_path / f"{scenario}.md").read_text()
    summary_path = tmp_path / f"{scenario}_summary.json"
    adjudication_path = tmp_path / f"{scenario}_adjudication.json"
    summary = json.loads(summary_path.read_text())

    assert exit_code == expected_exit_code
    assert f"Overall status: **{expected_status}**" in report
    assert summary_path.exists()
    assert adjudication_path.exists()
    assert summary["status"] == expected_status
    assert summary["passed"] is (expected_status == "PASSED")
    assert [gate["name"] for gate in summary["failed_gates"]] == expected_failed_gates

    if scenario == "passes_all_gates":
        assert summary["contracts"]["candidate"]["passed"] is True
        assert summary["metrics"]["admissibility"]["accuracy"] == 1.0
        assert summary["metrics"]["admissibility"]["requires_review_cells"] == 0

    if scenario == "contract_validation_failure":
        candidate_issues = summary["contracts"]["candidate"]["issues"]
        assert [issue["code"] for issue in candidate_issues] == [
            "invalid_allowed_value"
        ]
        assert candidate_issues[0]["value"] == "refund"
        assert summary["metric_deltas"] == []

    if scenario == "coverage_improves_false_acceptance_fails":
        failed_gate = summary["failed_gates"][0]
        product_area_delta = _metric_delta(summary, "product_area")
        assert failed_gate["name"] == "max_false_acceptance_rate"
        assert failed_gate["accuracy_drop"] > 0.0
        assert product_area_delta["baseline_row_level_abstention_rate"] > 0.0
        assert product_area_delta["candidate_row_level_abstention_rate"] == 0.0
        assert summary["metrics"]["admissibility"]["incorrect_accepted_cells"] == 1

    if scenario == "global_improves_segment_regresses":
        failed_gate = summary["failed_segment_gates"][0]
        urgency_delta = _metric_delta(summary, "urgency")
        enterprise_urgency_delta = _segment_metric_delta(
            summary,
            segment_column="customer_tier",
            segment_value="enterprise",
            attribute="urgency",
        )
        assert failed_gate["name"] == "segment_max_accuracy_drop"
        assert urgency_delta["accuracy_delta"] > 0.0
        assert enterprise_urgency_delta["accuracy_delta"] < 0.0

    if scenario == "coverage_improves_critical_review":
        issue_category_delta = _metric_delta(summary, "issue_category")
        assert summary["failed_gates"] == []
        assert summary["metrics"]["admissibility"]["requires_review_cells"] == 3
        assert summary["metrics"]["admissibility"]["critical_wrong_cells"] == 3
        assert issue_category_delta["baseline_row_level_abstention_rate"] > 0.0
        assert issue_category_delta["candidate_row_level_abstention_rate"] == 0.0

    if scenario == "severity_override_requires_review":
        severity_counts = summary["metrics"]["severity_review_counts"]
        assert summary["failed_gates"] == []
        assert summary["metrics"]["admissibility"]["false_acceptance_rate"] == 0.0
        assert summary["metrics"]["admissibility"]["incorrect_accepted_cells"] == 0
        assert summary["metrics"]["admissibility"]["requires_review_cells"] == 1
        assert severity_counts == [
            {
                "attribute": "product_area",
                "candidate_value": "payments",
                "count": 1,
                "expected_value": "subscriptions",
                "reason": "Subscription billing mistakes should be reviewed.",
                "severity": "high",
            }
        ]
        assert "### Severity Review Counts" in report
        assert (
            "| product_area | subscriptions | payments | high | "
            "Subscription billing mistakes should be reviewed. | 1 |"
        ) in report

    if scenario == "severity_override_gate_fails":
        failed_gate = summary["failed_gates"][0]
        severity_counts = summary["metrics"]["severity_review_counts"]
        assert failed_gate["name"] == "max_severity_review_count"
        assert failed_gate["attribute"] == "severity=high"
        assert failed_gate["accuracy_drop"] == 1
        assert failed_gate["threshold"] == 0
        assert summary["metrics"]["admissibility"]["requires_review_cells"] == 1
        assert severity_counts[0]["severity"] == "high"
        assert "### Severity Review Counts" in report
        assert (
            "| max_severity_review_count | severity-routed human review count |"
            in report
        )


def test_support_ticket_scenario_config_accepts_parquet_inputs(
    tmp_path: Path,
) -> None:
    """Verify support ticket scenario config accepts parquet inputs."""
    source_config_path = SCENARIO_CONFIG_DIR / "global_improves_segment_regresses.json"
    data = json.loads(source_config_path.read_text())
    source_base = source_config_path.parent

    data["paths"]["contract"] = str((source_base / data["paths"]["contract"]).resolve())
    for key in ("golden", "source", "baseline_output", "candidate_output"):
        source_path = (source_base / data["paths"][key]).resolve()
        parquet_path = tmp_path / f"{key}.parquet"
        _write_parquet_copy(source_path, parquet_path)
        data["paths"][key] = str(parquet_path)

    data["paths"]["report"] = str(tmp_path / "global_improves_segment_regresses.md")
    data["paths"]["adjudication"] = str(
        tmp_path / "global_improves_segment_regresses_adjudication.json"
    )
    data["paths"]["summary"] = str(
        tmp_path / "global_improves_segment_regresses_summary.json"
    )
    config_path = tmp_path / "global_improves_segment_regresses.json"
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    exit_code = main(["evaluate", "--config", str(config_path)])

    report = (tmp_path / "global_improves_segment_regresses.md").read_text()
    summary = json.loads(
        (tmp_path / "global_improves_segment_regresses_summary.json").read_text()
    )
    assert exit_code == 1
    assert "Overall status: **FAILED**" in report
    assert summary["status"] == "FAILED"
    assert [gate["name"] for gate in summary["failed_gates"]] == [
        "segment_max_accuracy_drop"
    ]
    assert summary["failed_segment_gates"][0]["name"] == "segment_max_accuracy_drop"


def _write_tmp_config(source_config_path: Path, tmp_path: Path) -> Path:
    """Support write tmp config."""
    data = json.loads(source_config_path.read_text())
    source_base = source_config_path.parent

    for key in ("contract", "golden", "source", "baseline_output", "candidate_output"):
        if key in data["paths"]:
            data["paths"][key] = str((source_base / data["paths"][key]).resolve())

    scenario = source_config_path.stem
    data["paths"]["report"] = str(tmp_path / f"{scenario}.md")
    data["paths"]["adjudication"] = str(tmp_path / f"{scenario}_adjudication.json")
    data["paths"]["summary"] = str(tmp_path / f"{scenario}_summary.json")

    config_path = tmp_path / f"{scenario}.json"
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return config_path


def _write_parquet_copy(source_path: Path, target_path: Path) -> None:
    """Support write parquet copy."""
    rows = read_csv_rows(source_path)
    pq.write_table(pa.Table.from_pylist(rows), target_path)


def _metric_delta(summary: dict[str, Any], attribute: str) -> dict[str, Any]:
    """Support metric delta."""
    return next(
        delta for delta in summary["metric_deltas"] if delta["attribute"] == attribute
    )


def _segment_metric_delta(
    summary: dict[str, Any],
    *,
    segment_column: str,
    segment_value: str,
    attribute: str,
) -> dict[str, Any]:
    """Support segment metric delta."""
    return next(
        delta
        for delta in summary["segment_metric_deltas"]
        if delta["segment_column"] == segment_column
        and delta["segment_value"] == segment_value
        and delta["attribute"] == attribute
    )
