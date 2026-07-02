"""Report generation for evaluation results."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_data_harness.adjudication import admissibility_metrics_json, outcome_counts
from ai_data_harness.contracts import ContractValidationResult
from ai_data_harness.evaluation import EvaluationResult


def write_markdown_report(result: EvaluationResult, path: str | Path) -> None:
    """Write an evaluation result as a Markdown report.

    Args:
        result: Evaluation result to serialize.
        path: Destination Markdown path.

    Raises:
        OSError: If the destination cannot be written.
    """
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(result))


def write_run_summary_json(result: EvaluationResult, path: str | Path) -> None:
    """Write an evaluation result as a deterministic machine-readable summary.

    Args:
        result: Evaluation result to serialize.
        path: Destination JSON path.

    Raises:
        OSError: If the destination cannot be written.
    """
    summary_path = Path(path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            render_run_summary(result, summary_path=summary_path),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def render_run_summary(
    result: EvaluationResult,
    *,
    summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Render a compact deterministic JSON-compatible run summary.

    Args:
        result: Evaluation result to summarize.
        summary_path: Optional summary path to include in artifact metadata.

    Returns:
        JSON-compatible run summary.
    """
    admissibility_metrics = None
    outcome_summary: dict[str, int] = {}
    critical_confusions: list[dict[str, Any]] = []
    severity_review_counts: list[dict[str, Any]] = []
    if result.adjudication is not None:
        admissibility_metrics = admissibility_metrics_json(
            result.adjudication.admissibility_metrics
        )
        outcome_summary = outcome_counts(result.adjudication.adjudications)
        critical_confusions = [
            asdict(confusion) for confusion in result.adjudication.critical_confusions
        ]
        severity_review_counts = [
            asdict(count) for count in result.adjudication.severity_review_counts
        ]

    return {
        "status": result.status,
        "passed": result.passed,
        "contracts": {
            "baseline": _contract_summary(result.baseline_contract),
            "candidate": _contract_summary(result.candidate_contract),
        },
        "metrics": {
            "candidate_attributes": [
                _candidate_attribute_metrics_json(metric)
                for metric in result.candidate_metrics
            ],
            "candidate_segments": [
                _candidate_segment_metrics_json(metric)
                for metric in result.candidate_segment_metrics
            ],
            "admissibility": admissibility_metrics,
            "outcome_counts": outcome_summary,
            "critical_confusions": critical_confusions,
            "severity_review_counts": severity_review_counts,
            "confidence_diagnostics": [
                _confidence_metrics_json(metric)
                for metric in result.confidence_diagnostics
            ],
        },
        "metric_deltas": [
            _metric_comparison_json(comparison)
            for comparison in result.metric_comparisons
        ],
        "segment_metric_deltas": [
            _segment_metric_comparison_json(comparison)
            for comparison in result.segment_metric_comparisons
        ],
        "failed_gates": [
            asdict(gate) for gate in result.gate_results if not gate.passed
        ],
        "failed_segment_gates": [
            asdict(gate)
            for gate in result.gate_results
            if gate.name == "segment_max_accuracy_drop" and not gate.passed
        ],
        "metric_groups": _metric_groups(),
        "artifact_paths": _artifact_paths(result, summary_path),
    }


def render_markdown_report(result: EvaluationResult) -> str:
    """Render a deterministic Markdown evaluation report.

    Args:
        result: Evaluation result to report.

    Returns:
        Markdown report text.
    """
    lines = [
        "# Evaluation Report",
        "",
        f"Overall status: **{result.status}**",
        "",
        "## Candidate Admissibility Decision",
        "",
        f"Final status: **{result.status}**",
        "",
        (
            "NEEDS_REVIEW is a safe routing outcome: configured gates passed, "
            "but one or more requires_review cells must be reviewed before "
            "promotion."
        ),
        "",
    ]

    if result.adjudication is not None:
        metrics = result.adjudication.admissibility_metrics
        lines.extend(
            [
                "| Adjudicated cell metric | Value |",
                "| --- | ---: |",
                f"| adjudicated_cell_accuracy | {_format_rate(metrics.accuracy)} |",
                f"| cell_level_abstention_rate | "
                f"{_format_rate(metrics.abstention_rate)} |",
                f"| cell_level_invalid_rate | {_format_rate(metrics.invalid_rate)} |",
                f"| false_acceptance_rate | "
                f"{_format_rate(metrics.false_acceptance_rate)} |",
                f"| human_review_rate | {_format_rate(metrics.human_review_rate)} |",
                f"| critical_wrong_rate | "
                f"{_format_rate(metrics.critical_wrong_rate)} |",
                f"| total_cells | {metrics.total_cells} |",
                f"| critical_cells | {metrics.critical_cells} |",
                f"| correct_cells | {metrics.correct_cells} |",
                f"| incorrect_cells | {metrics.incorrect_cells} |",
                f"| abstained_cells | {metrics.abstained_cells} |",
                f"| invalid_cells | {metrics.invalid_cells} |",
                f"| missing_cells | {metrics.missing_cells} |",
                f"| accepted_cells | {metrics.accepted_cells} |",
                f"| requires_review_cells | {metrics.requires_review_cells} |",
                f"| incorrect_accepted_cells | {metrics.incorrect_accepted_cells} |",
                f"| critical_wrong_cells | {metrics.critical_wrong_cells} |",
                "",
                "### Review Queue Composition",
                "",
                (
                    "Breakdown of requires_review_cells by outcome: how much of the "
                    "review queue is wrong values worth a reviewer's time versus "
                    "abstentions, invalid values, or missing data."
                ),
                "",
                "| Review composition metric | Value |",
                "| --- | ---: |",
                f"| review_incorrect_cells | {metrics.review_incorrect_cells} |",
                f"| review_incorrect_rate | "
                f"{_format_rate(metrics.review_incorrect_rate)} |",
                f"| review_abstained_rate | "
                f"{_format_rate(metrics.review_abstained_rate)} |",
                f"| review_invalid_rate | "
                f"{_format_rate(metrics.review_invalid_rate)} |",
                f"| review_missing_rate | "
                f"{_format_rate(metrics.review_missing_rate)} |",
                "",
                "### Outcome Counts",
                "",
                "| Outcome | Count |",
                "| --- | ---: |",
            ]
        )
        counts = outcome_counts(result.adjudication.adjudications)
        for outcome, count in counts.items():
            lines.append(f"| {outcome} | {count} |")

        lines.extend(["", "### Critical Confusion Counts", ""])
        if result.adjudication.critical_confusions:
            lines.extend(
                [
                    "| Attribute | Expected | Candidate | Count |",
                    "| --- | --- | --- | ---: |",
                ]
            )
            for confusion in result.adjudication.critical_confusions:
                lines.append(
                    "| "
                    f"{confusion.attribute} | "
                    f"{confusion.expected_value or ''} | "
                    f"{confusion.candidate_value or ''} | "
                    f"{confusion.count} |"
                )
        else:
            lines.append("Critical confusion counts: none")

        lines.extend(["", "### Severity Review Counts", ""])
        if result.adjudication.severity_review_counts:
            lines.extend(
                [
                    "| Attribute | Expected | Candidate | Severity | Reason | Count |",
                    "| --- | --- | --- | --- | --- | ---: |",
                ]
            )
            for count in result.adjudication.severity_review_counts:
                lines.append(
                    "| "
                    f"{count.attribute} | "
                    f"{count.expected_value or ''} | "
                    f"{count.candidate_value or ''} | "
                    f"{count.severity} | "
                    f"{count.reason} | "
                    f"{count.count} |"
                )
        else:
            lines.append("Severity review counts: none")
    else:
        lines.append(
            "Adjudication was skipped because candidate record IDs were not usable."
        )

    lines.extend(
        [
            "",
            "## Contract Validation",
            "",
            _render_contract_summary("Baseline", result.baseline_contract),
            "",
            _render_contract_summary("Candidate", result.candidate_contract),
            "",
            "## Baseline-vs-Candidate Regression Context",
            "",
            (
                "These are comparison metrics for regression checks, not "
                "cell-level routing or admissibility metrics."
            ),
            "",
            "### Attribute Regression Context",
            "",
        ]
    )

    if result.metric_comparisons:
        lines.extend(
            [
                "| Attribute | Total | baseline_attribute_regression_accuracy | "
                "candidate_attribute_regression_accuracy | "
                "attribute_regression_accuracy_delta | "
                "baseline_row_level_abstention_rate | "
                "candidate_row_level_abstention_rate |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for comparison in result.metric_comparisons:
            lines.append(
                "| "
                f"{comparison.attribute} | "
                f"{comparison.total} | "
                f"{_format_rate(comparison.baseline_accuracy)} | "
                f"{_format_rate(comparison.candidate_accuracy)} | "
                f"{_format_delta(comparison.accuracy_delta)} | "
                f"{_format_rate(comparison.baseline_abstention_rate)} | "
                f"{_format_rate(comparison.candidate_abstention_rate)} |"
            )
    else:
        lines.append(
            "Metrics were skipped because baseline or candidate contract "
            "validation failed."
        )

    lines.extend(["", "### Segment Regression Context", ""])
    if result.segment_metric_comparisons:
        lines.extend(
            [
                "| Segment | Value | Attribute | Total | "
                "baseline_segment_regression_accuracy | "
                "candidate_segment_regression_accuracy | "
                "segment_regression_accuracy_delta | "
                "baseline_row_level_abstention_rate | "
                "candidate_row_level_abstention_rate |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for comparison in result.segment_metric_comparisons:
            lines.append(
                "| "
                f"{comparison.segment_column} | "
                f"{comparison.segment_value} | "
                f"{comparison.attribute} | "
                f"{comparison.total} | "
                f"{_format_rate(comparison.baseline_accuracy)} | "
                f"{_format_rate(comparison.candidate_accuracy)} | "
                f"{_format_delta(comparison.accuracy_delta)} | "
                f"{_format_rate(comparison.baseline_abstention_rate)} | "
                f"{_format_rate(comparison.candidate_abstention_rate)} |"
            )

        segment_gates = [
            gate
            for gate in result.gate_results
            if gate.name == "segment_max_accuracy_drop"
        ]
        if segment_gates:
            lines.extend(
                [
                    "",
                    "| Gate | Metric family | Segment | Attribute | Status | "
                    "Min size | Threshold | Observed | Details |",
                    "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
                ]
            )
            for gate in segment_gates:
                observed = (
                    _format_rate(gate.accuracy_drop)
                    if gate.accuracy_drop is not None
                    else "n/a"
                )
                segment = f"{gate.segment_column}={gate.segment_value}"
                lines.append(
                    "| "
                    f"{gate.name} | "
                    f"{_gate_metric_family(gate)} | "
                    f"{segment} | "
                    f"{gate.attribute or ''} | "
                    f"{_gate_status(gate)} | "
                    f"{gate.min_segment_size or ''} | "
                    f"{_format_rate(gate.threshold)} | "
                    f"{observed} | "
                    f"{gate.message} |"
                )
    else:
        lines.append("Segment regression was not configured for this run.")

    lines.extend(["", "## Confidence Diagnostics", ""])
    if result.confidence_diagnostics:
        lines.extend(
            [
                "| Bucket | Total cells | adjudicated_cell_accuracy | "
                "cell_level_abstention_rate | false_acceptance_rate | Correct | "
                "Abstained | False acceptance |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for metric in result.confidence_diagnostics:
            lines.append(
                "| "
                f"{metric.bucket} | "
                f"{metric.total_cells} | "
                f"{_format_rate(metric.accuracy)} | "
                f"{_format_rate(metric.abstention_rate)} | "
                f"{_format_rate(metric.false_acceptance_rate)} | "
                f"{metric.correct_cells} | "
                f"{metric.abstained_cells} | "
                f"{metric.false_acceptance_cells} |"
            )
    else:
        lines.append(
            "Confidence diagnostics were skipped because adjudication was unavailable "
            "or candidate contract validation failed."
        )

    lines.extend(["", "## Regression Gates", ""])
    lines.append(
        "Human review routing is reported under review_routing metadata and "
        "requires_review_cells; it can produce NEEDS_REVIEW separately from "
        "gate failure."
    )
    lines.append("")
    if result.gate_results:
        lines.extend(
            [
                "| Gate | Metric family | Subject | Status | Threshold | Observed | "
                "Details |",
                "| --- | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for gate in result.gate_results:
            observed = (
                _format_gate_value(gate, gate.accuracy_drop)
                if gate.accuracy_drop is not None
                else "n/a"
            )
            lines.append(
                "| "
                f"{gate.name} | "
                f"{_gate_metric_family(gate)} | "
                f"{_gate_subject(gate)} | "
                f"{_gate_status(gate)} | "
                f"{_format_gate_value(gate, gate.threshold)} | "
                f"{observed} | "
                f"{gate.message} |"
            )
    else:
        lines.append(
            "Regression gates were skipped because baseline or candidate "
            "contract validation failed."
        )

    lines.extend(
        ["", "## Human Review Recommendation", "", _recommendation(result), ""]
    )
    return "\n".join(lines)


def _render_contract_summary(
    label: str,
    validation: ContractValidationResult,
) -> str:
    """Render contract validation status and issues as Markdown."""
    lines = [
        f"### {label}",
        "",
        f"Status: **{'PASSED' if validation.passed else 'FAILED'}**",
        f"Issue count: {len(validation.issues)}",
    ]
    if validation.issues:
        lines.extend(["", "| Code | Column | Record ID | Row | Message |"])
        lines.append("| --- | --- | --- | ---: | --- |")
        for issue in validation.issues:
            row_number = issue.row_number or ""
            lines.append(
                "| "
                f"{issue.code} | "
                f"{issue.column or ''} | "
                f"{issue.record_id or ''} | "
                f"{row_number} | "
                f"{issue.message} |"
            )
    return "\n".join(lines)


def _contract_summary(validation: ContractValidationResult) -> dict[str, Any]:
    """Render contract validation status and issues as JSON-compatible data."""
    return {
        "passed": validation.passed,
        "issue_count": len(validation.issues),
        "issues": [asdict(issue) for issue in validation.issues],
    }


def _asdict_renamed(obj: Any, renames: dict[str, str]) -> dict[str, Any]:
    """Serialize a dataclass and rename selected keys for explicit naming."""
    data = asdict(obj)
    for old_key, new_key in renames.items():
        data[new_key] = data.pop(old_key)
    return data


def _candidate_attribute_metrics_json(metric: Any) -> dict[str, Any]:
    """Serialize candidate attribute metrics with explicit row-level naming."""
    return _asdict_renamed(
        metric, {"abstention_rate": "candidate_row_level_abstention_rate"}
    )


def _candidate_segment_metrics_json(metric: Any) -> dict[str, Any]:
    """Serialize candidate segment metrics with explicit row-level naming."""
    return _asdict_renamed(
        metric, {"abstention_rate": "candidate_row_level_abstention_rate"}
    )


def _confidence_metrics_json(metric: Any) -> dict[str, Any]:
    """Serialize confidence diagnostics with explicit cell-level naming."""
    return _asdict_renamed(metric, {"abstention_rate": "cell_level_abstention_rate"})


def _metric_comparison_json(comparison: Any) -> dict[str, Any]:
    """Serialize attribute comparisons with explicit row-level abstention names."""
    return _asdict_renamed(
        comparison,
        {
            "baseline_abstention_rate": "baseline_row_level_abstention_rate",
            "candidate_abstention_rate": "candidate_row_level_abstention_rate",
        },
    )


def _segment_metric_comparison_json(comparison: Any) -> dict[str, Any]:
    """Serialize segment comparisons with explicit row-level abstention names."""
    return _asdict_renamed(
        comparison,
        {
            "baseline_abstention_rate": "baseline_row_level_abstention_rate",
            "candidate_abstention_rate": "candidate_row_level_abstention_rate",
        },
    )


def _metric_groups() -> dict[str, Any]:
    """Return metric grouping metadata used in run summaries."""
    return {
        "adjudicated_cell_admissibility": {
            "paths": [
                "metrics.admissibility",
                "metrics.outcome_counts",
            ],
            "aliases": {
                "metrics.admissibility.accuracy": "adjudicated_cell_accuracy",
                "metrics.admissibility.cell_level_abstention_rate": (
                    "cell_level_abstention_rate"
                ),
                "metrics.admissibility.false_acceptance_rate": (
                    "false_acceptance_rate"
                ),
                "metrics.admissibility.human_review_rate": "human_review_rate",
                "metrics.admissibility.critical_wrong_rate": "critical_wrong_rate",
            },
        },
        "baseline_vs_candidate_regression_context": {
            "paths": [
                "metric_deltas",
                "segment_metric_deltas",
                "metrics.candidate_attributes",
                "metrics.candidate_segments",
            ],
            "aliases": {
                "metric_deltas[].baseline_accuracy": (
                    "baseline_attribute_regression_accuracy"
                ),
                "metric_deltas[].candidate_accuracy": (
                    "candidate_attribute_regression_accuracy"
                ),
                "metric_deltas[].accuracy_delta": (
                    "attribute_regression_accuracy_delta"
                ),
                "segment_metric_deltas[].baseline_accuracy": (
                    "baseline_segment_regression_accuracy"
                ),
                "segment_metric_deltas[].candidate_accuracy": (
                    "candidate_segment_regression_accuracy"
                ),
                "segment_metric_deltas[].accuracy_delta": (
                    "segment_regression_accuracy_delta"
                ),
                "metric_deltas[].baseline_row_level_abstention_rate": (
                    "baseline_row_level_abstention_rate"
                ),
                "metric_deltas[].candidate_row_level_abstention_rate": (
                    "candidate_row_level_abstention_rate"
                ),
                "segment_metric_deltas[].baseline_row_level_abstention_rate": (
                    "baseline_row_level_abstention_rate"
                ),
                "segment_metric_deltas[].candidate_row_level_abstention_rate": (
                    "candidate_row_level_abstention_rate"
                ),
            },
        },
        "gates": {
            "paths": [
                "failed_gates",
                "failed_segment_gates",
            ],
            "gate_metric_families": {
                "max_accuracy_drop": (
                    "baseline-vs-candidate attribute regression metrics"
                ),
                "segment_max_accuracy_drop": (
                    "baseline-vs-candidate segment regression metrics"
                ),
                "max_candidate_abstention_rate": "row-level candidate abstention",
                "max_false_acceptance_rate": (
                    "adjudicated admissibility false_acceptance_rate"
                ),
                "max_severity_review_count": ("severity-routed human review count"),
            },
        },
        "review_routing": {
            "paths": [
                "status",
                "metrics.admissibility.requires_review_cells",
                "metrics.admissibility.human_review_rate",
            ],
            "aliases": {
                "metrics.admissibility.requires_review_cells": (
                    "requires_review_cells"
                ),
                "metrics.admissibility.human_review_rate": "human_review_rate",
            },
            "status_semantics": (
                "NEEDS_REVIEW is based on requires_review_cells when contracts and "
                "gates pass; it is not a failed regression or threshold gate."
            ),
        },
        "review_queue_composition": {
            "paths": [
                "metrics.admissibility",
            ],
            "aliases": {
                "metrics.admissibility.review_incorrect_rate": "review_incorrect_rate",
                "metrics.admissibility.review_abstained_rate": "review_abstained_rate",
                "metrics.admissibility.review_invalid_rate": "review_invalid_rate",
                "metrics.admissibility.review_missing_rate": "review_missing_rate",
            },
            "semantics": (
                "Breaks down requires_review_cells by outcome. Unlike "
                "false_acceptance_rate, which answers how often a wrong value was "
                "auto-accepted, this answers what the review queue is made of: "
                "genuinely wrong values worth a reviewer's time versus abstentions, "
                "invalid values, or missing data."
            ),
        },
    }


def _artifact_paths(
    result: EvaluationResult,
    summary_path: str | Path | None,
) -> dict[str, str]:
    """Return generated artifact paths for the run summary."""
    artifacts = {"report": result.report_path}
    if result.adjudication_path is not None:
        artifacts["adjudication"] = result.adjudication_path

    resolved_summary_path = (
        str(summary_path) if summary_path is not None else result.summary_path
    )
    if resolved_summary_path is not None:
        artifacts["summary"] = resolved_summary_path
    return artifacts


def _recommendation(result: EvaluationResult) -> str:
    """Render the human-review recommendation for an evaluation result."""
    if not result.baseline_contract.passed or not result.candidate_contract.passed:
        return (
            "Send the run to data engineering review. Contract failures mean the "
            "outputs are not admissible for semantic evaluation."
        )

    failed_gates = [gate for gate in result.gate_results if not gate.passed]
    if failed_gates:
        failed_names = ", ".join(_gate_subject(gate) for gate in failed_gates)
        return (
            "Send the candidate to human review before promotion. Failed gates: "
            f"{failed_names}."
        )

    if (
        result.adjudication is not None
        and result.adjudication.admissibility_metrics.requires_review_cells > 0
    ):
        return (
            "Send the candidate to human review before promotion. One or more "
            "adjudicated cells require review."
        )

    return (
        "No contract, regression-gate, or human-review blockers were found. "
        "Candidate is admissible for promotion under the configured rules."
    )


def _format_rate(value: float | None) -> str:
    """Format an optional rate for report output."""
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _format_gate_value(gate: Any, value: float | None) -> str:
    """Format an optional gate value for report output."""
    if value is None:
        return "n/a"
    if gate.name == "max_severity_review_count":
        return str(int(value))
    return _format_rate(value)


def _format_delta(value: float) -> str:
    """Format a signed metric delta for report output."""
    return f"{value:+.3f}"


def _gate_status(gate: Any) -> str:
    """Return the display status for a gate result."""
    if getattr(gate, "skipped", False):
        return "SKIPPED"
    return "PASSED" if gate.passed else "FAILED"


def _gate_subject(gate: Any) -> str:
    """Return the display subject for a gate result."""
    if gate.segment_column is not None and gate.segment_value is not None:
        return f"{gate.attribute} ({gate.segment_column}={gate.segment_value})"
    return gate.attribute or "candidate"


def _gate_metric_family(gate: Any) -> str:
    """Return the metric family label for a gate result."""
    gate_families = _metric_groups()["gates"]["gate_metric_families"]
    return gate_families.get(gate.name, "unknown")
