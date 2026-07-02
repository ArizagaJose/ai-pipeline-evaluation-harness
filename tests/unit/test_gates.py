"""Unit tests for regression gate evaluation."""

import csv
from io import StringIO
from pathlib import Path

import pytest

from ai_data_harness.adjudication import (
    AdjudicationResult,
    AdmissibilityMetrics,
    SeverityReviewCount,
)
from ai_data_harness.config import (
    EvaluationConfigError,
    RegressionGateConfig,
    SegmentRegressionGateConfig,
    SeverityReviewGateConfig,
    load_evaluation_config,
)
from ai_data_harness.evaluation import run_evaluation
from ai_data_harness.gates import (
    evaluate_accuracy_gates,
    evaluate_segment_accuracy_gates,
    evaluate_severity_review_gates,
)
from ai_data_harness.metrics import AttributeMetrics, SegmentAttributeMetrics

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "examples" / "support_ticket_evaluation.json"


def test_sample_routes_critical_wrong_without_false_acceptance() -> None:
    """Verify sample routes critical wrong without false acceptance."""
    result = run_evaluation(load_evaluation_config(CONFIG_PATH))

    assert result.status == "NEEDS_REVIEW"
    assert result.adjudication is not None
    assert result.adjudication.admissibility_metrics.false_acceptance_rate == 0
    assert result.adjudication.admissibility_metrics.critical_wrong_cells > 0
    assert result.adjudication.admissibility_metrics.requires_review_cells > 0


def test_candidate_without_review_cells_passes(tmp_path: Path) -> None:
    """Verify candidate without review cells passes."""
    candidate_rows = _csv_lines_with_updates(
        ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv",
        {"TKT-0007": {"predicted_urgency": "critical"}},
    )
    config = _config_with_candidate(
        tmp_path,
        candidate_rows,
        golden_rows=_golden_rows_with_candidate_escalation_policy(),
    )

    result = run_evaluation(load_evaluation_config(config))

    assert result.status == "PASSED"
    assert result.passed is True
    assert result.adjudication is not None
    assert result.adjudication.admissibility_metrics.requires_review_cells == 0


def test_degraded_gated_attribute_fails(tmp_path: Path) -> None:
    """Verify degraded gated attribute fails."""
    config = _config_with_candidate(tmp_path, _candidate_rows_with_degraded_urgency())

    result = run_evaluation(load_evaluation_config(config))

    assert result.status == "FAILED"
    assert any(
        gate.attribute == "urgency" and not gate.passed for gate in result.gate_results
    )


def test_unknown_gate_attribute_raises_clear_config_error() -> None:
    """Verify unknown gate attribute raises clear config error."""
    metric = AttributeMetrics(
        attribute="known",
        total=1,
        correct=1,
        incorrect=0,
        abstained=0,
        accuracy=1.0,
        abstention_rate=0.0,
    )

    with pytest.raises(EvaluationConfigError, match="unknown attribute 'unknown'"):
        evaluate_accuracy_gates(
            baseline_metrics=(metric,),
            candidate_metrics=(metric,),
            gate_configs=(
                RegressionGateConfig(
                    attribute="unknown",
                    max_accuracy_drop=0.0,
                ),
            ),
        )


def test_critical_false_acceptance_gate_config_is_rejected(tmp_path: Path) -> None:
    """Verify critical false acceptance gate config is rejected."""
    config_path = tmp_path / "evaluation.json"
    config_path.write_text(
        (CONFIG_PATH)
        .read_text()
        .replace(
            '"max_false_acceptance_rate": 0.1',
            '"max_false_acceptance_rate": 0.1,\n'
            '  "max_critical_false_acceptance_rate": 0.0',
        )
    )

    with pytest.raises(
        EvaluationConfigError,
        match="max_critical_false_acceptance_rate.*no longer supported",
    ):
        load_evaluation_config(config_path)


def test_candidate_abstention_above_threshold_fails(tmp_path: Path) -> None:
    """Verify candidate abstention above threshold fails."""
    rows = _csv_lines_with_updates(
        ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv",
        {
            "TKT-0001": {"predicted_urgency": "low", "abstained": "true"},
            "TKT-0002": {"predicted_urgency": "low"},
            "TKT-0004": {"predicted_urgency": "low"},
            "TKT-0010": {"predicted_urgency": "low"},
        },
    )
    config = _config_with_candidate(tmp_path, rows, max_abstention_rate=0.0)

    result = run_evaluation(load_evaluation_config(config))

    assert result.status == "FAILED"
    assert any(
        gate.name == "max_candidate_abstention_rate" and not gate.passed
        for gate in result.gate_results
    )


def test_false_acceptance_gate_passes_at_configured_threshold(tmp_path: Path) -> None:
    """Verify false acceptance gate passes at configured threshold."""
    config = _config_with_candidate(
        tmp_path,
        _candidate_rows_with_degraded_product_area(),
        max_false_acceptance_rate=1.0,
    )

    result = run_evaluation(load_evaluation_config(config))

    assert any(
        gate.name == "max_false_acceptance_rate" and gate.passed
        for gate in result.gate_results
    )


def test_false_acceptance_gate_fails_at_configured_threshold(tmp_path: Path) -> None:
    """Verify false acceptance gate fails at configured threshold."""
    config = _config_with_candidate(
        tmp_path,
        _candidate_rows_with_degraded_product_area(),
        max_false_acceptance_rate=0.0,
    )

    result = run_evaluation(load_evaluation_config(config))

    assert any(
        gate.name == "max_false_acceptance_rate" and not gate.passed
        for gate in result.gate_results
    )


def test_severity_review_gate_passes_at_threshold() -> None:
    """Verify severity review gate passes at threshold."""
    results = evaluate_severity_review_gates(
        _adjudication_with_severity_counts({"high": 1}),
        (_severity_review_gate(severity="high", max_count=1),),
    )

    assert results[0].name == "max_severity_review_count"
    assert results[0].passed is True
    assert results[0].attribute == "severity=high"
    assert results[0].accuracy_drop == 1
    assert results[0].threshold == 1


def test_severity_review_gate_fails_when_count_exceeds_threshold() -> None:
    """Verify severity review gate fails when count exceeds threshold."""
    results = evaluate_severity_review_gates(
        _adjudication_with_severity_counts({"high": 2}),
        (_severity_review_gate(severity="high", max_count=1),),
    )

    assert results[0].passed is False
    assert results[0].accuracy_drop == 2
    assert "exceeds threshold 1" in results[0].message


def test_severity_review_gate_treats_missing_severity_as_zero() -> None:
    """Verify severity review gate treats missing severity as zero."""
    results = evaluate_severity_review_gates(
        _adjudication_with_severity_counts({"high": 1}),
        (_severity_review_gate(severity="critical", max_count=0),),
    )

    assert results[0].passed is True
    assert results[0].accuracy_drop == 0


def test_segment_accuracy_gate_passes_at_threshold() -> None:
    """Verify segment accuracy gate passes at threshold."""
    baseline = _segment_metric(accuracy=0.75, total=4)
    candidate = _segment_metric(accuracy=0.75, total=4)

    results = evaluate_segment_accuracy_gates(
        baseline_metrics=(baseline,),
        candidate_metrics=(candidate,),
        gate_configs=(_segment_gate(max_accuracy_drop=0.0),),
    )

    assert results[0].passed is True
    assert results[0].skipped is False
    assert results[0].accuracy_drop == 0.0


def test_segment_accuracy_gate_fails_when_segment_regresses() -> None:
    """Verify segment accuracy gate fails when segment regresses."""
    baseline = _segment_metric(accuracy=1.0, total=4)
    candidate = _segment_metric(accuracy=0.5, total=4)

    results = evaluate_segment_accuracy_gates(
        baseline_metrics=(baseline,),
        candidate_metrics=(candidate,),
        gate_configs=(_segment_gate(max_accuracy_drop=0.0),),
    )

    assert results[0].passed is False
    assert results[0].accuracy_drop == 0.5
    assert "customer_tier=enterprise" in results[0].message


def test_segment_accuracy_gate_skips_small_segments() -> None:
    """Verify segment accuracy gate skips small segments."""
    baseline = _segment_metric(accuracy=1.0, total=1)
    candidate = _segment_metric(accuracy=0.0, total=1)

    results = evaluate_segment_accuracy_gates(
        baseline_metrics=(baseline,),
        candidate_metrics=(candidate,),
        gate_configs=(_segment_gate(max_accuracy_drop=0.0, min_segment_size=2),),
    )

    assert results[0].passed is True
    assert results[0].skipped is True
    assert results[0].accuracy_drop is None


def _config_with_candidate(
    tmp_path: Path,
    candidate_rows: list[str],
    *,
    golden_rows: list[str] | None = None,
    max_abstention_rate: float = 0.1,
    max_false_acceptance_rate: float = 0.1,
) -> Path:
    """Support config with candidate."""
    golden_path = ROOT / "data" / "golden" / "support_ticket_golden.csv"
    if golden_rows is not None:
        golden_path = tmp_path / "golden.csv"
        golden_path.write_text("".join(golden_rows))

    candidate_path = tmp_path / "candidate.csv"
    candidate_path.write_text("".join(candidate_rows))
    report_path = tmp_path / "report.md"
    config_path = tmp_path / "evaluation.json"
    config_path.write_text(
        (ROOT / "examples" / "support_ticket_evaluation.json")
        .read_text()
        .replace(
            "../contracts/support_ticket_output_contract.json",
            str(ROOT / "contracts" / "support_ticket_output_contract.json"),
        )
        .replace(
            "../data/golden/support_ticket_golden.csv",
            str(golden_path),
        )
        .replace(
            "../data/runs/support_ticket_baseline_outputs.csv",
            str(ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"),
        )
        .replace(
            "../data/runs/support_ticket_candidate_outputs.csv",
            str(candidate_path),
        )
        .replace("../reports/support_ticket_evaluation.md", str(report_path))
        .replace(
            "../reports/support_ticket_adjudication.json",
            str(tmp_path / "adjudication.json"),
        )
        .replace(
            '"max_candidate_abstention_rate": 0.1',
            f'"max_candidate_abstention_rate": {max_abstention_rate}',
        )
        .replace(
            '"max_false_acceptance_rate": 0.1',
            f'"max_false_acceptance_rate": {max_false_acceptance_rate}',
        )
    )
    return config_path


def _candidate_rows_with_degraded_urgency() -> list[str]:
    """Support candidate rows with degraded urgency."""
    return _csv_lines_with_updates(
        ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv",
        {
            "TKT-0001": {"predicted_urgency": "low"},
            "TKT-0002": {"predicted_urgency": "low"},
            "TKT-0004": {"predicted_urgency": "low"},
            "TKT-0010": {"predicted_urgency": "low"},
        },
    )


def _candidate_rows_with_degraded_product_area() -> list[str]:
    """Support candidate rows with degraded product area."""
    return _csv_lines_with_updates(
        ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv",
        {"TKT-0001": {"predicted_product_area": "payments"}},
    )


def _golden_rows_with_candidate_escalation_policy() -> list[str]:
    """Support golden rows with candidate escalation policy."""
    return _csv_lines_with_updates(
        ROOT / "data" / "golden" / "support_ticket_golden.csv",
        {"TKT-0007": {"expected_should_escalate": "false"}},
    )


def _csv_lines_with_updates(
    path: Path,
    updates: dict[str, dict[str, str]],
) -> list[str]:
    """Support csv lines with updates."""
    with path.open(newline="") as file:
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

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().splitlines(keepends=True)


def _segment_metric(*, accuracy: float, total: int) -> SegmentAttributeMetrics:
    """Support segment metric."""
    correct = int(accuracy * total)
    return SegmentAttributeMetrics(
        segment_column="customer_tier",
        segment_value="enterprise",
        attribute="urgency",
        total=total,
        correct=correct,
        incorrect=total - correct,
        abstained=0,
        accuracy=accuracy,
        abstention_rate=0.0,
    )


def _segment_gate(
    *,
    max_accuracy_drop: float,
    min_segment_size: int = 1,
) -> SegmentRegressionGateConfig:
    """Support segment gate."""
    return SegmentRegressionGateConfig(
        attribute="urgency",
        segment_column="customer_tier",
        segment_value="enterprise",
        max_accuracy_drop=max_accuracy_drop,
        min_segment_size=min_segment_size,
    )


def _severity_review_gate(
    *,
    severity: str,
    max_count: int,
) -> SeverityReviewGateConfig:
    """Support severity review gate."""
    return SeverityReviewGateConfig(severity=severity, max_count=max_count)


def _adjudication_with_severity_counts(
    counts_by_severity: dict[str, int],
) -> AdjudicationResult:
    """Support adjudication with severity counts."""
    return AdjudicationResult(
        adjudications=(),
        admissibility_metrics=AdmissibilityMetrics(
            total_cells=0,
            critical_cells=0,
            accepted_cells=0,
            requires_review_cells=sum(counts_by_severity.values()),
            correct_cells=0,
            incorrect_cells=0,
            abstained_cells=0,
            invalid_cells=0,
            missing_cells=0,
            incorrect_accepted_cells=0,
            critical_wrong_cells=0,
            review_incorrect_cells=0,
            accuracy=0.0,
            abstention_rate=0.0,
            invalid_rate=0.0,
            false_acceptance_rate=0.0,
            human_review_rate=0.0,
            critical_wrong_rate=0.0,
            review_incorrect_rate=0.0,
            review_abstained_rate=0.0,
            review_invalid_rate=0.0,
            review_missing_rate=0.0,
        ),
        critical_confusions=(),
        severity_review_counts=tuple(
            SeverityReviewCount(
                attribute="product_area",
                expected_value="subscriptions",
                candidate_value="payments",
                severity=severity,
                reason="Configured review override.",
                count=count,
            )
            for severity, count in counts_by_severity.items()
        ),
    )
