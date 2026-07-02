"""Diagnostic confidence bucket summaries for candidate outputs."""

from dataclasses import dataclass

from ai_data_harness.adjudication import AdjudicationRow
from ai_data_harness.common import index_by_record_id, is_null, safe_rate


@dataclass(frozen=True)
class ConfidenceBucketMetrics:
    """Represent adjudication metrics for one confidence bucket."""

    bucket: str
    total_cells: int
    correct_cells: int
    abstained_cells: int
    false_acceptance_cells: int
    accuracy: float
    abstention_rate: float
    false_acceptance_rate: float


_BUCKETS = (
    ("0.00-0.50", 0.0, 0.5, False),
    ("0.50-0.75", 0.5, 0.75, False),
    ("0.75-0.90", 0.75, 0.9, False),
    ("0.90-1.00", 0.9, 1.0, True),
)


def compute_confidence_diagnostics(
    candidate_rows: list[dict[str, str]],
    adjudications: tuple[AdjudicationRow, ...],
    record_id_column: str,
    confidence_column: str,
) -> tuple[ConfidenceBucketMetrics, ...]:
    """Aggregate adjudicated candidate cells by row-level confidence bucket.

    Args:
        candidate_rows: Candidate rows containing confidence values.
        adjudications: Cell-level adjudication rows to aggregate.
        record_id_column: Candidate row ID column.
        confidence_column: Candidate confidence column.

    Returns:
        Metrics for each configured confidence bucket.

    Raises:
        ValueError: If confidence values are missing, non-numeric, or out of range.
    """
    candidate_by_id = index_by_record_id(candidate_rows, record_id_column, "candidate")
    counters = {
        bucket: {
            "total_cells": 0,
            "correct_cells": 0,
            "abstained_cells": 0,
            "false_acceptance_cells": 0,
        }
        for bucket, *_ in _BUCKETS
    }

    for adjudication in adjudications:
        candidate_row = candidate_by_id.get(adjudication.record_id)
        if candidate_row is None:
            msg = (
                "Cannot compute confidence diagnostics because candidate row "
                f"'{adjudication.record_id}' is missing."
            )
            raise ValueError(msg)

        confidence = _parse_confidence(
            candidate_row.get(confidence_column),
            record_id=adjudication.record_id,
            confidence_column=confidence_column,
        )
        bucket = _confidence_bucket(confidence)
        counters[bucket]["total_cells"] += 1
        if adjudication.outcome == "correct":
            counters[bucket]["correct_cells"] += 1
        if adjudication.outcome == "abstained":
            counters[bucket]["abstained_cells"] += 1
        if adjudication.outcome == "incorrect" and adjudication.accepted:
            counters[bucket]["false_acceptance_cells"] += 1

    return tuple(
        ConfidenceBucketMetrics(
            bucket=bucket,
            total_cells=counts["total_cells"],
            correct_cells=counts["correct_cells"],
            abstained_cells=counts["abstained_cells"],
            false_acceptance_cells=counts["false_acceptance_cells"],
            accuracy=safe_rate(counts["correct_cells"], counts["total_cells"]),
            abstention_rate=safe_rate(
                counts["abstained_cells"],
                counts["total_cells"],
            ),
            false_acceptance_rate=safe_rate(
                counts["false_acceptance_cells"],
                counts["total_cells"],
            ),
        )
        for bucket, counts in counters.items()
    )


def _confidence_bucket(confidence: float) -> str:
    """Return the configured bucket label for a confidence value."""
    for bucket, lower, upper, upper_inclusive in _BUCKETS:
        if confidence >= lower and (
            confidence < upper or (upper_inclusive and confidence <= upper)
        ):
            return bucket

    msg = f"Confidence value {confidence} is outside the supported range 0 to 1."
    raise ValueError(msg)


def _parse_confidence(
    value: str | None,
    *,
    record_id: str,
    confidence_column: str,
) -> float:
    """Parse and validate a row-level confidence value."""
    if is_null(value):
        msg = (
            f"Candidate row '{record_id}' has missing confidence value in "
            f"column '{confidence_column}'."
        )
        raise ValueError(msg)

    try:
        confidence = float(value)
    except ValueError as exc:
        msg = (
            f"Candidate row '{record_id}' has non-numeric confidence value "
            f"{value!r} in column '{confidence_column}'."
        )
        raise ValueError(msg) from exc

    if confidence < 0 or confidence > 1:
        msg = (
            f"Candidate row '{record_id}' has confidence value {value!r} outside "
            f"the supported range 0 to 1 in column '{confidence_column}'."
        )
        raise ValueError(msg)
    return confidence
