"""Shared row and scalar helpers used across the evaluation harness."""


def is_null(value: str | None) -> bool:
    """Return whether a CSV scalar should be treated as null."""
    return value is None or value == ""


def matches_type(value: str, data_type: str) -> bool:
    """Return whether a string value matches a contract scalar type."""
    if data_type == "string":
        return True
    if data_type == "boolean":
        return value in {"false", "true"}
    if data_type == "number":
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def safe_rate(numerator: int, denominator: int) -> float:
    """Compute a zero-safe ratio."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def index_by_record_id(
    rows: list[dict[str, str]],
    record_id_column: str,
    dataset_name: str,
) -> dict[str, dict[str, str]]:
    """Index rows by record ID and reject missing, null, or duplicate IDs.

    Args:
        rows: Rows to index, represented as string-valued dictionaries.
        record_id_column: Column used as the record identifier.
        dataset_name: Dataset label used in raised error messages.

    Returns:
        Rows indexed by record ID.

    Raises:
        ValueError: If rows are empty, or contain a missing or duplicate ID.
    """
    if not rows:
        msg = f"{dataset_name} rows cannot be empty."
        raise ValueError(msg)

    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = row.get(record_id_column)
        if is_null(record_id):
            msg = f"{dataset_name} row is missing record ID."
            raise ValueError(msg)
        if record_id in indexed:
            msg = f"{dataset_name} rows contain duplicate record ID '{record_id}'."
            raise ValueError(msg)
        indexed[record_id] = row

    return indexed
