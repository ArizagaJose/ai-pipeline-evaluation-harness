"""Unit tests for evaluation config parsing and validation."""

import json
from pathlib import Path

import pytest

from ai_data_harness.config import EvaluationConfigError, load_evaluation_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "examples" / "support_ticket_evaluation.json"


def test_segment_config_omitted_preserves_existing_behavior() -> None:
    """Verify segment config omitted preserves existing behavior."""
    config = load_evaluation_config(CONFIG_PATH)

    assert config.source_path is None
    assert config.confidence_column == "model_confidence"
    assert config.segment_columns == ()
    assert config.segment_regression_gates == ()
    assert config.severity_review_gates == ()


def test_confidence_column_can_be_configured(tmp_path: Path) -> None:
    """Verify confidence column can be configured."""
    config_path = _write_config(tmp_path, confidence_column="confidence_score")

    config = load_evaluation_config(config_path)

    assert config.confidence_column == "confidence_score"


def test_confidence_column_must_be_non_empty_string(tmp_path: Path) -> None:
    """Verify confidence column must be non empty string."""
    config_path = _write_config(tmp_path, confidence_column="")

    with pytest.raises(EvaluationConfigError, match="confidence_column"):
        load_evaluation_config(config_path)


def test_severity_review_gate_config_loads(tmp_path: Path) -> None:
    """Verify severity review gate config loads."""
    config_path = _write_config(
        tmp_path,
        severity_review_gates=[
            {"severity": "critical", "max_count": 0},
            {"severity": "high", "max_count": 1},
        ],
    )

    config = load_evaluation_config(config_path)

    assert [gate.severity for gate in config.severity_review_gates] == [
        "critical",
        "high",
    ]
    assert [gate.max_count for gate in config.severity_review_gates] == [0, 1]


def test_severity_review_gate_rejects_unknown_severity(tmp_path: Path) -> None:
    """Verify severity review gate rejects unknown severity."""
    config_path = _write_config(
        tmp_path,
        severity_review_gates=[{"severity": "low", "max_count": 0}],
    )

    with pytest.raises(EvaluationConfigError, match="severity.*must be one of"):
        load_evaluation_config(config_path)


@pytest.mark.parametrize("max_count", [-1, 1.5, "1", True])
def test_severity_review_gate_rejects_invalid_max_count(
    tmp_path: Path,
    max_count: object,
) -> None:
    """Verify severity review gate rejects invalid max count."""
    config_path = _write_config(
        tmp_path,
        severity_review_gates=[{"severity": "high", "max_count": max_count}],
    )

    with pytest.raises(
        EvaluationConfigError, match="max_count.*greater than or equal to 0|integer"
    ):
        load_evaluation_config(config_path)


def test_severity_review_gate_rejects_duplicate_severity(tmp_path: Path) -> None:
    """Verify severity review gate rejects duplicate severity."""
    config_path = _write_config(
        tmp_path,
        severity_review_gates=[
            {"severity": "high", "max_count": 0},
            {"severity": "high", "max_count": 1},
        ],
    )

    with pytest.raises(EvaluationConfigError, match="duplicate severity 'high'"):
        load_evaluation_config(config_path)


def test_segment_gate_requires_source_and_segment_columns(tmp_path: Path) -> None:
    """Verify segment gate requires source and segment columns."""
    config_path = _write_config(
        tmp_path,
        segment_regression_gates=[
            {
                "attribute": "urgency",
                "segment_column": "customer_tier",
                "segment_value": "enterprise",
                "max_accuracy_drop": 0.0,
                "min_segment_size": 2,
            }
        ],
    )

    with pytest.raises(EvaluationConfigError, match="segment_columns.*required"):
        load_evaluation_config(config_path)


def test_segment_gate_requires_configured_segment_column(tmp_path: Path) -> None:
    """Verify segment gate requires configured segment column."""
    config_path = _write_config(
        tmp_path,
        paths={
            "source": str(
                ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
            )
        },
        segment_columns=["region"],
        segment_regression_gates=[
            {
                "attribute": "urgency",
                "segment_column": "customer_tier",
                "segment_value": "enterprise",
                "max_accuracy_drop": 0.0,
                "min_segment_size": 2,
            }
        ],
    )

    with pytest.raises(EvaluationConfigError, match="not listed in segment_columns"):
        load_evaluation_config(config_path)


def test_segment_gate_rejects_invalid_rate(tmp_path: Path) -> None:
    """Verify segment gate rejects invalid rate."""
    config_path = _write_config(
        tmp_path,
        paths={
            "source": str(
                ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
            )
        },
        segment_columns=["customer_tier"],
        segment_regression_gates=[
            {
                "attribute": "urgency",
                "segment_column": "customer_tier",
                "segment_value": "enterprise",
                "max_accuracy_drop": 1.5,
                "min_segment_size": 2,
            }
        ],
    )

    with pytest.raises(
        EvaluationConfigError, match="max_accuracy_drop.*between 0 and 1"
    ):
        load_evaluation_config(config_path)


def test_segment_gate_requires_min_segment_size(tmp_path: Path) -> None:
    """Verify segment gate requires min segment size."""
    config_path = _write_config(
        tmp_path,
        paths={
            "source": str(
                ROOT / "data" / "synthetic" / "support_ticket_source_records.csv"
            )
        },
        segment_columns=["customer_tier"],
        segment_regression_gates=[
            {
                "attribute": "urgency",
                "segment_column": "customer_tier",
                "segment_value": "enterprise",
                "max_accuracy_drop": 0.0,
            }
        ],
    )

    with pytest.raises(
        EvaluationConfigError, match="min_segment_size.*positive integer"
    ):
        load_evaluation_config(config_path)


def _write_config(
    tmp_path: Path,
    *,
    paths: dict[str, str] | None = None,
    confidence_column: object | None = None,
    segment_columns: list[str] | None = None,
    segment_regression_gates: list[dict[str, object]] | None = None,
    severity_review_gates: list[dict[str, object]] | None = None,
) -> Path:
    """Support write config."""
    data = json.loads(CONFIG_PATH.read_text())
    data["paths"].update(paths or {})
    if confidence_column is not None:
        data["confidence_column"] = confidence_column
    if segment_columns is not None:
        data["segment_columns"] = segment_columns
    if segment_regression_gates is not None:
        data["segment_regression_gates"] = segment_regression_gates
    if severity_review_gates is not None:
        data["severity_review_gates"] = severity_review_gates

    config_path = tmp_path / "evaluation.json"
    config_path.write_text(json.dumps(data))
    return config_path
