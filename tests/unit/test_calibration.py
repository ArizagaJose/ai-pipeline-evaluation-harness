"""Unit tests for confidence calibration diagnostics."""

import pytest

from ai_data_harness.adjudication import AdjudicationRow
from ai_data_harness.calibration import compute_confidence_diagnostics


def test_confidence_diagnostics_assign_boundary_values_to_fixed_buckets() -> None:
    """Verify confidence diagnostics assign boundary values to fixed buckets."""
    rows = [
        {"record_id": "r0", "model_confidence": "0.0"},
        {"record_id": "r1", "model_confidence": "0.5"},
        {"record_id": "r2", "model_confidence": "0.75"},
        {"record_id": "r3", "model_confidence": "0.9"},
        {"record_id": "r4", "model_confidence": "1.0"},
    ]
    adjudications = tuple(_adjudication(row["record_id"]) for row in rows)

    diagnostics = compute_confidence_diagnostics(
        candidate_rows=rows,
        adjudications=adjudications,
        record_id_column="record_id",
        confidence_column="model_confidence",
    )

    assert [(metric.bucket, metric.total_cells) for metric in diagnostics] == [
        ("0.00-0.50", 1),
        ("0.50-0.75", 1),
        ("0.75-0.90", 1),
        ("0.90-1.00", 2),
    ]


@pytest.mark.parametrize("value", ["-0.01", "1.01", "", "high"])
def test_confidence_diagnostics_reject_invalid_confidence_values(value: str) -> None:
    """Verify confidence diagnostics reject invalid confidence values."""
    with pytest.raises(ValueError, match="confidence"):
        compute_confidence_diagnostics(
            candidate_rows=[{"record_id": "r1", "model_confidence": value}],
            adjudications=(_adjudication("r1"),),
            record_id_column="record_id",
            confidence_column="model_confidence",
        )


def test_confidence_diagnostics_aggregate_cell_level_outcomes() -> None:
    """Verify confidence diagnostics aggregate cell level outcomes."""
    adjudications = (
        _adjudication("r1", attribute="issue_category", outcome="correct"),
        _adjudication("r1", attribute="product_area", outcome="abstained"),
        _adjudication(
            "r1",
            attribute="routing_team",
            outcome="incorrect",
            accepted=True,
        ),
        _adjudication(
            "r1",
            attribute="urgency",
            outcome="incorrect",
            accepted=False,
        ),
    )

    diagnostics = compute_confidence_diagnostics(
        candidate_rows=[{"record_id": "r1", "model_confidence": "0.8"}],
        adjudications=adjudications,
        record_id_column="record_id",
        confidence_column="model_confidence",
    )

    metric = next(metric for metric in diagnostics if metric.bucket == "0.75-0.90")
    assert metric.bucket == "0.75-0.90"
    assert metric.total_cells == 4
    assert metric.correct_cells == 1
    assert metric.abstained_cells == 1
    assert metric.false_acceptance_cells == 1
    assert metric.accuracy == 0.25
    assert metric.abstention_rate == 0.25
    assert metric.false_acceptance_rate == 0.25
    assert [(metric.bucket, metric.total_cells) for metric in diagnostics] == [
        ("0.00-0.50", 0),
        ("0.50-0.75", 0),
        ("0.75-0.90", 4),
        ("0.90-1.00", 0),
    ]


def _adjudication(
    record_id: str,
    *,
    attribute: str = "issue_category",
    outcome: str = "correct",
    accepted: bool = True,
) -> AdjudicationRow:
    """Support adjudication."""
    return AdjudicationRow(
        record_id=record_id,
        attribute=attribute,
        expected_value="billing",
        candidate_value="billing",
        outcome=outcome,
        accepted=accepted,
        requires_review=False,
        critical=False,
        review_severity=None,
        reason="test row",
    )
