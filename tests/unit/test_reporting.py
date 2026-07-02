"""Unit tests for report and run-summary rendering."""

import csv
import json
from pathlib import Path

import pytest

from ai_data_harness.config import load_evaluation_config
from ai_data_harness.evaluation import run_evaluation
from ai_data_harness.reporting import render_markdown_report, render_run_summary

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "examples" / "support_ticket_evaluation.json"


def test_report_includes_status_metrics_admissibility_and_gate_results() -> None:
    """Verify report includes status metrics admissibility and gate results."""
    result = run_evaluation(load_evaluation_config(CONFIG_PATH))

    report = render_markdown_report(result)

    assert "Overall status: **NEEDS_REVIEW**" in report
    assert report.index("## Candidate Admissibility Decision") < report.index(
        "## Baseline-vs-Candidate Regression Context"
    )
    assert "## Attribute Metrics" not in report
    assert (
        "NEEDS_REVIEW is a safe routing outcome: configured gates passed, but one "
        "or more requires_review cells must be reviewed before promotion."
    ) in report
    assert "adjudicated_cell_accuracy" in report
    assert "cell_level_abstention_rate" in report
    assert "false_acceptance_rate" in report
    assert "human_review_rate" in report
    assert "critical_wrong_rate" in report
    assert "### Review Queue Composition" in report
    assert "review_incorrect_rate" in report
    assert "review_abstained_rate" in report
    assert "review_invalid_rate" in report
    assert "review_missing_rate" in report
    assert "These are comparison metrics for regression checks" in report
    assert "not cell-level routing or admissibility metrics" in report
    assert "baseline_attribute_regression_accuracy" in report
    assert "candidate_attribute_regression_accuracy" in report
    assert "attribute_regression_accuracy_delta" in report
    assert "max_accuracy_drop" in report
    assert "requires_review_cells" in report
    assert "## Admissibility & Human Review" not in report
    assert "### Critical Confusion Counts" in report
    assert "## Confidence Diagnostics" in report
    assert "Send the candidate to human review before promotion." in report


def test_run_summary_includes_status_metrics_failed_gates_and_artifacts() -> None:
    """Verify run summary includes status metrics failed gates and artifacts."""
    result = run_evaluation(load_evaluation_config(CONFIG_PATH))

    summary = render_run_summary(result)

    assert summary["status"] == "NEEDS_REVIEW"
    assert summary["passed"] is False
    assert summary["contracts"]["candidate"] == {
        "passed": True,
        "issue_count": 0,
        "issues": [],
    }
    assert summary["metrics"]["admissibility"]["critical_wrong_cells"] > 0
    assert summary["metrics"]["confidence_diagnostics"] == [
        {
            "abstained_cells": 0,
            "accuracy": 0.0,
            "bucket": "0.00-0.50",
            "cell_level_abstention_rate": 0.0,
            "correct_cells": 0,
            "false_acceptance_cells": 0,
            "false_acceptance_rate": 0.0,
            "total_cells": 0,
        },
        {
            "abstained_cells": 0,
            "accuracy": 13 / 15,
            "bucket": "0.50-0.75",
            "cell_level_abstention_rate": 0.0,
            "correct_cells": 13,
            "false_acceptance_cells": 0,
            "false_acceptance_rate": 0.0,
            "total_cells": 15,
        },
        {
            "abstained_cells": 0,
            "accuracy": 1.0,
            "bucket": "0.75-0.90",
            "cell_level_abstention_rate": 0.0,
            "correct_cells": 30,
            "false_acceptance_cells": 0,
            "false_acceptance_rate": 0.0,
            "total_cells": 30,
        },
        {
            "abstained_cells": 0,
            "accuracy": 1.0,
            "bucket": "0.90-1.00",
            "cell_level_abstention_rate": 0.0,
            "correct_cells": 15,
            "false_acceptance_cells": 0,
            "false_acceptance_rate": 0.0,
            "total_cells": 15,
        },
    ]
    assert summary["metrics"]["admissibility"]["requires_review_cells"] > 0
    assert summary["metrics"]["admissibility"]["cell_level_abstention_rate"] == 0.0
    assert summary["metrics"]["admissibility"]["review_incorrect_rate"] == 1.0
    assert summary["metrics"]["admissibility"]["review_abstained_rate"] == 0.0
    assert (
        summary["metric_groups"]["review_queue_composition"]["aliases"][
            "metrics.admissibility.review_incorrect_rate"
        ]
        == "review_incorrect_rate"
    )
    assert summary["metrics"]["outcome_counts"]["incorrect"] > 0
    assert summary["metrics"]["critical_confusions"] == [
        {
            "attribute": "should_escalate",
            "candidate_value": "false",
            "count": 1,
            "expected_value": "true",
        },
        {
            "attribute": "urgency",
            "candidate_value": "medium",
            "count": 1,
            "expected_value": "critical",
        },
    ]
    assert summary["metric_deltas"][0]["attribute"] == "issue_category"
    assert summary["metric_deltas"][0]["accuracy_delta"] == pytest.approx(1 / 12)
    assert summary["metric_deltas"][0]["candidate_row_level_abstention_rate"] == 0.0
    assert (
        summary["metrics"]["candidate_attributes"][0][
            "candidate_row_level_abstention_rate"
        ]
        == 0.0
    )
    assert summary["failed_gates"] == []
    assert summary["metric_groups"]["adjudicated_cell_admissibility"]["paths"] == [
        "metrics.admissibility",
        "metrics.outcome_counts",
    ]
    assert (
        summary["metric_groups"]["adjudicated_cell_admissibility"]["aliases"][
            "metrics.admissibility.accuracy"
        ]
        == "adjudicated_cell_accuracy"
    )
    assert (
        summary["metric_groups"]["adjudicated_cell_admissibility"]["aliases"][
            "metrics.admissibility.cell_level_abstention_rate"
        ]
        == "cell_level_abstention_rate"
    )
    assert (
        summary["metric_groups"]["baseline_vs_candidate_regression_context"]["aliases"][
            "metric_deltas[].accuracy_delta"
        ]
        == "attribute_regression_accuracy_delta"
    )
    regression_aliases = summary["metric_groups"][
        "baseline_vs_candidate_regression_context"
    ]["aliases"]
    assert (
        regression_aliases["metric_deltas[].baseline_row_level_abstention_rate"]
        == "baseline_row_level_abstention_rate"
    )
    assert (
        regression_aliases["metric_deltas[].candidate_row_level_abstention_rate"]
        == "candidate_row_level_abstention_rate"
    )
    assert (
        regression_aliases["segment_metric_deltas[].baseline_row_level_abstention_rate"]
        == "baseline_row_level_abstention_rate"
    )
    assert (
        regression_aliases[
            "segment_metric_deltas[].candidate_row_level_abstention_rate"
        ]
        == "candidate_row_level_abstention_rate"
    )
    assert (
        summary["metric_groups"]["gates"]["gate_metric_families"][
            "max_false_acceptance_rate"
        ]
        == "adjudicated admissibility false_acceptance_rate"
    )
    assert (
        "review_status" not in summary["metric_groups"]["gates"]["gate_metric_families"]
    )
    assert not any(
        "requires_review" in path for path in summary["metric_groups"]["gates"]["paths"]
    )
    assert (
        summary["metric_groups"]["review_routing"]["status_semantics"]
        == "NEEDS_REVIEW is based on requires_review_cells when contracts and gates "
        "pass; it is not a failed regression or threshold gate."
    )
    assert summary["metric_groups"]["review_routing"]["paths"] == [
        "status",
        "metrics.admissibility.requires_review_cells",
        "metrics.admissibility.human_review_rate",
    ]
    assert summary["metric_groups"]["review_routing"]["aliases"] == {
        "metrics.admissibility.requires_review_cells": "requires_review_cells",
        "metrics.admissibility.human_review_rate": "human_review_rate",
    }
    assert summary["artifact_paths"]["report"].endswith(
        "reports/support_ticket_evaluation.md"
    )
    assert summary["artifact_paths"]["adjudication"].endswith(
        "reports/support_ticket_adjudication.json"
    )
    assert summary["artifact_paths"]["summary"].endswith(
        "reports/support_ticket_run_summary.json"
    )
    assert _find_keys(summary, "abstention_rate") == []
    assert _find_keys(summary, "baseline_abstention_rate") == []
    assert _find_keys(summary, "candidate_abstention_rate") == []


def test_failing_report_includes_gate_details_and_human_review_recommendation() -> None:
    """Verify failing report includes gate details and human review recommendation."""
    result = run_evaluation(load_evaluation_config(CONFIG_PATH))
    failed_gate = result.gate_results[0].__class__(
        name=result.gate_results[0].name,
        passed=False,
        attribute="issue_category",
        baseline_accuracy=1.0,
        candidate_accuracy=0.5,
        accuracy_drop=0.5,
        threshold=0.0,
        message="issue_category accuracy drop 0.500 exceeds threshold 0.000.",
    )
    failed_result = result.__class__(
        status="FAILED",
        baseline_contract=result.baseline_contract,
        candidate_contract=result.candidate_contract,
        baseline_metrics=result.baseline_metrics,
        candidate_metrics=result.candidate_metrics,
        metric_comparisons=result.metric_comparisons,
        baseline_segment_metrics=result.baseline_segment_metrics,
        candidate_segment_metrics=result.candidate_segment_metrics,
        segment_metric_comparisons=result.segment_metric_comparisons,
        adjudication=result.adjudication,
        confidence_diagnostics=result.confidence_diagnostics,
        gate_results=(failed_gate,),
        report_path=result.report_path,
        adjudication_path=result.adjudication_path,
    )

    report = render_markdown_report(failed_result)

    assert "Overall status: **FAILED**" in report
    assert "issue_category accuracy drop 0.500 exceeds threshold 0.000." in report
    assert "Send the candidate to human review before promotion." in report


def test_report_includes_segment_regression_table(tmp_path: Path) -> None:
    """Verify report includes segment regression table."""
    config = _segment_config(tmp_path)
    result = run_evaluation(load_evaluation_config(config))

    report = render_markdown_report(result)

    assert "### Segment Regression Context" in report
    assert "customer_tier" in report
    assert "segment_max_accuracy_drop" in report


def test_run_summary_includes_segment_deltas_and_failed_segment_gates(
    tmp_path: Path,
) -> None:
    """Verify run summary includes segment deltas and failed segment gates."""
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate_with_updates(
        candidate_path,
        {
            "TKT-0001": {"predicted_urgency": "low"},
            "TKT-0004": {"predicted_urgency": "low"},
            "TKT-0010": {"predicted_urgency": "low"},
        },
    )
    config = _segment_config(tmp_path, candidate_path=candidate_path)

    summary = render_run_summary(run_evaluation(load_evaluation_config(config)))

    assert summary["segment_metric_deltas"][0]["segment_column"] == "customer_tier"
    assert summary["failed_segment_gates"][0]["name"] == "segment_max_accuracy_drop"
    assert summary["failed_segment_gates"][0]["segment_value"] == "enterprise"


def _segment_config(tmp_path: Path, candidate_path: Path | None = None) -> Path:
    """Support segment config."""
    data = json.loads(CONFIG_PATH.read_text())
    data["paths"].update(
        {
            "contract": str(ROOT / "contracts" / "support_ticket_output_contract.json"),
            "golden": str(ROOT / "data" / "golden" / "support_ticket_golden.csv"),
            "source": str(
                ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
            ),
            "baseline_output": str(
                ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"
            ),
            "candidate_output": str(
                candidate_path
                or ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
            ),
            "report": str(tmp_path / "report.md"),
            "adjudication": str(tmp_path / "adjudication.json"),
            "summary": str(tmp_path / "summary.json"),
        }
    )
    data["segment_columns"] = ["customer_tier"]
    data["segment_regression_gates"] = [
        {
            "attribute": "urgency",
            "segment_column": "customer_tier",
            "segment_value": "enterprise",
            "max_accuracy_drop": 0.0,
            "min_segment_size": 2,
        }
    ]

    config_path = tmp_path / "evaluation.json"
    config_path.write_text(json.dumps(data))
    return config_path


def _write_candidate_with_updates(
    path: Path,
    updates: dict[str, dict[str, str]],
) -> None:
    """Support write candidate with updates."""
    source_path = ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
    with source_path.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fieldnames = reader.fieldnames

    assert fieldnames is not None
    by_record_id = {row["record_id"]: row for row in rows}
    assert set(updates) <= set(by_record_id)
    for record_id, field_updates in updates.items():
        row = by_record_id[record_id]
        assert set(field_updates) <= set(row)
        row.update(field_updates)

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _find_keys(data: object, key: str) -> list[str]:
    """Support recursive key lookup."""
    matches: list[str] = []
    if isinstance(data, dict):
        for candidate_key, value in data.items():
            if candidate_key == key:
                matches.append(candidate_key)
            matches.extend(_find_keys(value, key))
    elif isinstance(data, list):
        for value in data:
            matches.extend(_find_keys(value, key))
    return matches
