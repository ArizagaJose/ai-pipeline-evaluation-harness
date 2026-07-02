"""Evaluation config loading and validation."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_data_harness.contracts import SUPPORTED_REVIEW_SEVERITIES
from ai_data_harness.metrics import AttributeMapping


class EvaluationConfigError(ValueError):
    """Raised when an evaluation config is invalid."""


@dataclass(frozen=True)
class RegressionGateConfig:
    """Represent a configured attribute-level accuracy regression gate."""

    attribute: str
    max_accuracy_drop: float


@dataclass(frozen=True)
class SegmentRegressionGateConfig:
    """Represent a configured segment-level accuracy regression gate."""

    attribute: str
    segment_column: str
    segment_value: str
    max_accuracy_drop: float
    min_segment_size: int


@dataclass(frozen=True)
class SeverityReviewGateConfig:
    """Represent a configured severity review count gate."""

    severity: str
    max_count: int


@dataclass(frozen=True)
class EvaluationConfig:
    """Represent a validated evaluation run configuration."""

    contract_path: Path
    golden_path: Path
    source_path: Path | None
    baseline_output_path: Path
    candidate_output_path: Path
    report_path: Path
    adjudication_path: Path | None
    summary_path: Path | None
    record_id_column: str
    abstention_column: str
    confidence_column: str
    attributes: tuple[AttributeMapping, ...]
    regression_gates: tuple[RegressionGateConfig, ...]
    segment_columns: tuple[str, ...]
    segment_regression_gates: tuple[SegmentRegressionGateConfig, ...]
    severity_review_gates: tuple[SeverityReviewGateConfig, ...]
    max_candidate_abstention_rate: float
    max_false_acceptance_rate: float | None


def load_evaluation_config(path: str | Path) -> EvaluationConfig:
    """Load an evaluation config from JSON.

    Args:
        path: Path to the evaluation config JSON file.

    Returns:
        Parsed and validated evaluation config.

    Raises:
        EvaluationConfigError: If the config is malformed or inconsistent.
        OSError: If the file cannot be read.
    """
    config_path = Path(path)
    try:
        with config_path.open() as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        msg = f"Config file is not valid JSON: {exc}"
        raise EvaluationConfigError(msg) from exc

    if not isinstance(data, dict):
        msg = "Evaluation config must be a JSON object."
        raise EvaluationConfigError(msg)
    if "max_critical_false_acceptance_rate" in data:
        msg = (
            "Config field 'max_critical_false_acceptance_rate' is no longer "
            "supported. Critical wrong valid values are routed to review and "
            "tracked by critical_wrong_rate."
        )
        raise EvaluationConfigError(msg)

    base_dir = config_path.parent
    paths = _required_object(data, "paths")
    attributes = _parse_attributes(_required_object(data, "attributes"))
    gates = _parse_gates(data.get("regression_gates", []))
    segment_columns = _parse_optional_string_list(data.get("segment_columns", []))
    segment_gates = _parse_segment_gates(
        data.get("segment_regression_gates", []),
        attributes=attributes,
        segment_columns=segment_columns,
    )
    severity_review_gates = _parse_severity_review_gates(
        data.get("severity_review_gates", [])
    )
    source_path = _optional_path(base_dir, paths, "source")
    if segment_columns and source_path is None:
        msg = "Config field 'paths.source' is required when segment_columns is set."
        raise EvaluationConfigError(msg)
    if segment_gates and not segment_columns:
        msg = (
            "Config field 'segment_columns' is required when "
            "segment_regression_gates is set."
        )
        raise EvaluationConfigError(msg)
    if segment_gates and source_path is None:
        msg = (
            "Config field 'paths.source' is required when "
            "segment_regression_gates is set."
        )
        raise EvaluationConfigError(msg)

    return EvaluationConfig(
        contract_path=_resolve_path(base_dir, _required_string(paths, "contract")),
        golden_path=_resolve_path(base_dir, _required_string(paths, "golden")),
        source_path=source_path,
        baseline_output_path=_resolve_path(
            base_dir, _required_string(paths, "baseline_output")
        ),
        candidate_output_path=_resolve_path(
            base_dir, _required_string(paths, "candidate_output")
        ),
        report_path=_resolve_path(base_dir, _required_string(paths, "report")),
        adjudication_path=_optional_path(base_dir, paths, "adjudication"),
        summary_path=_optional_path(base_dir, paths, "summary"),
        record_id_column=_required_string(data, "record_id_column"),
        abstention_column=_required_string(data, "abstention_column"),
        confidence_column=_optional_string(
            data,
            "confidence_column",
            default="model_confidence",
        ),
        attributes=attributes,
        regression_gates=gates,
        segment_columns=segment_columns,
        segment_regression_gates=segment_gates,
        severity_review_gates=severity_review_gates,
        max_candidate_abstention_rate=_required_rate(
            data, "max_candidate_abstention_rate"
        ),
        max_false_acceptance_rate=_optional_rate(data, "max_false_acceptance_rate"),
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    """Resolve a configured path relative to the config file directory."""
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _optional_path(base_dir: Path, data: dict[str, Any], key: str) -> Path | None:
    """Parse an optional path field from a config object."""
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        msg = f"Config field 'paths.{key}' must be a non-empty string."
        raise EvaluationConfigError(msg)
    return _resolve_path(base_dir, value)


def _required_object(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Read a required non-empty object field."""
    value = data.get(key)
    if not isinstance(value, dict) or not value:
        msg = f"Config field '{key}' must be a non-empty object."
        raise EvaluationConfigError(msg)
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    """Read a required non-empty string field."""
    value = data.get(key)
    if not isinstance(value, str) or not value:
        msg = f"Config field '{key}' must be a non-empty string."
        raise EvaluationConfigError(msg)
    return value


def _optional_string(data: dict[str, Any], key: str, *, default: str) -> str:
    """Read an optional string field with a default value."""
    if key not in data:
        return default
    return _required_string(data, key)


def _required_rate(data: dict[str, Any], key: str) -> float:
    """Read a required numeric rate between zero and one."""
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        msg = f"Config field '{key}' must be a number from 0 to 1."
        raise EvaluationConfigError(msg)
    rate = float(value)
    if rate < 0 or rate > 1:
        msg = f"Config field '{key}' must be between 0 and 1."
        raise EvaluationConfigError(msg)
    return rate


def _optional_rate(data: dict[str, Any], key: str) -> float | None:
    """Read an optional numeric rate between zero and one."""
    if key not in data:
        return None
    return _required_rate(data, key)


def _parse_attributes(data: dict[str, Any]) -> tuple[AttributeMapping, ...]:
    """Parse configured attribute mappings."""
    attributes: list[AttributeMapping] = []
    for name, mapping in data.items():
        if not isinstance(name, str) or not name:
            msg = "Attribute names must be non-empty strings."
            raise EvaluationConfigError(msg)
        if not isinstance(mapping, dict):
            msg = f"Attribute '{name}' config must be an object."
            raise EvaluationConfigError(msg)
        attributes.append(
            AttributeMapping(
                name=name,
                expected_column=_required_string(mapping, "expected_column"),
                predicted_column=_required_string(mapping, "predicted_column"),
            )
        )
    return tuple(attributes)


def _parse_gates(data: Any) -> tuple[RegressionGateConfig, ...]:
    """Parse configured attribute-level regression gates."""
    if not isinstance(data, list):
        msg = "Config field 'regression_gates' must be a list."
        raise EvaluationConfigError(msg)

    gates: list[RegressionGateConfig] = []
    for index, gate in enumerate(data):
        if not isinstance(gate, dict):
            msg = f"Regression gate at index {index} must be an object."
            raise EvaluationConfigError(msg)
        gates.append(
            RegressionGateConfig(
                attribute=_required_string(gate, "attribute"),
                max_accuracy_drop=_required_rate(gate, "max_accuracy_drop"),
            )
        )
    return tuple(gates)


def _parse_optional_string_list(data: Any) -> tuple[str, ...]:
    """Parse the optional segment column list."""
    if data is None:
        return ()
    if not isinstance(data, list):
        msg = "Config field 'segment_columns' must be a list."
        raise EvaluationConfigError(msg)

    values: list[str] = []
    for index, value in enumerate(data):
        if not isinstance(value, str) or not value:
            msg = f"Config field 'segment_columns[{index}]' must be a non-empty string."
            raise EvaluationConfigError(msg)
        if value in values:
            msg = f"Config field 'segment_columns' contains duplicate value '{value}'."
            raise EvaluationConfigError(msg)
        values.append(value)
    return tuple(values)


def _parse_segment_gates(
    data: Any,
    *,
    attributes: tuple[AttributeMapping, ...],
    segment_columns: tuple[str, ...],
) -> tuple[SegmentRegressionGateConfig, ...]:
    """Parse configured segment-level regression gates."""
    if not isinstance(data, list):
        msg = "Config field 'segment_regression_gates' must be a list."
        raise EvaluationConfigError(msg)

    attribute_names = {attribute.name for attribute in attributes}
    gates: list[SegmentRegressionGateConfig] = []
    for index, gate in enumerate(data):
        if not isinstance(gate, dict):
            msg = f"Segment regression gate at index {index} must be an object."
            raise EvaluationConfigError(msg)

        attribute = _required_string(gate, "attribute")
        if attribute not in attribute_names:
            msg = f"Segment regression gate references unknown attribute '{attribute}'."
            raise EvaluationConfigError(msg)

        segment_column = _required_string(gate, "segment_column")
        if segment_columns and segment_column not in segment_columns:
            msg = (
                f"Segment regression gate references segment column "
                f"'{segment_column}' that is not listed in segment_columns."
            )
            raise EvaluationConfigError(msg)

        gates.append(
            SegmentRegressionGateConfig(
                attribute=attribute,
                segment_column=segment_column,
                segment_value=_required_string(gate, "segment_value"),
                max_accuracy_drop=_required_rate(gate, "max_accuracy_drop"),
                min_segment_size=_required_positive_int(gate, "min_segment_size"),
            )
        )
    return tuple(gates)


def _parse_severity_review_gates(
    data: Any,
) -> tuple[SeverityReviewGateConfig, ...]:
    """Parse configured severity review count gates."""
    if not isinstance(data, list):
        msg = "Config field 'severity_review_gates' must be a list."
        raise EvaluationConfigError(msg)

    gates: list[SeverityReviewGateConfig] = []
    severities: set[str] = set()
    for index, gate in enumerate(data):
        if not isinstance(gate, dict):
            msg = f"Severity review gate at index {index} must be an object."
            raise EvaluationConfigError(msg)

        severity = _required_string(gate, "severity")
        if severity not in SUPPORTED_REVIEW_SEVERITIES:
            supported = ", ".join(sorted(SUPPORTED_REVIEW_SEVERITIES))
            msg = (
                f"Severity review gate at index {index} severity must be one of: "
                f"{supported}."
            )
            raise EvaluationConfigError(msg)
        if severity in severities:
            msg = (
                "Config field 'severity_review_gates' contains duplicate severity "
                f"'{severity}'."
            )
            raise EvaluationConfigError(msg)
        severities.add(severity)

        gates.append(
            SeverityReviewGateConfig(
                severity=severity,
                max_count=_required_non_negative_int(gate, "max_count"),
            )
        )
    return tuple(gates)


def _required_positive_int(data: dict[str, Any], key: str) -> int:
    """Read a required positive integer field."""
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"Config field '{key}' must be a positive integer."
        raise EvaluationConfigError(msg)
    if value < 1:
        msg = f"Config field '{key}' must be at least 1."
        raise EvaluationConfigError(msg)
    return value


def _required_non_negative_int(data: dict[str, Any], key: str) -> int:
    """Read a required non-negative integer field."""
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"Config field '{key}' must be an integer greater than or equal to 0."
        raise EvaluationConfigError(msg)
    if value < 0:
        msg = f"Config field '{key}' must be greater than or equal to 0."
        raise EvaluationConfigError(msg)
    return value
