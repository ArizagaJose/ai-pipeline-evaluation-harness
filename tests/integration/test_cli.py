"""Integration tests for the command line evaluation flow."""

import csv
import json
from pathlib import Path

from ai_data_harness.cli import main

ROOT = Path(__file__).resolve().parents[2]


def test_cli_evaluate_writes_report_adjudication_and_summary_json(
    tmp_path: Path,
) -> None:
    """Verify cli evaluate writes report adjudication and summary json."""
    config_path = _write_config(
        tmp_path,
        max_false_acceptance_rate=1.0,
    )

    exit_code = main(["evaluate", "--config", str(config_path)])

    report = (tmp_path / "report.md").read_text()
    assert exit_code == 1
    assert report.startswith("# Evaluation Report")
    assert "Overall status: **NEEDS_REVIEW**" in report
    assert (tmp_path / "adjudication.json").exists()
    adjudication_json = (tmp_path / "adjudication.json").read_text()
    assert '"adjudications"' in adjudication_json
    assert '"accepted"' in adjudication_json
    assert '"critical_confusions"' in adjudication_json
    assert '"critical_wrong_rate"' in adjudication_json
    assert (tmp_path / "summary.json").exists()
    summary = (tmp_path / "summary.json").read_text()
    assert '"failed_gates"' in summary
    assert '"confidence_diagnostics"' in summary


def test_cli_degraded_candidate_exits_one(tmp_path: Path) -> None:
    """Verify cli degraded candidate exits one."""
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate_with_updates(
        candidate_path,
        {
            "TKT-0001": {"predicted_issue_category": "feedback"},
            "TKT-0005": {"predicted_issue_category": "feedback"},
            "TKT-0009": {"predicted_issue_category": "feedback"},
        },
    )
    config_path = _write_config(tmp_path, candidate_path=candidate_path)

    exit_code = main(["evaluate", "--config", str(config_path)])

    assert exit_code == 1
    assert "Overall status: **FAILED**" in (tmp_path / "report.md").read_text()


def test_cli_false_acceptance_gate_exits_one(tmp_path: Path) -> None:
    """Verify cli false acceptance gate exits one."""
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate_with_updates(
        candidate_path,
        {"TKT-0001": {"predicted_product_area": "payments"}},
    )
    config_path = _write_config(
        tmp_path,
        candidate_path=candidate_path,
        max_false_acceptance_rate=0.0,
    )

    exit_code = main(["evaluate", "--config", str(config_path)])

    assert exit_code == 1
    assert "max_false_acceptance_rate" in (tmp_path / "report.md").read_text()


def test_cli_segment_regression_exits_one_when_global_gates_pass(
    tmp_path: Path,
) -> None:
    """Verify cli segment regression exits one when global gates pass."""
    candidate_path = tmp_path / "candidate.csv"
    _write_candidate_with_updates(
        candidate_path,
        {
            "TKT-0001": {"predicted_urgency": "low"},
            "TKT-0004": {"predicted_urgency": "low"},
            "TKT-0010": {"predicted_urgency": "low"},
        },
    )
    config_path = _write_segment_config(tmp_path, candidate_path)

    exit_code = main(["evaluate", "--config", str(config_path)])

    report = (tmp_path / "report.md").read_text()
    assert exit_code == 1
    assert "## Segment Regression" in report
    assert "segment_max_accuracy_drop" in report


def test_cli_missing_config_path_exits_two(tmp_path: Path) -> None:
    """Verify cli missing config path exits two."""
    exit_code = main(["evaluate", "--config", str(tmp_path / "missing.json")])

    assert exit_code == 2


def _write_config(
    tmp_path: Path,
    candidate_path: Path | None = None,
    *,
    max_false_acceptance_rate: float = 0.1,
) -> Path:
    """Support write config."""
    candidate = (
        candidate_path
        or ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
    )
    config_path = tmp_path / "evaluation.json"
    config_path.write_text(
        (ROOT / "examples" / "support_ticket_evaluation.json")
        .read_text()
        .replace(
            "../contracts/support_ticket_output_contract.json",
            str(ROOT / "contracts" / "support_ticket_output_contract.json"),
        )
        .replace(
            "../data/golden/support_ticket_golden.csv",
            str(ROOT / "data" / "golden" / "support_ticket_golden.csv"),
        )
        .replace(
            "../data/runs/support_ticket_baseline_outputs.csv",
            str(ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"),
        )
        .replace("../data/runs/support_ticket_candidate_outputs.csv", str(candidate))
        .replace("../reports/support_ticket_evaluation.md", str(tmp_path / "report.md"))
        .replace(
            "../reports/support_ticket_adjudication.json",
            str(tmp_path / "adjudication.json"),
        )
        .replace(
            "../reports/support_ticket_run_summary.json",
            str(tmp_path / "summary.json"),
        )
        .replace(
            '"max_false_acceptance_rate": 0.1',
            f'"max_false_acceptance_rate": {max_false_acceptance_rate}',
        )
    )
    return config_path


def _write_segment_config(tmp_path: Path, candidate_path: Path) -> Path:
    """Support write segment config."""
    data = json.loads(
        (ROOT / "examples" / "support_ticket_evaluation.json").read_text()
    )
    data["paths"].update(
        {
            "contract": str(ROOT / "contracts" / "support_ticket_output_contract.json"),
            "golden": str(ROOT / "data" / "golden" / "support_ticket_golden.csv"),
            "source": str(
                ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
            ),
            "baseline_output": str(
                ROOT / "data" / "runs" / "support_ticket_baseline_outputs.csv"
            ),
            "candidate_output": str(candidate_path),
            "report": str(tmp_path / "report.md"),
            "adjudication": str(tmp_path / "adjudication.json"),
            "summary": str(tmp_path / "summary.json"),
        }
    )
    data["segment_columns"] = ["customer_tier"]
    data["segment_regression_gates"] = [
        {
            "attribute": "urgency",
            "segment_column": "customer_tier",
            "segment_value": "enterprise",
            "max_accuracy_drop": 0.0,
            "min_segment_size": 2,
        }
    ]

    config_path = tmp_path / "evaluation.json"
    config_path.write_text(json.dumps(data))
    return config_path


def _write_candidate_with_updates(
    path: Path,
    updates: dict[str, dict[str, str]],
) -> None:
    """Support write candidate with updates."""
    source_path = ROOT / "data" / "runs" / "support_ticket_candidate_outputs.csv"
    with source_path.open(newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fieldnames = reader.fieldnames

    assert fieldnames is not None
    by_record_id = {row["record_id"]: row for row in rows}
    assert set(updates) <= set(by_record_id)
    for record_id, field_updates in updates.items():
        row = by_record_id[record_id]
        assert set(field_updates) <= set(row)
        row.update(field_updates)

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
