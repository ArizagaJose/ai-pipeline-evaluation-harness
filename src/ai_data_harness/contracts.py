"""Output contract loading and deterministic row validation."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_data_harness.common import is_null, matches_type

SUPPORTED_TYPES = {"boolean", "number", "string"}
SUPPORTED_REVIEW_SEVERITIES = {"medium", "high", "critical"}


@dataclass(frozen=True)
class ReviewOverride:
    """Represent a contract rule that routes a value pair to review."""

    expected_value: str
    candidate_value: str
    severity: str
    reason: str


@dataclass(frozen=True)
class ContractColumn:
    """Represent one output contract column definition."""

    name: str
    data_type: str
    required: bool
    nullable: bool
    allowed_values: frozenset[str]
    abstention_values: frozenset[str]
    review_overrides: tuple[ReviewOverride, ...]
    critical: bool


@dataclass(frozen=True)
class OutputContract:
    """Represent a parsed output contract."""

    version: int
    record_id_column: str
    columns: tuple[ContractColumn, ...]


@dataclass(frozen=True)
class ValidationIssue:
    """Represent one deterministic contract validation issue."""

    code: str
    message: str
    column: str | None = None
    record_id: str | None = None
    row_number: int | None = None
    value: str | None = None


@dataclass(frozen=True)
class ContractValidationResult:
    """Represent all validation issues for a dataset."""

    issues: tuple[ValidationIssue, ...]

    @property
    def passed(self) -> bool:
        """Return whether contract validation found no issues."""
        return not self.issues


def load_contract(path: str | Path) -> OutputContract:
    """Load an output contract from a JSON file.

    Args:
        path: Path to the JSON contract file.

    Returns:
        Parsed output contract.

    Raises:
        ValueError: If the contract data is invalid.
        OSError: If the file cannot be read.
    """
    with Path(path).open() as file:
        data = json.load(file)

    return parse_contract(data)


def parse_contract(data: dict[str, Any]) -> OutputContract:
    """Parse contract data loaded from JSON.

    Args:
        data: JSON-compatible contract object.

    Returns:
        Parsed output contract.

    Raises:
        ValueError: If required fields or column definitions are invalid.
    """
    version = data.get("version")
    record_id_column = data.get("record_id_column")
    columns = data.get("columns")

    if not isinstance(version, int):
        msg = "Contract field 'version' must be an integer."
        raise ValueError(msg)
    if not isinstance(record_id_column, str) or not record_id_column:
        msg = "Contract field 'record_id_column' must be a non-empty string."
        raise ValueError(msg)
    if not isinstance(columns, dict) or not columns:
        msg = "Contract field 'columns' must be a non-empty object."
        raise ValueError(msg)

    parsed_columns = tuple(
        _parse_column(name, config) for name, config in columns.items()
    )
    column_names = {column.name for column in parsed_columns}
    if record_id_column not in column_names:
        msg = "The record ID column must be defined in contract columns."
        raise ValueError(msg)

    return OutputContract(
        version=version,
        record_id_column=record_id_column,
        columns=parsed_columns,
    )


def validate_rows(
    rows: list[dict[str, str]],
    contract: OutputContract,
) -> ContractValidationResult:
    """Validate CSV-style rows against an output contract.

    Args:
        rows: Candidate rows represented as string-valued dictionaries.
        contract: Parsed output contract to validate against.

    Returns:
        Contract validation result containing all discovered issues.
    """
    issues: list[ValidationIssue] = []

    if not rows:
        return ContractValidationResult(
            issues=(
                ValidationIssue(
                    code="empty_dataset",
                    message="Dataset contains no rows.",
                ),
            )
        )

    required_columns = {column.name for column in contract.columns if column.required}
    present_columns = set(rows[0])
    for column_name in sorted(required_columns - present_columns):
        issues.append(
            ValidationIssue(
                code="missing_required_column",
                message=f"Required column '{column_name}' is missing.",
                column=column_name,
            )
        )

    issues.extend(_validate_record_ids(rows, contract.record_id_column))

    for row_number, row in enumerate(rows, start=2):
        record_id = row.get(contract.record_id_column) or None
        for column in contract.columns:
            if column.name not in row:
                continue
            issues.extend(
                _validate_value(row[column.name], column, record_id, row_number)
            )

    return ContractValidationResult(issues=tuple(issues))


def _parse_column(name: str, config: Any) -> ContractColumn:
    """Parse one contract column definition."""
    if not isinstance(config, dict):
        msg = f"Contract column '{name}' must be an object."
        raise ValueError(msg)

    data_type = config.get("type")
    if data_type not in SUPPORTED_TYPES:
        msg = (
            f"Contract column '{name}' has unsupported type {data_type!r}. "
            f"Supported types: {sorted(SUPPORTED_TYPES)}."
        )
        raise ValueError(msg)

    allowed_values = _parse_string_list(name, config, "allowed_values")
    abstention_values = _parse_string_list(name, config, "abstention_values")

    return ContractColumn(
        name=name,
        data_type=data_type,
        required=bool(config.get("required", False)),
        nullable=bool(config.get("nullable", True)),
        allowed_values=frozenset(allowed_values),
        abstention_values=frozenset(abstention_values),
        review_overrides=_parse_review_overrides(
            name,
            config,
            allowed_values=frozenset(allowed_values),
            abstention_values=frozenset(abstention_values),
        ),
        critical=bool(config.get("critical", False)),
    )


def _parse_string_list(name: str, config: dict[str, Any], key: str) -> list[str]:
    """Parse a string-list field from a column config."""
    values = config.get(key, [])
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        msg = f"Contract column '{name}' {key} must be a list of strings."
        raise ValueError(msg)
    return values


def _parse_review_overrides(
    name: str,
    config: dict[str, Any],
    *,
    allowed_values: frozenset[str],
    abstention_values: frozenset[str],
) -> tuple[ReviewOverride, ...]:
    """Parse severity review overrides for one contract column."""
    values = config.get("severity_overrides", [])
    if not isinstance(values, list):
        msg = f"Contract column '{name}' severity_overrides must be a list."
        raise ValueError(msg)

    overrides: list[ReviewOverride] = []
    seen: set[tuple[str, str]] = set()
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            msg = (
                f"Contract column '{name}' severity_overrides[{index}] "
                "must be an object."
            )
            raise ValueError(msg)

        expected_value = _required_override_string(name, index, value, "expected_value")
        candidate_value = _required_override_string(
            name, index, value, "candidate_value"
        )
        severity = _required_override_string(name, index, value, "severity")
        reason = _required_override_string(name, index, value, "reason")

        if severity not in SUPPORTED_REVIEW_SEVERITIES:
            msg = (
                f"Contract column '{name}' severity_overrides[{index}] severity "
                f"must be one of {sorted(SUPPORTED_REVIEW_SEVERITIES)}."
            )
            raise ValueError(msg)
        key = (expected_value, candidate_value)
        if key in seen:
            msg = (
                f"Contract column '{name}' has duplicate severity override "
                f"for expected value '{expected_value}' and candidate value "
                f"'{candidate_value}'."
            )
            raise ValueError(msg)
        if candidate_value in abstention_values:
            msg = (
                f"Contract column '{name}' severity_overrides[{index}] "
                "candidate_value must not be an abstention value."
            )
            raise ValueError(msg)
        if allowed_values and candidate_value not in allowed_values:
            msg = (
                f"Contract column '{name}' severity_overrides[{index}] "
                "candidate_value must be in allowed_values."
            )
            raise ValueError(msg)

        seen.add(key)
        overrides.append(
            ReviewOverride(
                expected_value=expected_value,
                candidate_value=candidate_value,
                severity=severity,
                reason=reason,
            )
        )

    return tuple(overrides)


def _required_override_string(
    column_name: str,
    index: int,
    data: dict[str, Any],
    key: str,
) -> str:
    """Read a required non-empty string from a review override."""
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = (
            f"Contract column '{column_name}' severity_overrides[{index}].{key} "
            "must be a non-empty string."
        )
        raise ValueError(msg)
    return value


def _validate_record_ids(
    rows: list[dict[str, str]],
    record_id_column: str,
) -> list[ValidationIssue]:
    """Validate record IDs for presence and uniqueness."""
    issues: list[ValidationIssue] = []
    seen: set[str] = set()

    for row_number, row in enumerate(rows, start=2):
        record_id = row.get(record_id_column, "")
        if is_null(record_id):
            issues.append(
                ValidationIssue(
                    code="missing_record_id",
                    message="Record ID is required and cannot be null.",
                    column=record_id_column,
                    row_number=row_number,
                )
            )
            continue

        if record_id in seen:
            issues.append(
                ValidationIssue(
                    code="duplicate_record_id",
                    message=f"Record ID '{record_id}' appears more than once.",
                    column=record_id_column,
                    record_id=record_id,
                    row_number=row_number,
                    value=record_id,
                )
            )
        seen.add(record_id)

    return issues


def _validate_value(
    value: str,
    column: ContractColumn,
    record_id: str | None,
    row_number: int,
) -> list[ValidationIssue]:
    """Validate one scalar value against a contract column."""
    if value in column.abstention_values:
        return []

    if is_null(value):
        if column.nullable:
            return []
        return [
            ValidationIssue(
                code="null_value",
                message=f"Column '{column.name}' cannot be null.",
                column=column.name,
                record_id=record_id,
                row_number=row_number,
                value=value,
            )
        ]

    issues: list[ValidationIssue] = []
    if not matches_type(value, column.data_type):
        issues.append(
            ValidationIssue(
                code="invalid_type",
                message=f"Column '{column.name}' must be {column.data_type}.",
                column=column.name,
                record_id=record_id,
                row_number=row_number,
                value=value,
            )
        )

    if column.allowed_values and value not in column.allowed_values:
        issues.append(
            ValidationIssue(
                code="invalid_allowed_value",
                message=f"Column '{column.name}' contains unsupported value '{value}'.",
                column=column.name,
                record_id=record_id,
                row_number=row_number,
                value=value,
            )
        )

    return issues
