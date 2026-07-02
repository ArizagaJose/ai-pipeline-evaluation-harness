"""Unit tests for supported local tabular readers."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ai_data_harness.io import read_csv_rows, read_rows


def test_read_rows_reads_csv_like_existing_reader(tmp_path: Path) -> None:
    """Verify read rows reads csv like existing reader."""
    path = tmp_path / "rows.csv"
    path.write_text("record_id,value,blank\nA-1,alpha,\nA-2,beta,present\n")

    assert read_rows(path) == read_csv_rows(path)
    assert read_rows(path) == [
        {"record_id": "A-1", "value": "alpha", "blank": ""},
        {"record_id": "A-2", "value": "beta", "blank": "present"},
    ]


def test_read_rows_reads_equivalent_parquet_rows(tmp_path: Path) -> None:
    """Verify read rows reads equivalent parquet rows."""
    path = tmp_path / "rows.parquet"
    rows = [
        {"record_id": "A-1", "value": "alpha", "blank": ""},
        {"record_id": "A-2", "value": "beta", "blank": "present"},
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)

    assert read_rows(path) == rows


def test_read_rows_normalizes_parquet_scalars(tmp_path: Path) -> None:
    """Verify read rows normalizes parquet scalars."""
    path = tmp_path / "typed_rows.parquet"
    table = pa.table(
        {
            "flag": [True, False, None],
            "count": [1, 2, None],
            "ratio": [1.25, None, 3.0],
            "name": ["alpha", None, "gamma"],
        }
    )
    pq.write_table(table, path)

    assert read_rows(path) == [
        {"flag": "true", "count": "1", "ratio": "1.25", "name": "alpha"},
        {"flag": "false", "count": "2", "ratio": "", "name": ""},
        {"flag": "", "count": "", "ratio": "3.0", "name": "gamma"},
    ]


def test_read_rows_rejects_unsupported_suffix(tmp_path: Path) -> None:
    """Verify read rows rejects unsupported suffix."""
    with pytest.raises(ValueError, match="Supported extensions are: .csv, .parquet"):
        read_rows(tmp_path / "rows.json")
