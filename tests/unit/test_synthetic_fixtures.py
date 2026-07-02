"""Unit tests for synthetic fixture consistency."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
GOLDEN_PATH = ROOT / "data" / "golden" / "support_ticket_golden.csv"
BASELINE_PATH = ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"
CANDIDATE_PATH = ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
SCENARIO_ROOT = ROOT / "data" / "scenarios" / "support_ticket"

SOURCE_COLUMNS = {
    "record_id",
    "source_channel",
    "customer_tier",
    "region",
    "ticket_text",
}

GOLDEN_COLUMNS = {
    "record_id",
    "expected_issue_category",
    "expected_product_area",
    "expected_urgency",
    "expected_routing_team",
    "expected_should_escalate",
}

RUN_COLUMNS = {
    "record_id",
    "predicted_issue_category",
    "predicted_product_area",
    "predicted_urgency",
    "predicted_routing_team",
    "predicted_should_escalate",
    "model_confidence",
    "abstained",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    """Support read rows."""
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def record_ids(rows: list[dict[str, str]]) -> list[str]:
    """Support record ids."""
    return [row["record_id"] for row in rows]


def test_support_ticket_fixtures_share_one_row_per_record() -> None:
    """Verify support ticket fixtures share one row per record."""
    source_rows = read_rows(SOURCE_PATH)
    golden_rows = read_rows(GOLDEN_PATH)
    baseline_rows = read_rows(BASELINE_PATH)
    candidate_rows = read_rows(CANDIDATE_PATH)

    source_ids = record_ids(source_rows)

    assert len(source_ids) == 12
    assert len(source_ids) == len(set(source_ids))
    assert record_ids(golden_rows) == source_ids
    assert record_ids(baseline_rows) == source_ids
    assert record_ids(candidate_rows) == source_ids


def test_support_ticket_fixture_columns_are_stable() -> None:
    """Verify support ticket fixture columns are stable."""
    assert set(read_rows(SOURCE_PATH)[0]) == SOURCE_COLUMNS
    assert set(read_rows(GOLDEN_PATH)[0]) == GOLDEN_COLUMNS
    assert set(read_rows(BASELINE_PATH)[0]) == RUN_COLUMNS
    assert set(read_rows(CANDIDATE_PATH)[0]) == RUN_COLUMNS


def test_support_ticket_scenario_fixtures_match_canonical_grain() -> None:
    """Verify support ticket scenario fixtures match canonical grain."""
    source_ids = record_ids(read_rows(SOURCE_PATH))
    scenario_paths = sorted(SCENARIO_ROOT.glob("*/*.csv"))

    assert scenario_paths
    for path in scenario_paths:
        rows = read_rows(path)
        ids = record_ids(rows)
        assert ids == source_ids
        assert len(ids) == len(set(ids))
        assert set(rows[0]) == RUN_COLUMNS
