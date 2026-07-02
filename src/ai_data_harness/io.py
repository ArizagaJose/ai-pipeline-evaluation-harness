"""Small local file IO helpers."""

import csv
from numbers import Number
from pathlib import Path


def read_rows(path: str | Path) -> list[dict[str, str]]:
    """Read supported tabular inputs as CSV-compatible row dictionaries.

    Args:
        path: Path to a supported tabular input file.

    Returns:
        Rows normalized to string-valued dictionaries.

    Raises:
        ValueError: If the file extension is unsupported.
        OSError: If the file cannot be read.
    """
    input_path = Path(path)
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return read_csv_rows(input_path)
    if suffix == ".parquet":
        return _read_parquet_rows(input_path)

    msg = (
        f"Unsupported input file extension '{input_path.suffix}' for {input_path}. "
        "Supported extensions are: .csv, .parquet."
    )
    raise ValueError(msg)


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Read CSV rows as dictionaries.

    Args:
        path: Path to the CSV file.

    Returns:
        Rows as dictionaries keyed by CSV header.

    Raises:
        OSError: If the file cannot be read.
    """
    with Path(path).open(newline="") as file:
        return list(csv.DictReader(file))


def _read_parquet_rows(path: Path) -> list[dict[str, str]]:
    """Read Parquet rows as CSV-compatible dictionaries."""
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    return [
        {str(column): _normalize_scalar(value) for column, value in row.items()}
        for row in table.to_pylist()
    ]


def _normalize_scalar(value: object) -> str:
    """Normalize a tabular scalar to the harness string representation."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, Number):
        return str(value)
    return str(value)
