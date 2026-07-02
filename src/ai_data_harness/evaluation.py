"""End-to-end local evaluation orchestration."""

from dataclasses import dataclass

from ai_data_harness.adjudication import AdjudicationResult, adjudicate_candidate
from ai_data_harness.calibration import (
    ConfidenceBucketMetrics,
    compute_confidence_diagnostics,
)
from ai_data_harness.config import EvaluationConfig
from ai_data_harness.contracts import (
    ContractValidationResult,
    ValidationIssue,
    load_contract,
    validate_rows,
)
from ai_data_harness.gates import (
    RegressionGateResult,
    evaluate_abstention_gate,
    evaluate_accuracy_gates,
    evaluate_false_acceptance_gate,
    evaluate_segment_accuracy_gates,
    evaluate_severity_review_gates,
)
from ai_data_harness.io import read_rows
from ai_data_harness.metrics import (
    AttributeMetrics,
    SegmentAttributeMetrics,
    compute_attribute_metrics,
    compute_segment_attribute_metrics,
)


@dataclass(frozen=True)
class MetricComparison:
    """Represent baseline and candidate metrics for one attribute."""

    attribute: str
    total: int
    baseline_accuracy: float
    candidate_accuracy: float
    accuracy_delta: float
    baseline_abstention_rate: float
    candidate_abstention_rate: float


@dataclass(frozen=True)
class SegmentMetricComparison:
    """Represent baseline and candidate metrics for one segment attribute."""

    segment_column: str
    segment_value: str
    attribute: str
    total: int
    baseline_accuracy: float
    candidate_accuracy: float
    accuracy_delta: float
    baseline_abstention_rate: float
    candidate_abstention_rate: float


@dataclass(frozen=True)
class EvaluationResult:
    """Represent all outputs from one evaluation run."""

    status: str
    baseline_contract: ContractValidationResult
    candidate_contract: ContractValidationResult
    baseline_metrics: tuple[AttributeMetrics, ...]
    candidate_metrics: tuple[AttributeMetrics, ...]
    metric_comparisons: tuple[MetricComparison, ...]
    baseline_segment_metrics: tuple[SegmentAttributeMetrics, ...]
    candidate_segment_metrics: tuple[SegmentAttributeMetrics, ...]
    segment_metric_comparisons: tuple[SegmentMetricComparison, ...]
    adjudication: AdjudicationResult | None
    confidence_diagnostics: tuple[ConfidenceBucketMetrics, ...]
    gate_results: tuple[RegressionGateResult, ...]
    report_path: str
    adjudication_path: str | None
    summary_path: str | None = None

    @property
    def passed(self) -> bool:
        """Return whether the evaluation status passed."""
        return self.status == "PASSED"


def run_evaluation(config: EvaluationConfig) -> EvaluationResult:
    """Run contract validation, metrics, and regression gates.

    Args:
        config: Validated evaluation run configuration.

    Returns:
        Complete evaluation result.

    Raises:
        ValueError: If configured data cannot be evaluated consistently.
        OSError: If configured inputs cannot be read.
    """
    contract = load_contract(config.contract_path)
    golden_rows = read_rows(config.golden_path)
    baseline_rows = read_rows(config.baseline_output_path)
    candidate_rows = read_rows(config.candidate_output_path)

    baseline_contract = validate_rows(baseline_rows, contract)
    candidate_contract = validate_rows(candidate_rows, contract)

    baseline_metrics: tuple[AttributeMetrics, ...] = ()
    candidate_metrics: tuple[AttributeMetrics, ...] = ()
    comparisons: tuple[MetricComparison, ...] = ()
    baseline_segment_metrics: tuple[SegmentAttributeMetrics, ...] = ()
    candidate_segment_metrics: tuple[SegmentAttributeMetrics, ...] = ()
    segment_comparisons: tuple[SegmentMetricComparison, ...] = ()
    gate_results: tuple[RegressionGateResult, ...] = ()
    adjudication: AdjudicationResult | None = None
    confidence_diagnostics: tuple[ConfidenceBucketMetrics, ...] = ()

    if _record_ids_are_usable(candidate_contract):
        adjudication = adjudicate_candidate(
            golden_rows=golden_rows,
            candidate_rows=candidate_rows,
            attributes=config.attributes,
            contract=contract,
            record_id_column=config.record_id_column,
            abstention_column=config.abstention_column,
        )

    if baseline_contract.passed and candidate_contract.passed:
        baseline_metrics = compute_attribute_metrics(
            golden_rows=golden_rows,
            output_rows=baseline_rows,
            attributes=list(config.attributes),
            record_id_column=config.record_id_column,
            abstention_column=config.abstention_column,
        )
        candidate_metrics = compute_attribute_metrics(
            golden_rows=golden_rows,
            output_rows=candidate_rows,
            attributes=list(config.attributes),
            record_id_column=config.record_id_column,
            abstention_column=config.abstention_column,
        )
        comparisons = compare_metrics(baseline_metrics, candidate_metrics)
        if config.segment_columns:
            if config.source_path is None:
                msg = "Config field 'paths.source' is required for segment metrics."
                raise ValueError(msg)
            source_rows = read_rows(config.source_path)
            baseline_segment_metrics = compute_segment_attribute_metrics(
                golden_rows=golden_rows,
                output_rows=baseline_rows,
                source_rows=source_rows,
                attributes=list(config.attributes),
                segment_columns=config.segment_columns,
                record_id_column=config.record_id_column,
                abstention_column=config.abstention_column,
            )
            candidate_segment_metrics = compute_segment_attribute_metrics(
                golden_rows=golden_rows,
                output_rows=candidate_rows,
                source_rows=source_rows,
                attributes=list(config.attributes),
                segment_columns=config.segment_columns,
                record_id_column=config.record_id_column,
                abstention_column=config.abstention_column,
            )
            segment_comparisons = compare_segment_metrics(
                baseline_segment_metrics,
                candidate_segment_metrics,
            )
        gate_results = (
            *evaluate_accuracy_gates(
                baseline_metrics,
                candidate_metrics,
                config.regression_gates,
            ),
            *evaluate_segment_accuracy_gates(
                baseline_segment_metrics,
                candidate_segment_metrics,
                config.segment_regression_gates,
            ),
            evaluate_abstention_gate(
                candidate_rows,
                abstention_column=config.abstention_column,
                max_candidate_abstention_rate=config.max_candidate_abstention_rate,
            ),
        )

    if adjudication is not None:
        if candidate_contract.passed:
            confidence_diagnostics = compute_confidence_diagnostics(
                candidate_rows=candidate_rows,
                adjudications=adjudication.adjudications,
                record_id_column=config.record_id_column,
                confidence_column=config.confidence_column,
            )
        if config.max_false_acceptance_rate is not None:
            gate_results = (
                *gate_results,
                evaluate_false_acceptance_gate(
                    adjudication.admissibility_metrics,
                    max_false_acceptance_rate=config.max_false_acceptance_rate,
                ),
            )
        if config.severity_review_gates:
            gate_results = (
                *gate_results,
                *evaluate_severity_review_gates(
                    adjudication,
                    config.severity_review_gates,
                ),
            )

    status = _evaluation_status(
        baseline_contract=baseline_contract,
        candidate_contract=candidate_contract,
        gate_results=gate_results,
        adjudication=adjudication,
    )

    return EvaluationResult(
        status=status,
        baseline_contract=baseline_contract,
        candidate_contract=candidate_contract,
        baseline_metrics=baseline_metrics,
        candidate_metrics=candidate_metrics,
        metric_comparisons=comparisons,
        baseline_segment_metrics=baseline_segment_metrics,
        candidate_segment_metrics=candidate_segment_metrics,
        segment_metric_comparisons=segment_comparisons,
        adjudication=adjudication,
        confidence_diagnostics=confidence_diagnostics,
        gate_results=gate_results,
        report_path=str(config.report_path),
        adjudication_path=(
            str(config.adjudication_path)
            if config.adjudication_path is not None
            else None
        ),
        summary_path=(
            str(config.summary_path) if config.summary_path is not None else None
        ),
    )


def compare_metrics(
    baseline_metrics: tuple[AttributeMetrics, ...],
    candidate_metrics: tuple[AttributeMetrics, ...],
) -> tuple[MetricComparison, ...]:
    """Compare baseline and candidate metrics by attribute.

    Args:
        baseline_metrics: Baseline attribute metrics.
        candidate_metrics: Candidate attribute metrics.

    Returns:
        Baseline-vs-candidate comparisons in baseline metric order.
    """
    candidate_by_attribute = {metric.attribute: metric for metric in candidate_metrics}
    comparisons: list[MetricComparison] = []

    for baseline in baseline_metrics:
        candidate = candidate_by_attribute[baseline.attribute]
        comparisons.append(
            MetricComparison(
                attribute=baseline.attribute,
                total=baseline.total,
                baseline_accuracy=baseline.accuracy,
                candidate_accuracy=candidate.accuracy,
                accuracy_delta=candidate.accuracy - baseline.accuracy,
                baseline_abstention_rate=baseline.abstention_rate,
                candidate_abstention_rate=candidate.abstention_rate,
            )
        )

    return tuple(comparisons)


def compare_segment_metrics(
    baseline_metrics: tuple[SegmentAttributeMetrics, ...],
    candidate_metrics: tuple[SegmentAttributeMetrics, ...],
) -> tuple[SegmentMetricComparison, ...]:
    """Compare baseline and candidate metrics by segment and attribute.

    Args:
        baseline_metrics: Baseline segment metrics.
        candidate_metrics: Candidate segment metrics.

    Returns:
        Baseline-vs-candidate segment comparisons in baseline metric order.
    """
    candidate_by_key = {
        (metric.segment_column, metric.segment_value, metric.attribute): metric
        for metric in candidate_metrics
    }
    comparisons: list[SegmentMetricComparison] = []

    for baseline in baseline_metrics:
        key = (baseline.segment_column, baseline.segment_value, baseline.attribute)
        candidate = candidate_by_key[key]
        comparisons.append(
            SegmentMetricComparison(
                segment_column=baseline.segment_column,
                segment_value=baseline.segment_value,
                attribute=baseline.attribute,
                total=baseline.total,
                baseline_accuracy=baseline.accuracy,
                candidate_accuracy=candidate.accuracy,
                accuracy_delta=candidate.accuracy - baseline.accuracy,
                baseline_abstention_rate=baseline.abstention_rate,
                candidate_abstention_rate=candidate.abstention_rate,
            )
        )

    return tuple(comparisons)


def _evaluation_status(
    *,
    baseline_contract: ContractValidationResult,
    candidate_contract: ContractValidationResult,
    gate_results: tuple[RegressionGateResult, ...],
    adjudication: AdjudicationResult | None,
) -> str:
    """Derive the final evaluation status from contracts, gates, and review routing."""
    gates_passed = (
        baseline_contract.passed
        and candidate_contract.passed
        and all(gate.passed for gate in gate_results)
        and bool(gate_results)
    )
    if not gates_passed:
        return "FAILED"
    if (
        adjudication is not None
        and adjudication.admissibility_metrics.requires_review_cells > 0
    ):
        return "NEEDS_REVIEW"
    return "PASSED"


def _record_ids_are_usable(validation: ContractValidationResult) -> bool:
    """Return whether candidate validation left record IDs usable for adjudication."""
    unusable_codes = {"duplicate_record_id", "empty_dataset", "missing_record_id"}
    return not any(_has_code(issue, unusable_codes) for issue in validation.issues)


def _has_code(issue: ValidationIssue, codes: set[str]) -> bool:
    """Return whether a validation issue has any matching code."""
    return issue.code in codes
