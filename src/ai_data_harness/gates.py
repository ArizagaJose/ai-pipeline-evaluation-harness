"""Regression gate evaluation."""

from dataclasses import dataclass

from ai_data_harness.adjudication import AdjudicationResult, AdmissibilityMetrics
from ai_data_harness.config import (
    EvaluationConfigError,
    RegressionGateConfig,
    SegmentRegressionGateConfig,
    SeverityReviewGateConfig,
)
from ai_data_harness.metrics import AttributeMetrics, SegmentAttributeMetrics


def _threshold_message(prefix: str, suffix: str, *, passed: bool) -> str:
    """Build a pass/fail threshold message from a prefix and threshold suffix."""
    verb = "is within threshold" if passed else "exceeds threshold"
    return f"{prefix} {verb} {suffix}"


@dataclass(frozen=True)
class RegressionGateResult:
    """Represent the outcome of one regression gate."""

    name: str
    passed: bool
    attribute: str | None
    baseline_accuracy: float | None
    candidate_accuracy: float | None
    accuracy_drop: float | None
    threshold: float
    message: str
    segment_column: str | None = None
    segment_value: str | None = None
    min_segment_size: int | None = None
    baseline_total: int | None = None
    candidate_total: int | None = None
    skipped: bool = False


def evaluate_accuracy_gates(
    baseline_metrics: tuple[AttributeMetrics, ...],
    candidate_metrics: tuple[AttributeMetrics, ...],
    gate_configs: tuple[RegressionGateConfig, ...],
) -> tuple[RegressionGateResult, ...]:
    """Evaluate per-attribute max accuracy drop gates.

    Args:
        baseline_metrics: Baseline attribute metrics.
        candidate_metrics: Candidate attribute metrics.
        gate_configs: Configured attribute regression gates.

    Returns:
        Gate results in configured gate order.

    Raises:
        EvaluationConfigError: If a gate references an unknown attribute.
    """
    baseline_by_attribute = _index_metrics(baseline_metrics, "baseline")
    candidate_by_attribute = _index_metrics(candidate_metrics, "candidate")
    results: list[RegressionGateResult] = []

    for gate in gate_configs:
        if gate.attribute not in baseline_by_attribute:
            msg = (
                f"Regression gate references unknown attribute '{gate.attribute}' "
                "in baseline metrics."
            )
            raise EvaluationConfigError(msg)
        if gate.attribute not in candidate_by_attribute:
            msg = (
                f"Regression gate references unknown attribute '{gate.attribute}' "
                "in candidate metrics."
            )
            raise EvaluationConfigError(msg)

        baseline = baseline_by_attribute[gate.attribute]
        candidate = candidate_by_attribute[gate.attribute]
        accuracy_drop = baseline.accuracy - candidate.accuracy
        passed = accuracy_drop <= gate.max_accuracy_drop
        message = _threshold_message(
            f"{gate.attribute} baseline-vs-candidate attribute regression "
            f"accuracy drop {accuracy_drop:.3f}",
            f"{gate.max_accuracy_drop:.3f}.",
            passed=passed,
        )
        results.append(
            RegressionGateResult(
                name="max_accuracy_drop",
                passed=passed,
                attribute=gate.attribute,
                baseline_accuracy=baseline.accuracy,
                candidate_accuracy=candidate.accuracy,
                accuracy_drop=accuracy_drop,
                threshold=gate.max_accuracy_drop,
                message=message,
            )
        )

    return tuple(results)


def evaluate_abstention_gate(
    candidate_rows: list[dict[str, str]],
    *,
    abstention_column: str,
    max_candidate_abstention_rate: float,
) -> RegressionGateResult:
    """Evaluate the configured candidate abstention-rate gate.

    Args:
        candidate_rows: Candidate rows to inspect.
        abstention_column: Candidate row-level abstention column.
        max_candidate_abstention_rate: Maximum allowed row-level abstention rate.

    Returns:
        Gate result for the candidate abstention rate.

    Raises:
        EvaluationConfigError: If candidate rows are empty.
    """
    if not candidate_rows:
        msg = "Candidate rows cannot be empty when evaluating abstention gate."
        raise EvaluationConfigError(msg)

    abstained = sum(1 for row in candidate_rows if row.get(abstention_column) == "true")
    abstention_rate = abstained / len(candidate_rows)
    passed = abstention_rate <= max_candidate_abstention_rate
    message = _threshold_message(
        f"row-level candidate abstention rate {abstention_rate:.3f}",
        f"{max_candidate_abstention_rate:.3f}.",
        passed=passed,
    )

    return RegressionGateResult(
        name="max_candidate_abstention_rate",
        passed=passed,
        attribute=None,
        baseline_accuracy=None,
        candidate_accuracy=None,
        accuracy_drop=None,
        threshold=max_candidate_abstention_rate,
        message=message,
    )


def evaluate_false_acceptance_gate(
    metrics: AdmissibilityMetrics,
    *,
    max_false_acceptance_rate: float,
) -> RegressionGateResult:
    """Evaluate the configured false-acceptance-rate gate.

    Args:
        metrics: Admissibility metrics from candidate adjudication.
        max_false_acceptance_rate: Maximum allowed false acceptance rate.

    Returns:
        Gate result for the false acceptance rate.
    """
    rate = metrics.false_acceptance_rate
    passed = rate <= max_false_acceptance_rate
    message = _threshold_message(
        f"adjudicated admissibility false_acceptance_rate {rate:.3f}",
        f"{max_false_acceptance_rate:.3f}.",
        passed=passed,
    )
    return RegressionGateResult(
        name="max_false_acceptance_rate",
        passed=passed,
        attribute=None,
        baseline_accuracy=None,
        candidate_accuracy=None,
        accuracy_drop=rate,
        threshold=max_false_acceptance_rate,
        message=message,
    )


def evaluate_severity_review_gates(
    adjudication: AdjudicationResult,
    gate_configs: tuple[SeverityReviewGateConfig, ...],
) -> tuple[RegressionGateResult, ...]:
    """Evaluate configured maximum severity-routed human review counts.

    Args:
        adjudication: Candidate adjudication result.
        gate_configs: Configured severity review count gates.

    Returns:
        Gate results in configured gate order.
    """
    counts_by_severity: dict[str, int] = {}
    for count in adjudication.severity_review_counts:
        counts_by_severity[count.severity] = (
            counts_by_severity.get(count.severity, 0) + count.count
        )

    results: list[RegressionGateResult] = []
    for gate in gate_configs:
        observed_count = counts_by_severity.get(gate.severity, 0)
        passed = observed_count <= gate.max_count
        subject = f"severity={gate.severity}"
        message = _threshold_message(
            f"{subject} severity-routed human review count {observed_count}",
            f"{gate.max_count}.",
            passed=passed,
        )
        results.append(
            RegressionGateResult(
                name="max_severity_review_count",
                passed=passed,
                attribute=subject,
                baseline_accuracy=None,
                candidate_accuracy=None,
                accuracy_drop=observed_count,
                threshold=gate.max_count,
                message=message,
            )
        )

    return tuple(results)


def evaluate_segment_accuracy_gates(
    baseline_metrics: tuple[SegmentAttributeMetrics, ...],
    candidate_metrics: tuple[SegmentAttributeMetrics, ...],
    gate_configs: tuple[SegmentRegressionGateConfig, ...],
) -> tuple[RegressionGateResult, ...]:
    """Evaluate configured max accuracy drop gates within source segments.

    Args:
        baseline_metrics: Baseline segment metrics.
        candidate_metrics: Candidate segment metrics.
        gate_configs: Configured segment regression gates.

    Returns:
        Gate results in configured gate order.

    Raises:
        EvaluationConfigError: If segment metrics contain duplicate keys.
    """
    baseline_by_key = _index_segment_metrics(baseline_metrics, "baseline")
    candidate_by_key = _index_segment_metrics(candidate_metrics, "candidate")
    results: list[RegressionGateResult] = []

    for gate in gate_configs:
        key = (gate.segment_column, gate.segment_value, gate.attribute)
        baseline = baseline_by_key.get(key)
        candidate = candidate_by_key.get(key)
        baseline_total = baseline.total if baseline is not None else 0
        candidate_total = candidate.total if candidate is not None else 0

        if (
            baseline is None
            or candidate is None
            or baseline_total < gate.min_segment_size
            or candidate_total < gate.min_segment_size
        ):
            observed_total = min(baseline_total, candidate_total)
            results.append(
                RegressionGateResult(
                    name="segment_max_accuracy_drop",
                    passed=True,
                    attribute=gate.attribute,
                    baseline_accuracy=(
                        baseline.accuracy if baseline is not None else None
                    ),
                    candidate_accuracy=(
                        candidate.accuracy if candidate is not None else None
                    ),
                    accuracy_drop=None,
                    threshold=gate.max_accuracy_drop,
                    message=(
                        f"{gate.attribute} baseline-vs-candidate segment "
                        f"regression gate for {gate.segment_column}="
                        f"{gate.segment_value} skipped because segment size "
                        f"{observed_total} is below minimum {gate.min_segment_size}."
                    ),
                    segment_column=gate.segment_column,
                    segment_value=gate.segment_value,
                    min_segment_size=gate.min_segment_size,
                    baseline_total=baseline_total,
                    candidate_total=candidate_total,
                    skipped=True,
                )
            )
            continue

        accuracy_drop = baseline.accuracy - candidate.accuracy
        passed = accuracy_drop <= gate.max_accuracy_drop
        segment_label = f"{gate.segment_column}={gate.segment_value}"
        message = _threshold_message(
            f"{gate.attribute} baseline-vs-candidate segment regression "
            f"accuracy drop {accuracy_drop:.3f} for segment {segment_label}",
            f"{gate.max_accuracy_drop:.3f}.",
            passed=passed,
        )
        results.append(
            RegressionGateResult(
                name="segment_max_accuracy_drop",
                passed=passed,
                attribute=gate.attribute,
                baseline_accuracy=baseline.accuracy,
                candidate_accuracy=candidate.accuracy,
                accuracy_drop=accuracy_drop,
                threshold=gate.max_accuracy_drop,
                message=message,
                segment_column=gate.segment_column,
                segment_value=gate.segment_value,
                min_segment_size=gate.min_segment_size,
                baseline_total=baseline.total,
                candidate_total=candidate.total,
            )
        )

    return tuple(results)


def _index_metrics(
    metrics: tuple[AttributeMetrics, ...],
    dataset_name: str,
) -> dict[str, AttributeMetrics]:
    """Index attribute metrics and reject duplicate attributes."""
    indexed: dict[str, AttributeMetrics] = {}
    for metric in metrics:
        if metric.attribute in indexed:
            msg = (
                f"{dataset_name} metrics contain duplicate attribute "
                f"'{metric.attribute}'."
            )
            raise EvaluationConfigError(msg)
        indexed[metric.attribute] = metric
    return indexed


def _index_segment_metrics(
    metrics: tuple[SegmentAttributeMetrics, ...],
    dataset_name: str,
) -> dict[tuple[str, str, str], SegmentAttributeMetrics]:
    """Index segment metrics and reject duplicate segment keys."""
    indexed: dict[tuple[str, str, str], SegmentAttributeMetrics] = {}
    for metric in metrics:
        key = (metric.segment_column, metric.segment_value, metric.attribute)
        if key in indexed:
            msg = (
                f"{dataset_name} segment metrics contain duplicate key "
                f"'{metric.segment_column}={metric.segment_value}' for "
                f"attribute '{metric.attribute}'."
            )
            raise EvaluationConfigError(msg)
        indexed[key] = metric
    return indexed
