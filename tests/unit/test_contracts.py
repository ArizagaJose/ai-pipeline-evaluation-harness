"""Unit tests for output contract parsing and validation."""

import csv
from pathlib import Path

import pytest

from ai_data_harness.contracts import load_contract, parse_contract, validate_rows

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "support_ticket_output_contract.json"
BASELINE_PATH = ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"
CANDIDATE_PATH = ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"


def read_rows(path: Path) -> list[dict[str, str]]:
    """Support read rows."""
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def issue_codes(rows: list[dict[str, str]]) -> set[str]:
    """Support issue codes."""
    contract = load_contract(CONTRACT_PATH)
    return {issue.code for issue in validate_rows(rows, contract).issues}


def test_support_ticket_run_outputs_pass_contract() -> None:
    """Verify support ticket run outputs pass contract."""
    contract = load_contract(CONTRACT_PATH)

    assert validate_rows(read_rows(BASELINE_PATH), contract).passed
    assert validate_rows(read_rows(CANDIDATE_PATH), contract).passed


def test_contract_validation_fails_for_missing_required_column() -> None:
    """Verify contract validation fails for missing required column."""
    rows = read_rows(CANDIDATE_PATH)
    for row in rows:
        del row["predicted_urgency"]

    assert "missing_required_column" in issue_codes(rows)


def test_contract_validation_fails_for_invalid_allowed_value() -> None:
    """Verify contract validation fails for invalid allowed value."""
    rows = read_rows(CANDIDATE_PATH)
    rows[0]["predicted_issue_category"] = "refund"

    result = validate_rows(rows, load_contract(CONTRACT_PATH))

    issue = next(
        issue for issue in result.issues if issue.code == "invalid_allowed_value"
    )
    assert issue.column == "predicted_issue_category"
    assert issue.record_id == "TKT-0001"
    assert issue.row_number == 2
    assert issue.value == "refund"


def test_contract_validation_fails_for_null_value() -> None:
    """Verify contract validation fails for null value."""
    rows = read_rows(CANDIDATE_PATH)
    rows[0]["predicted_routing_team"] = ""

    assert "null_value" in issue_codes(rows)


def test_contract_validation_fails_for_duplicate_record_id() -> None:
    """Verify contract validation fails for duplicate record id."""
    rows = read_rows(CANDIDATE_PATH)
    rows[1]["record_id"] = rows[0]["record_id"]

    result = validate_rows(rows, load_contract(CONTRACT_PATH))

    issue = next(
        issue for issue in result.issues if issue.code == "duplicate_record_id"
    )
    assert issue.column == "record_id"
    assert issue.record_id == "TKT-0001"
    assert issue.row_number == 3
    assert issue.value == "TKT-0001"


def test_contract_validation_fails_for_invalid_type() -> None:
    """Verify contract validation fails for invalid type."""
    rows = read_rows(CANDIDATE_PATH)
    rows[0]["model_confidence"] = "high"

    assert "invalid_type" in issue_codes(rows)


def test_contract_rejects_unknown_column_type(tmp_path: Path) -> None:
    """Verify contract rejects unknown column type."""
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(
        """
        {
          "version": 1,
          "record_id_column": "record_id",
          "columns": {
            "record_id": {"type": "uuid", "required": true, "nullable": false}
          }
        }
        """
    )

    with pytest.raises(ValueError, match="unsupported type"):
        load_contract(contract_path)


def test_contract_parser_accepts_valid_severity_override() -> None:
    """Verify contract parser accepts valid severity override."""
    contract = parse_contract(_contract_with_override())

    product_area = next(
        column for column in contract.columns if column.name == "predicted_product_area"
    )

    assert len(product_area.review_overrides) == 1
    assert product_area.review_overrides[0].expected_value == "subscriptions"
    assert product_area.review_overrides[0].candidate_value == "payments"
    assert product_area.review_overrides[0].severity == "high"


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda override: override.update({"severity": "low"}),
            "severity.*must be one of",
        ),
        (
            lambda override: override.update({"reason": "   "}),
            "reason must be a non-empty string",
        ),
        (
            lambda override: override.update({"candidate_value": "unknown"}),
            "candidate_value must not be an abstention value",
        ),
        (
            lambda override: override.update({"candidate_value": "refunds"}),
            "candidate_value must be in allowed_values",
        ),
    ],
)
def test_contract_parser_rejects_invalid_severity_override(
    mutate,
    match: str,
) -> None:
    """Verify contract parser rejects invalid severity override."""
    contract = _contract_with_override()
    override = contract["columns"]["predicted_product_area"]["severity_overrides"][0]
    mutate(override)

    with pytest.raises(ValueError, match=match):
        parse_contract(contract)


def test_contract_parser_rejects_duplicate_severity_override() -> None:
    """Verify contract parser rejects duplicate severity override."""
    contract = _contract_with_override()
    overrides = contract["columns"]["predicted_product_area"]["severity_overrides"]
    overrides.append(dict(overrides[0]))

    with pytest.raises(ValueError, match="duplicate severity override"):
        parse_contract(contract)


def _contract_with_override() -> dict:
    """Support contract with override."""
    return {
        "version": 1,
        "record_id_column": "record_id",
        "columns": {
            "record_id": {
                "type": "string",
                "required": True,
                "nullable": False,
            },
            "predicted_product_area": {
                "type": "string",
                "required": True,
                "nullable": False,
                "allowed_values": ["payments", "subscriptions", "unknown"],
                "abstention_values": ["unknown"],
                "severity_overrides": [
                    {
                        "expected_value": "subscriptions",
                        "candidate_value": "payments",
                        "severity": "high",
                        "reason": "Subscription billing mistakes should be reviewed.",
                    }
                ],
            },
        },
    }
