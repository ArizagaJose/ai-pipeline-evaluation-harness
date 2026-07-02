"""Record-level candidate-vs-golden adjudication."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_data_harness.common import index_by_record_id, is_null, matches_type, safe_rate
from ai_data_harness.contracts import ContractColumn, OutputContract, ReviewOverride
from ai_data_harness.metrics import AttributeMapping

ALLOWED_OUTCOMES = ("correct", "incorrect", "abstained", "invalid", "missing")


@dataclass(frozen=True)
class AdjudicationRow:
    """Represent one adjudicated candidate cell."""

    record_id: str
    attribute: str
    expected_value: str | None
    candidate_value: str | None
    outcome: str
    accepted: bool
    requires_review: bool
    critical: bool
    review_severity: str | None
    reason: str


@dataclass(frozen=True)
class AdmissibilityMetrics:
    """Represent aggregate admissibility metrics for adjudicated cells."""

    total_cells: int
    critical_cells: int
    accepted_cells: int
    requires_review_cells: int
    correct_cells: int
    incorrect_cells: int
    abstained_cells: int
    invalid_cells: int
    missing_cells: int
    incorrect_accepted_cells: int
    critical_wrong_cells: int
    review_incorrect_cells: int
    accuracy: float
    abstention_rate: float
    invalid_rate: float
    false_acceptance_rate: float
    human_review_rate: float
    critical_wrong_rate: float
    review_incorrect_rate: float
    review_abstained_rate: float
    review_invalid_rate: float
    review_missing_rate: float


@dataclass(frozen=True)
class CriticalConfusionCount:
    """Represent a grouped count of wrong critical predictions."""

    attribute: str
    expected_value: str | None
    candidate_value: str | None
    count: int


@dataclass(frozen=True)
class SeverityReviewCount:
    """Represent a grouped count of severity-routed review cells."""

    attribute: str
    expected_value: str | None
    candidate_value: str | None
    severity: str
    reason: str
    count: int


@dataclass(frozen=True)
class AdjudicationResult:
    """Bundle adjudication rows, metrics, and grouped review counts."""

    adjudications: tuple[AdjudicationRow, ...]
    admissibility_metrics: AdmissibilityMetrics
    critical_confusions: tuple[CriticalConfusionCount, ...]
    severity_review_counts: tuple[SeverityReviewCount, ...]


def adjudicate_candidate(
    *,
    golden_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    attributes: tuple[AttributeMapping, ...],
    contract: OutputContract,
    record_id_column: str,
    abstention_column: str,
) -> AdjudicationResult:
    """Classify every configured candidate value against its golden value.

    Args:
        golden_rows: Golden reference rows.
        candidate_rows: Candidate rows to adjudicate.
        attributes: Attribute mappings to adjudicate.
        contract: Output contract containing column rules.
        record_id_column: Column used to align rows.
        abstention_column: Candidate row-level abstention column.

    Returns:
        Cell-level adjudication rows and aggregate admissibility metrics.

    Raises:
        ValueError: If attributes, record IDs, or referenced contract columns are
            invalid.
    """
    if not attributes:
        msg = "At least one attribute mapping is required."
        raise ValueError(msg)

    golden_by_id = index_by_record_id(golden_rows, record_id_column, "golden")
    candidate_by_id = index_by_record_id(candidate_rows, record_id_column, "candidate")
    column_by_name = {column.name: column for column in contract.columns}

    adjudications: list[AdjudicationRow] = []
    for record_id, golden_row in golden_by_id.items():
        candidate_row = candidate_by_id.get(record_id)
        for attribute in attributes:
            column = column_by_name.get(attribute.predicted_column)
            if column is None:
                msg = (
                    f"Attribute '{attribute.name}' references predicted column "
                    f"'{attribute.predicted_column}' that is not in the contract."
                )
                raise ValueError(msg)
            adjudications.append(
                _adjudicate_cell(
                    record_id=record_id,
                    attribute=attribute,
                    golden_row=golden_row,
                    candidate_row=candidate_row,
                    column=column,
                    abstention_column=abstention_column,
                )
            )

    adjudication_rows = tuple(adjudications)
    return AdjudicationResult(
        adjudications=adjudication_rows,
        admissibility_metrics=_compute_admissibility_metrics(adjudication_rows),
        critical_confusions=critical_confusion_counts(adjudication_rows),
        severity_review_counts=severity_review_counts(adjudication_rows),
    )


def write_adjudication_json(result: AdjudicationResult, path: str | Path) -> None:
    """Write adjudication rows and metrics as deterministic JSON.

    Args:
        result: Adjudication result to serialize.
        path: Destination JSON path.

    Raises:
        OSError: If the destination cannot be written.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "adjudications": [
                    asdict(adjudication) for adjudication in result.adjudications
                ],
                "admissibility_metrics": admissibility_metrics_json(
                    result.admissibility_metrics
                ),
                "critical_confusions": [
                    asdict(confusion) for confusion in result.critical_confusions
                ],
                "severity_review_counts": [
                    asdict(count) for count in result.severity_review_counts
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def admissibility_metrics_json(metrics: AdmissibilityMetrics) -> dict[str, int | float]:
    """Serialize admissibility metrics with explicit public metric names."""
    data = asdict(metrics)
    data["cell_level_abstention_rate"] = data.pop("abstention_rate")
    return data


def outcome_counts(adjudications: tuple[AdjudicationRow, ...]) -> dict[str, int]:
    """Count adjudication outcomes in deterministic key order.

    Args:
        adjudications: Cell-level adjudication rows.

    Returns:
        Outcome counts keyed by supported outcome name.
    """
    counts = dict.fromkeys(ALLOWED_OUTCOMES, 0)
    for adjudication in adjudications:
        counts[adjudication.outcome] = counts.get(adjudication.outcome, 0) + 1
    return counts


def critical_confusion_counts(
    adjudications: tuple[AdjudicationRow, ...],
) -> tuple[CriticalConfusionCount, ...]:
    """Summarize wrong critical predictions by expected and candidate value.

    Args:
        adjudications: Cell-level adjudication rows.

    Returns:
        Grouped critical confusion counts sorted for deterministic output.
    """
    counts: dict[tuple[str, str | None, str | None], int] = {}
    for adjudication in adjudications:
        if not adjudication.critical or adjudication.outcome != "incorrect":
            continue
        key = (
            adjudication.attribute,
            adjudication.expected_value,
            adjudication.candidate_value,
        )
        counts[key] = counts.get(key, 0) + 1

    return tuple(
        CriticalConfusionCount(
            attribute=attribute,
            expected_value=expected_value,
            candidate_value=candidate_value,
            count=count,
        )
        for (attribute, expected_value, candidate_value), count in sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0][0],
                item[0][1] or "",
                item[0][2] or "",
            ),
        )
    )


def severity_review_counts(
    adjudications: tuple[AdjudicationRow, ...],
) -> tuple[SeverityReviewCount, ...]:
    """Summarize cells routed or annotated by configured severity overrides.

    Args:
        adjudications: Cell-level adjudication rows.

    Returns:
        Grouped severity review counts sorted for deterministic output.
    """
    counts: dict[tuple[str, str | None, str | None, str, str], int] = {}
    for adjudication in adjudications:
        if adjudication.review_severity is None:
            continue
        key = (
            adjudication.attribute,
            adjudication.expected_value,
            adjudication.candidate_value,
            adjudication.review_severity,
            adjudication.reason,
        )
        counts[key] = counts.get(key, 0) + 1

    return tuple(
        SeverityReviewCount(
            attribute=attribute,
            expected_value=expected_value,
            candidate_value=candidate_value,
            severity=severity,
            reason=reason,
            count=count,
        )
        for (
            attribute,
            expected_value,
            candidate_value,
            severity,
            reason,
        ), count in sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                item[0][0],
                item[0][1] or "",
                item[0][2] or "",
                item[0][3],
                item[0][4],
            ),
        )
    )


def _adjudicate_cell(
    *,
    record_id: str,
    attribute: AttributeMapping,
    golden_row: dict[str, str],
    candidate_row: dict[str, str] | None,
    column: ContractColumn,
    abstention_column: str,
) -> AdjudicationRow:
    """Classify one candidate cell against its golden value and contract rules."""
    expected_value = golden_row.get(attribute.expected_column)

    if candidate_row is None or attribute.predicted_column not in candidate_row:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            None,
            "missing",
            accepted=False,
            requires_review=True,
            critical=column.critical,
            reason="candidate column or row is missing",
        )

    candidate_value = candidate_row.get(attribute.predicted_column)
    if is_null(candidate_value):
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "missing",
            accepted=False,
            requires_review=True,
            critical=column.critical,
            reason="candidate value is missing",
        )

    if candidate_row.get(abstention_column) == "true":
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "abstained",
            accepted=False,
            requires_review=True,
            critical=column.critical,
            reason="legacy row-level abstention is true",
        )

    if candidate_value in column.abstention_values:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "abstained",
            accepted=False,
            requires_review=True,
            critical=column.critical,
            reason="candidate value matches attribute abstention value",
        )

    invalid_reason = _invalid_reason(candidate_value, column)
    if invalid_reason is not None:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "invalid",
            accepted=False,
            requires_review=True,
            critical=column.critical,
            reason=invalid_reason,
        )

    if candidate_value == expected_value:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "correct",
            accepted=True,
            requires_review=False,
            critical=column.critical,
            reason="candidate value equals golden value",
        )

    review_override = _matching_review_override(
        column,
        expected_value=expected_value,
        candidate_value=candidate_value,
    )
    if column.critical:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "incorrect",
            accepted=False,
            requires_review=True,
            critical=True,
            review_severity=(
                review_override.severity if review_override is not None else None
            ),
            reason=(
                review_override.reason
                if review_override is not None
                else "critical attribute differs from golden value"
            ),
        )

    if review_override is not None:
        return _row(
            record_id,
            attribute.name,
            expected_value,
            candidate_value,
            "incorrect",
            accepted=False,
            requires_review=True,
            critical=False,
            review_severity=review_override.severity,
            reason=review_override.reason,
        )

    return _row(
        record_id,
        attribute.name,
        expected_value,
        candidate_value,
        "incorrect",
        accepted=True,
        requires_review=False,
        critical=False,
        reason="non-critical attribute differs from golden value",
    )


def _row(
    record_id: str,
    attribute: str,
    expected_value: str | None,
    candidate_value: str | None,
    outcome: str,
    *,
    accepted: bool,
    requires_review: bool,
    critical: bool,
    reason: str,
    review_severity: str | None = None,
) -> AdjudicationRow:
    """Build an adjudication row with consistent field ordering."""
    return AdjudicationRow(
        record_id=record_id,
        attribute=attribute,
        expected_value=expected_value,
        candidate_value=candidate_value,
        outcome=outcome,
        accepted=accepted,
        requires_review=requires_review,
        critical=critical,
        review_severity=review_severity,
        reason=reason,
    )


def _compute_admissibility_metrics(
    adjudications: tuple[AdjudicationRow, ...],
) -> AdmissibilityMetrics:
    """Compute aggregate admissibility metrics from adjudication rows."""
    total_cells = len(adjudications)
    critical_cells = sum(1 for adjudication in adjudications if adjudication.critical)
    correct_cells = _count(adjudications, "correct")
    incorrect_cells = _count(adjudications, "incorrect")
    abstained_cells = _count(adjudications, "abstained")
    invalid_cells = _count(adjudications, "invalid")
    missing_cells = _count(adjudications, "missing")
    accepted_cells = sum(1 for adjudication in adjudications if adjudication.accepted)
    requires_review_cells = sum(
        1 for adjudication in adjudications if adjudication.requires_review
    )
    incorrect_accepted_cells = sum(
        1
        for adjudication in adjudications
        if adjudication.outcome == "incorrect" and adjudication.accepted
    )
    critical_wrong_cells = sum(
        1
        for adjudication in adjudications
        if adjudication.outcome == "incorrect" and adjudication.critical
    )
    # Every "incorrect" cell is either accepted or review-routed (never both),
    # so the review-routed share is the complement of incorrect_accepted_cells.
    review_incorrect_cells = incorrect_cells - incorrect_accepted_cells

    return AdmissibilityMetrics(
        total_cells=total_cells,
        critical_cells=critical_cells,
        accepted_cells=accepted_cells,
        requires_review_cells=requires_review_cells,
        correct_cells=correct_cells,
        incorrect_cells=incorrect_cells,
        abstained_cells=abstained_cells,
        invalid_cells=invalid_cells,
        missing_cells=missing_cells,
        incorrect_accepted_cells=incorrect_accepted_cells,
        critical_wrong_cells=critical_wrong_cells,
        review_incorrect_cells=review_incorrect_cells,
        accuracy=safe_rate(correct_cells, total_cells),
        abstention_rate=safe_rate(abstained_cells, total_cells),
        invalid_rate=safe_rate(invalid_cells, total_cells),
        false_acceptance_rate=safe_rate(incorrect_accepted_cells, total_cells),
        human_review_rate=safe_rate(requires_review_cells, total_cells),
        critical_wrong_rate=safe_rate(critical_wrong_cells, critical_cells),
        review_incorrect_rate=safe_rate(review_incorrect_cells, requires_review_cells),
        review_abstained_rate=safe_rate(abstained_cells, requires_review_cells),
        review_invalid_rate=safe_rate(invalid_cells, requires_review_cells),
        review_missing_rate=safe_rate(missing_cells, requires_review_cells),
    )


def _count(adjudications: tuple[AdjudicationRow, ...], outcome: str) -> int:
    """Count adjudication rows with a matching outcome."""
    return sum(1 for adjudication in adjudications if adjudication.outcome == outcome)


def _invalid_reason(value: str, column: ContractColumn) -> str | None:
    """Return the contract validation reason for an invalid candidate value."""
    if not matches_type(value, column.data_type):
        return f"candidate value does not match {column.data_type} type"
    if column.allowed_values and value not in column.allowed_values:
        return "candidate value is not in allowed values"
    return None


def _matching_review_override(
    column: ContractColumn,
    *,
    expected_value: str | None,
    candidate_value: str,
) -> ReviewOverride | None:
    """Find the configured review override for an expected/candidate pair."""
    if expected_value is None:
        return None
    for review_override in column.review_overrides:
        if (
            review_override.expected_value == expected_value
            and review_override.candidate_value == candidate_value
        ):
            return review_override
    return None
