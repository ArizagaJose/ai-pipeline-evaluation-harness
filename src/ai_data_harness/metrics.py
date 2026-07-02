"""Attribute-level metrics for AI-generated analytical outputs."""

from collections.abc import Iterable
from dataclasses import dataclass

from ai_data_harness.common import index_by_record_id


@dataclass(frozen=True)
class AttributeMapping:
    """Map a logical attribute to golden and output columns."""

    name: str
    expected_column: str
    predicted_column: str


@dataclass(frozen=True)
class AttributeMetrics:
    """Represent aggregate metrics for one attribute."""

    attribute: str
    total: int
    correct: int
    incorrect: int
    abstained: int
    accuracy: float
    abstention_rate: float


@dataclass(frozen=True)
class SegmentAttributeMetrics:
    """Represent aggregate metrics for one attribute within a segment."""

    segment_column: str
    segment_value: str
    attribute: str
    total: int
    correct: int
    incorrect: int
    abstained: int
    accuracy: float
    abstention_rate: float


def compute_attribute_metrics(
    golden_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    attributes: list[AttributeMapping],
    *,
    record_id_column: str = "record_id",
    abstention_column: str = "abstained",
) -> tuple[AttributeMetrics, ...]:
    """Compute deterministic quality metrics for each mapped attribute.

    Scoring is sample-level: only records present in the golden rows are
    scored. Output rows without a golden label are ignored here, but every
    golden record ID must be covered by the output rows.

    Args:
        golden_rows: Golden reference rows.
        output_rows: Output rows to score against the golden rows.
        attributes: Attribute mappings to evaluate.
        record_id_column: Column used to align rows across datasets.
        abstention_column: Output column that marks row-level abstention.

    Returns:
        Attribute-level metrics in configured attribute order.

    Raises:
        ValueError: If inputs are empty, duplicated, or do not cover the
            golden record IDs.
    """
    if not attributes:
        msg = "At least one attribute mapping is required."
        raise ValueError(msg)

    golden_by_id = index_by_record_id(golden_rows, record_id_column, "golden")
    output_by_id = index_by_record_id(output_rows, record_id_column, "output")
    _require_golden_coverage(golden_by_id, output_by_id, "output")

    metrics: list[AttributeMetrics] = []
    for attribute in attributes:
        correct, abstained = _score_attribute(
            golden_by_id.keys(),
            golden_by_id,
            output_by_id,
            attribute,
            abstention_column,
        )

        total = len(golden_by_id)
        incorrect = total - correct
        metrics.append(
            AttributeMetrics(
                attribute=attribute.name,
                total=total,
                correct=correct,
                incorrect=incorrect,
                abstained=abstained,
                accuracy=correct / total,
                abstention_rate=abstained / total,
            )
        )

    return tuple(metrics)


def compute_segment_attribute_metrics(
    golden_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    attributes: list[AttributeMapping],
    segment_columns: tuple[str, ...],
    *,
    record_id_column: str = "record_id",
    abstention_column: str = "abstained",
) -> tuple[SegmentAttributeMetrics, ...]:
    """Compute attribute metrics within configured source-data segments.

    Scoring is sample-level: only records present in the golden rows are
    scored and grouped into segments. Output and source rows without a golden
    label are ignored here, but every golden record ID must be covered by
    both the output rows and the source rows.

    Args:
        golden_rows: Golden reference rows.
        output_rows: Output rows to score against the golden rows.
        source_rows: Source rows containing segment columns.
        attributes: Attribute mappings to evaluate.
        segment_columns: Source columns used to form segment groups.
        record_id_column: Column used to align rows across datasets.
        abstention_column: Output column that marks row-level abstention.

    Returns:
        Segment metrics grouped by segment column, segment value, and attribute.

    Raises:
        ValueError: If record IDs are unusable or segment data is missing.
    """
    if not segment_columns:
        return ()
    if not attributes:
        msg = "At least one attribute mapping is required."
        raise ValueError(msg)

    golden_by_id = index_by_record_id(golden_rows, record_id_column, "golden")
    output_by_id = index_by_record_id(output_rows, record_id_column, "output")
    source_by_id = index_by_record_id(source_rows, record_id_column, "source")
    _require_golden_coverage(golden_by_id, output_by_id, "output")
    _require_golden_coverage(golden_by_id, source_by_id, "source")
    source_by_id = {record_id: source_by_id[record_id] for record_id in golden_by_id}

    for segment_column in segment_columns:
        for record_id, source_row in source_by_id.items():
            if segment_column not in source_row or not source_row[segment_column]:
                msg = (
                    f"source row for record ID '{record_id}' is missing "
                    f"segment column '{segment_column}'."
                )
                raise ValueError(msg)

    metrics: list[SegmentAttributeMetrics] = []
    for segment_column in segment_columns:
        segment_values = sorted(
            {source_row[segment_column] for source_row in source_by_id.values()}
        )
        for segment_value in segment_values:
            record_ids = [
                record_id
                for record_id, source_row in source_by_id.items()
                if source_row[segment_column] == segment_value
            ]
            for attribute in attributes:
                correct, abstained = _score_attribute(
                    record_ids,
                    golden_by_id,
                    output_by_id,
                    attribute,
                    abstention_column,
                )

                total = len(record_ids)
                metrics.append(
                    SegmentAttributeMetrics(
                        segment_column=segment_column,
                        segment_value=segment_value,
                        attribute=attribute.name,
                        total=total,
                        correct=correct,
                        incorrect=total - correct,
                        abstained=abstained,
                        accuracy=correct / total,
                        abstention_rate=abstained / total,
                    )
                )

    return tuple(metrics)


def _require_golden_coverage(
    golden_by_id: dict[str, dict[str, str]],
    other_by_id: dict[str, dict[str, str]],
    dataset_name: str,
) -> None:
    """Require every golden record ID to be present in another dataset."""
    missing = sorted(set(golden_by_id) - set(other_by_id))
    if missing:
        preview = ", ".join(missing[:5])
        msg = (
            f"{dataset_name} rows are missing {len(missing)} golden record "
            f"ID(s): {preview}."
        )
        raise ValueError(msg)


def _score_attribute(
    record_ids: Iterable[str],
    golden_by_id: dict[str, dict[str, str]],
    output_by_id: dict[str, dict[str, str]],
    attribute: AttributeMapping,
    abstention_column: str,
) -> tuple[int, int]:
    """Count correct and abstained outcomes for one attribute over record IDs."""
    correct = 0
    abstained = 0
    for record_id in record_ids:
        golden_row = golden_by_id[record_id]
        output_row = output_by_id[record_id]
        if output_row.get(abstention_column) == "true":
            abstained += 1
        if golden_row.get(attribute.expected_column) == output_row.get(
            attribute.predicted_column
        ):
            correct += 1
    return correct, abstained
