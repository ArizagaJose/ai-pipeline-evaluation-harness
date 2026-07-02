"""Unit tests for attribute and segment metric computation."""

import csv
from pathlib import Path

import pytest

from ai_data_harness.metrics import (
    AttributeMapping,
    compute_attribute_metrics,
    compute_segment_attribute_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "data" / "golden" / "support_ticket_golden.csv"
BASELINE_PATH = ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"
CANDIDATE_PATH = ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
SOURCE_PATH = ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"

SUPPORT_TICKET_ATTRIBUTES = [
    AttributeMapping(
        name="issue_category",
        expected_column="expected_issue_category",
        predicted_column="predicted_issue_category",
    ),
    AttributeMapping(
        name="product_area",
        expected_column="expected_product_area",
        predicted_column="predicted_product_area",
    ),
    AttributeMapping(
        name="urgency",
        expected_column="expected_urgency",
        predicted_column="predicted_urgency",
    ),
    AttributeMapping(
        name="routing_team",
        expected_column="expected_routing_team",
        predicted_column="predicted_routing_team",
    ),
    AttributeMapping(
        name="should_escalate",
        expected_column="expected_should_escalate",
        predicted_column="predicted_should_escalate",
    ),
]


def read_rows(path: Path) -> list[dict[str, str]]:
    """Support read rows."""
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def metrics_by_attribute(path: Path) -> dict[str, tuple[int, int, float]]:
    """Support metrics by attribute."""
    metrics = compute_attribute_metrics(
        golden_rows=read_rows(GOLDEN_PATH),
        output_rows=read_rows(path),
        attributes=SUPPORT_TICKET_ATTRIBUTES,
    )
    return {
        metric.attribute: (metric.correct, metric.incorrect, metric.accuracy)
        for metric in metrics
    }


def test_baseline_attribute_metrics_are_computed_against_golden() -> None:
    """Verify baseline attribute metrics are computed against golden."""
    metrics = metrics_by_attribute(BASELINE_PATH)

    assert metrics == {
        "issue_category": (11, 1, 11 / 12),
        "product_area": (11, 1, 11 / 12),
        "urgency": (8, 4, 8 / 12),
        "routing_team": (10, 2, 10 / 12),
        "should_escalate": (11, 1, 11 / 12),
    }


def test_candidate_attribute_metrics_are_computed_against_golden() -> None:
    """Verify candidate attribute metrics are computed against golden."""
    metrics = metrics_by_attribute(CANDIDATE_PATH)

    assert metrics == {
        "issue_category": (12, 0, 1.0),
        "product_area": (12, 0, 1.0),
        "urgency": (11, 1, 11 / 12),
        "routing_team": (12, 0, 1.0),
        "should_escalate": (11, 1, 11 / 12),
    }


def test_abstention_rate_is_computed_per_attribute() -> None:
    """Verify abstention rate is computed per attribute."""
    output_rows = read_rows(CANDIDATE_PATH)
    output_rows[0]["abstained"] = "true"

    metrics = compute_attribute_metrics(
        golden_rows=read_rows(GOLDEN_PATH),
        output_rows=output_rows,
        attributes=[SUPPORT_TICKET_ATTRIBUTES[0]],
    )

    assert metrics[0].abstained == 1
    assert metrics[0].abstention_rate == 1 / 12


def test_attribute_metrics_match_records_by_id_not_row_position() -> None:
    """Verify attribute metrics match records by id not row position."""
    metrics = compute_attribute_metrics(
        golden_rows=[
            {"record_id": "R2", "expected_value": "bravo"},
            {"record_id": "R1", "expected_value": "alpha"},
        ],
        output_rows=[
            {"record_id": "R1", "predicted_value": "alpha", "abstained": "false"},
            {"record_id": "R2", "predicted_value": "charlie", "abstained": "true"},
        ],
        attributes=[
            AttributeMapping(
                name="value",
                expected_column="expected_value",
                predicted_column="predicted_value",
            )
        ],
    )

    assert metrics[0].correct == 1
    assert metrics[0].incorrect == 1
    assert metrics[0].abstained == 1
    assert metrics[0].accuracy == 0.5


def test_metric_computation_requires_golden_coverage() -> None:
    """Verify metric computation rejects outputs missing golden record ids."""
    output_rows = read_rows(CANDIDATE_PATH)
    output_rows[0]["record_id"] = "TKT-9999"

    with pytest.raises(ValueError, match="missing 1 golden record ID"):
        compute_attribute_metrics(
            golden_rows=read_rows(GOLDEN_PATH),
            output_rows=output_rows,
            attributes=SUPPORT_TICKET_ATTRIBUTES,
        )


def test_metric_computation_ignores_unlabeled_output_rows() -> None:
    """Verify extra output rows without golden labels are not scored."""
    golden_rows = read_rows(GOLDEN_PATH)
    output_rows = read_rows(CANDIDATE_PATH)
    extra_row = dict(output_rows[0])
    extra_row["record_id"] = "TKT-9999"
    extra_row["predicted_urgency"] = "critical"

    full_sample = compute_attribute_metrics(
        golden_rows=golden_rows,
        output_rows=output_rows,
        attributes=SUPPORT_TICKET_ATTRIBUTES,
    )
    with_extra = compute_attribute_metrics(
        golden_rows=golden_rows,
        output_rows=[*output_rows, extra_row],
        attributes=SUPPORT_TICKET_ATTRIBUTES,
    )

    assert with_extra == full_sample
    assert all(metric.total == len(golden_rows) for metric in with_extra)


def test_metric_computation_rejects_duplicate_record_ids() -> None:
    """Verify metric computation rejects duplicate record ids."""
    output_rows = read_rows(CANDIDATE_PATH)
    output_rows[1]["record_id"] = output_rows[0]["record_id"]

    with pytest.raises(ValueError, match="duplicate record ID"):
        compute_attribute_metrics(
            golden_rows=read_rows(GOLDEN_PATH),
            output_rows=output_rows,
            attributes=SUPPORT_TICKET_ATTRIBUTES,
        )


def test_segment_metrics_are_computed_per_attribute_and_segment() -> None:
    """Verify segment metrics are computed per attribute and segment."""
    metrics = compute_segment_attribute_metrics(
        golden_rows=read_rows(GOLDEN_PATH),
        output_rows=read_rows(BASELINE_PATH),
        source_rows=read_rows(SOURCE_PATH),
        attributes=SUPPORT_TICKET_ATTRIBUTES,
        segment_columns=("customer_tier", "region"),
    )
    by_key = {
        (metric.segment_column, metric.segment_value, metric.attribute): metric
        for metric in metrics
    }

    enterprise_urgency = by_key[("customer_tier", "enterprise", "urgency")]
    na_routing = by_key[("region", "na", "routing_team")]

    assert enterprise_urgency.total == 4
    assert enterprise_urgency.correct == 2
    assert enterprise_urgency.incorrect == 2
    assert enterprise_urgency.accuracy == 0.5
    assert na_routing.total == 5
    assert na_routing.correct == 5
    assert na_routing.accuracy == 1.0


def test_segment_metrics_match_source_records_by_id_not_row_position() -> None:
    """Verify segment metrics match source records by id not row position."""
    metrics = compute_segment_attribute_metrics(
        golden_rows=[
            {"record_id": "R2", "expected_value": "bravo"},
            {"record_id": "R1", "expected_value": "alpha"},
        ],
        output_rows=[
            {"record_id": "R1", "predicted_value": "alpha", "abstained": "false"},
            {"record_id": "R2", "predicted_value": "charlie", "abstained": "false"},
        ],
        source_rows=[
            {"record_id": "R1", "tier": "enterprise"},
            {"record_id": "R2", "tier": "self_serve"},
        ],
        attributes=[
            AttributeMapping(
                name="value",
                expected_column="expected_value",
                predicted_column="predicted_value",
            )
        ],
        segment_columns=("tier",),
    )
    by_segment = {metric.segment_value: metric for metric in metrics}

    assert by_segment["enterprise"].correct == 1
    assert by_segment["self_serve"].correct == 0


def test_segment_metrics_reject_missing_source_record_ids() -> None:
    """Verify segment metrics reject source rows missing golden record ids."""
    source_rows = read_rows(SOURCE_PATH)
    source_rows.pop()

    with pytest.raises(ValueError, match="missing 1 golden record ID"):
        compute_segment_attribute_metrics(
            golden_rows=read_rows(GOLDEN_PATH),
            output_rows=read_rows(BASELINE_PATH),
            source_rows=source_rows,
            attributes=SUPPORT_TICKET_ATTRIBUTES,
            segment_columns=("customer_tier",),
        )


def test_segment_metrics_ignore_unlabeled_rows() -> None:
    """Verify segment metrics ignore output and source rows without labels."""
    golden_rows = read_rows(GOLDEN_PATH)
    output_rows = read_rows(BASELINE_PATH)
    source_rows = read_rows(SOURCE_PATH)
    extra_output = dict(output_rows[0])
    extra_output["record_id"] = "TKT-9999"
    extra_source = dict(source_rows[0])
    extra_source["record_id"] = "TKT-9999"
    extra_source["customer_tier"] = "unseen_tier"

    full_sample = compute_segment_attribute_metrics(
        golden_rows=golden_rows,
        output_rows=output_rows,
        source_rows=source_rows,
        attributes=SUPPORT_TICKET_ATTRIBUTES,
        segment_columns=("customer_tier",),
    )
    with_extra = compute_segment_attribute_metrics(
        golden_rows=golden_rows,
        output_rows=[*output_rows, extra_output],
        source_rows=[*source_rows, extra_source],
        attributes=SUPPORT_TICKET_ATTRIBUTES,
        segment_columns=("customer_tier",),
    )

    assert with_extra == full_sample
    assert all(metric.segment_value != "unseen_tier" for metric in with_extra)


def test_segment_metrics_reject_duplicate_source_record_ids() -> None:
    """Verify segment metrics reject duplicate source record ids."""
    source_rows = read_rows(SOURCE_PATH)
    source_rows[1]["record_id"] = source_rows[0]["record_id"]

    with pytest.raises(ValueError, match="duplicate record ID"):
        compute_segment_attribute_metrics(
            golden_rows=read_rows(GOLDEN_PATH),
            output_rows=read_rows(BASELINE_PATH),
            source_rows=source_rows,
            attributes=SUPPORT_TICKET_ATTRIBUTES,
            segment_columns=("customer_tier",),
        )


def test_segment_metrics_count_row_level_abstention_in_segment_totals() -> None:
    """Verify segment metrics count row level abstention in segment totals."""
    output_rows = read_rows(BASELINE_PATH)
    output_rows[0]["abstained"] = "true"

    metrics = compute_segment_attribute_metrics(
        golden_rows=read_rows(GOLDEN_PATH),
        output_rows=output_rows,
        source_rows=read_rows(SOURCE_PATH),
        attributes=[SUPPORT_TICKET_ATTRIBUTES[0]],
        segment_columns=("customer_tier",),
    )
    enterprise = next(
        metric
        for metric in metrics
        if metric.segment_column == "customer_tier"
        and metric.segment_value == "enterprise"
        and metric.attribute == "issue_category"
    )

    assert enterprise.total == 4
    assert enterprise.abstained == 1
    assert enterprise.abstention_rate == 0.25
