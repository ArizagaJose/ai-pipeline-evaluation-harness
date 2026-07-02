"""Unit tests for candidate adjudication semantics."""

from ai_data_harness.adjudication import (
    AdjudicationRow,
    CriticalConfusionCount,
    SeverityReviewCount,
    _compute_admissibility_metrics,
    adjudicate_candidate,
    admissibility_metrics_json,
    critical_confusion_counts,
    severity_review_counts,
)
from ai_data_harness.contracts import parse_contract, validate_rows
from ai_data_harness.metrics import AttributeMapping


def test_adjudication_classifies_configured_cell_outcomes() -> None:
    """Verify adjudication classifies configured cell outcomes."""
    contract = _contract()
    golden_rows = [
        {
            "record_id": "R1",
            "expected_category": "billing",
            "expected_team": "billing_ops",
            "expected_urgency": "high",
            "expected_escalate": "true",
            "expected_reason": "known",
            "expected_missing": "present",
        }
    ]
    candidate_rows = [
        {
            "record_id": "R1",
            "predicted_category": "billing",
            "predicted_team": "identity_support",
            "predicted_urgency": "__ABSTAIN__",
            "predicted_escalate": "maybe",
            "predicted_reason": "different",
            "abstained": "false",
        }
    ]

    result = adjudicate_candidate(
        golden_rows=golden_rows,
        candidate_rows=candidate_rows,
        attributes=(
            AttributeMapping("category", "expected_category", "predicted_category"),
            AttributeMapping("team", "expected_team", "predicted_team"),
            AttributeMapping("urgency", "expected_urgency", "predicted_urgency"),
            AttributeMapping("escalate", "expected_escalate", "predicted_escalate"),
            AttributeMapping("reason", "expected_reason", "predicted_reason"),
            AttributeMapping("missing", "expected_missing", "predicted_missing"),
        ),
        contract=contract,
        record_id_column="record_id",
        abstention_column="abstained",
    )

    rows = {
        adjudication.attribute: adjudication for adjudication in result.adjudications
    }
    outcomes = {attribute: row.outcome for attribute, row in rows.items()}
    assert outcomes == {
        "category": "correct",
        "team": "incorrect",
        "urgency": "abstained",
        "escalate": "invalid",
        "reason": "incorrect",
        "missing": "missing",
    }

    assert rows["team"].accepted is True
    assert rows["team"].requires_review is False
    assert rows["team"].critical is False

    assert rows["reason"].accepted is False
    assert rows["reason"].requires_review is True
    assert rows["reason"].critical is True

    assert rows["urgency"].accepted is False
    assert rows["urgency"].requires_review is True

    assert rows["escalate"].accepted is False
    assert rows["escalate"].requires_review is True

    assert rows["missing"].accepted is False
    assert rows["missing"].requires_review is True

    assert result.admissibility_metrics.total_cells == 6
    assert result.admissibility_metrics.critical_cells == 3
    assert result.admissibility_metrics.accepted_cells == 2
    assert result.admissibility_metrics.requires_review_cells == 4
    assert result.admissibility_metrics.accuracy == 1 / 6
    assert result.admissibility_metrics.abstention_rate == 1 / 6
    assert result.admissibility_metrics.invalid_rate == 1 / 6
    assert result.admissibility_metrics.incorrect_accepted_cells == 1
    assert result.admissibility_metrics.false_acceptance_rate == 1 / 6
    assert result.admissibility_metrics.critical_wrong_cells == 1
    assert result.admissibility_metrics.critical_wrong_rate == 1 / 3
    assert result.admissibility_metrics.review_incorrect_cells == 1
    assert result.admissibility_metrics.review_incorrect_rate == 1 / 4
    assert result.admissibility_metrics.review_abstained_rate == 1 / 4
    assert result.admissibility_metrics.review_invalid_rate == 1 / 4
    assert result.admissibility_metrics.review_missing_rate == 1 / 4
    assert (
        result.admissibility_metrics.review_incorrect_rate
        + result.admissibility_metrics.review_abstained_rate
        + result.admissibility_metrics.review_invalid_rate
        + result.admissibility_metrics.review_missing_rate
        == 1.0
    )
    assert result.critical_confusions == (
        CriticalConfusionCount(
            attribute="reason",
            expected_value="known",
            candidate_value="different",
            count=1,
        ),
    )


def test_severity_override_routes_non_critical_wrong_cell_to_review() -> None:
    """Verify severity override routes non critical wrong cell to review."""
    contract = _contract_with_team_override()
    result = adjudicate_candidate(
        golden_rows=[
            {
                "record_id": "R1",
                "expected_team": "billing_ops",
            }
        ],
        candidate_rows=[
            {
                "record_id": "R1",
                "predicted_team": "identity_support",
                "abstained": "false",
            }
        ],
        attributes=(AttributeMapping("team", "expected_team", "predicted_team"),),
        contract=contract,
        record_id_column="record_id",
        abstention_column="abstained",
    )

    row = result.adjudications[0]

    assert row.outcome == "incorrect"
    assert row.accepted is False
    assert row.requires_review is True
    assert row.review_severity == "high"
    assert row.reason == "Billing team misses should be reviewed."
    assert result.admissibility_metrics.false_acceptance_rate == 0.0
    assert result.admissibility_metrics.incorrect_accepted_cells == 0
    assert result.severity_review_counts == (
        SeverityReviewCount(
            attribute="team",
            expected_value="billing_ops",
            candidate_value="identity_support",
            severity="high",
            reason="Billing team misses should be reviewed.",
            count=1,
        ),
    )


def test_non_matching_non_critical_wrong_cell_remains_accepted() -> None:
    """Verify non matching non critical wrong cell remains accepted."""
    contract = _contract_with_team_override()
    result = adjudicate_candidate(
        golden_rows=[
            {
                "record_id": "R1",
                "expected_team": "identity_support",
            }
        ],
        candidate_rows=[
            {
                "record_id": "R1",
                "predicted_team": "billing_ops",
                "abstained": "false",
            }
        ],
        attributes=(AttributeMapping("team", "expected_team", "predicted_team"),),
        contract=contract,
        record_id_column="record_id",
        abstention_column="abstained",
    )

    row = result.adjudications[0]

    assert row.outcome == "incorrect"
    assert row.accepted is True
    assert row.requires_review is False
    assert row.review_severity is None
    assert result.admissibility_metrics.false_acceptance_rate == 1.0
    assert result.severity_review_counts == ()


def test_adjudication_matches_candidate_rows_by_record_id_not_row_position() -> None:
    """Verify adjudication matches candidate rows by record id not row position."""
    result = adjudicate_candidate(
        golden_rows=[
            {"record_id": "R2", "expected_category": "access"},
            {"record_id": "R1", "expected_category": "billing"},
        ],
        candidate_rows=[
            {
                "record_id": "R1",
                "predicted_category": "billing",
                "abstained": "false",
            },
            {
                "record_id": "R2",
                "predicted_category": "access",
                "abstained": "false",
            },
        ],
        attributes=(
            AttributeMapping("category", "expected_category", "predicted_category"),
        ),
        contract=_contract(),
        record_id_column="record_id",
        abstention_column="abstained",
    )

    assert [row.record_id for row in result.adjudications] == ["R2", "R1"]
    assert [row.outcome for row in result.adjudications] == ["correct", "correct"]


def test_false_acceptance_only_means_incorrect_and_accepted() -> None:
    """Verify false acceptance only means outcome incorrect and accepted true."""
    metrics = _compute_admissibility_metrics(
        (
            _adjudication("category", "billing", "billing", "correct"),
            _adjudication(
                "team",
                "billing_ops",
                "identity_support",
                "incorrect",
                accepted=True,
            ),
            _adjudication(
                "urgency",
                "critical",
                "medium",
                "incorrect",
                critical=True,
                accepted=False,
            ),
            _adjudication(
                "escalate",
                "true",
                "maybe",
                "invalid",
                accepted=True,
            ),
            _adjudication(
                "reason",
                "known",
                "different",
                "abstained",
                accepted=True,
            ),
        )
    )

    assert metrics.incorrect_accepted_cells == 1
    assert metrics.false_acceptance_rate == 1 / 5


def test_review_queue_composition_excludes_accepted_incorrect_cells() -> None:
    """Verify review composition counts only review-routed incorrect cells."""
    metrics = _compute_admissibility_metrics(
        (
            _adjudication("category", "billing", "billing", "correct"),
            _adjudication(
                "team",
                "billing_ops",
                "identity_support",
                "incorrect",
                accepted=True,
            ),
            _adjudication(
                "urgency",
                "critical",
                "medium",
                "incorrect",
                critical=True,
                accepted=False,
            ),
        )
    )

    assert metrics.requires_review_cells == 1
    assert metrics.review_incorrect_cells == 1
    assert metrics.review_incorrect_rate == 1.0
    assert metrics.review_abstained_rate == 0.0
    assert metrics.review_invalid_rate == 0.0
    assert metrics.review_missing_rate == 0.0


def test_review_queue_composition_is_zero_safe_with_no_review_cells() -> None:
    """Verify review composition rates default to zero with no review queue."""
    metrics = _compute_admissibility_metrics(
        (_adjudication("category", "billing", "billing", "correct"),)
    )

    assert metrics.requires_review_cells == 0
    assert metrics.review_incorrect_rate == 0.0
    assert metrics.review_abstained_rate == 0.0
    assert metrics.review_invalid_rate == 0.0
    assert metrics.review_missing_rate == 0.0


def test_critical_wrong_cell_with_matching_override_stays_review_routed() -> None:
    """Verify critical wrong values require review and are not false acceptances."""
    contract = _contract_with_critical_reason_override()
    result = adjudicate_candidate(
        golden_rows=[
            {
                "record_id": "R1",
                "expected_reason": "known",
            }
        ],
        candidate_rows=[
            {
                "record_id": "R1",
                "predicted_reason": "different",
                "abstained": "false",
            }
        ],
        attributes=(AttributeMapping("reason", "expected_reason", "predicted_reason"),),
        contract=contract,
        record_id_column="record_id",
        abstention_column="abstained",
    )

    row = result.adjudications[0]

    assert row.outcome == "incorrect"
    assert row.accepted is False
    assert row.requires_review is True
    assert row.critical is True
    assert row.review_severity == "critical"
    assert row.reason == "Known reason changes are critical review cases."
    assert result.admissibility_metrics.false_acceptance_rate == 0.0
    assert result.admissibility_metrics.incorrect_accepted_cells == 0
    assert result.admissibility_metrics.critical_wrong_cells == 1


def test_admissibility_metrics_json_uses_cell_level_abstention_name() -> None:
    """Verify public admissibility JSON names cell-level abstention explicitly."""
    metrics = _compute_admissibility_metrics(
        (
            _adjudication("category", "billing", "billing", "correct"),
            _adjudication(
                "urgency",
                "critical",
                "__ABSTAIN__",
                "abstained",
                accepted=False,
            ),
        )
    )

    data = admissibility_metrics_json(metrics)

    assert data["cell_level_abstention_rate"] == 0.5
    assert "abstention_rate" not in data


def test_critical_confusion_counts_include_only_wrong_critical_values() -> None:
    """Verify critical confusion counts include only wrong critical values."""
    adjudications = (
        _adjudication("urgency", "high", "medium", "incorrect", critical=True),
        _adjudication("urgency", "high", "medium", "incorrect", critical=True),
        _adjudication("category", "billing", "access", "incorrect", critical=True),
        _adjudication("category", "billing", "access", "correct", critical=True),
        _adjudication("category", "billing", "unknown", "abstained", critical=True),
        _adjudication("category", "billing", "invalid", "invalid", critical=True),
        _adjudication("team", "billing_ops", "identity_support", "incorrect"),
    )

    assert critical_confusion_counts(adjudications) == (
        CriticalConfusionCount(
            attribute="urgency",
            expected_value="high",
            candidate_value="medium",
            count=2,
        ),
        CriticalConfusionCount(
            attribute="category",
            expected_value="billing",
            candidate_value="access",
            count=1,
        ),
    )


def test_severity_review_counts_include_only_override_matches() -> None:
    """Verify severity review counts include only override matches."""
    adjudications = (
        _adjudication(
            "team",
            "billing_ops",
            "identity_support",
            "incorrect",
            review_severity="high",
            reason="Billing team misses should be reviewed.",
        ),
        _adjudication(
            "team",
            "billing_ops",
            "identity_support",
            "incorrect",
            review_severity="high",
            reason="Billing team misses should be reviewed.",
        ),
        _adjudication("team", "identity_support", "billing_ops", "incorrect"),
    )

    assert severity_review_counts(adjudications) == (
        SeverityReviewCount(
            attribute="team",
            expected_value="billing_ops",
            candidate_value="identity_support",
            severity="high",
            reason="Billing team misses should be reviewed.",
            count=2,
        ),
    )


def test_abstention_values_are_contract_admissible_before_allowed_values() -> None:
    """Verify abstention values are contract admissible before allowed values."""
    contract = _contract()
    rows = [
        {
            "record_id": "R1",
            "predicted_category": "billing",
            "predicted_team": "billing_ops",
            "predicted_urgency": "__ABSTAIN__",
            "predicted_escalate": "true",
            "predicted_reason": "known",
            "predicted_missing": "present",
            "abstained": "false",
        }
    ]

    assert validate_rows(rows, contract).passed


def test_legacy_row_level_abstention_applies_to_all_configured_attributes() -> None:
    """Verify legacy row level abstention applies to all configured attributes."""
    contract = _contract()
    result = adjudicate_candidate(
        golden_rows=[
            {
                "record_id": "R1",
                "expected_category": "billing",
                "expected_team": "billing_ops",
            }
        ],
        candidate_rows=[
            {
                "record_id": "R1",
                "predicted_category": "billing",
                "predicted_team": "billing_ops",
                "abstained": "true",
            }
        ],
        attributes=(
            AttributeMapping("category", "expected_category", "predicted_category"),
            AttributeMapping("team", "expected_team", "predicted_team"),
        ),
        contract=contract,
        record_id_column="record_id",
        abstention_column="abstained",
    )

    assert [row.outcome for row in result.adjudications] == ["abstained", "abstained"]


def _adjudication(
    attribute: str,
    expected_value: str,
    candidate_value: str,
    outcome: str,
    *,
    critical: bool = False,
    accepted: bool | None = None,
    review_severity: str | None = None,
    reason: str = "test row",
) -> AdjudicationRow:
    """Support adjudication."""
    resolved_accepted = outcome == "correct" if accepted is None else accepted
    return AdjudicationRow(
        record_id=f"{attribute}-{expected_value}-{candidate_value}-{outcome}",
        attribute=attribute,
        expected_value=expected_value,
        candidate_value=candidate_value,
        outcome=outcome,
        accepted=resolved_accepted,
        requires_review=critical and outcome != "correct",
        critical=critical,
        review_severity=review_severity,
        reason=reason,
    )


def _contract():
    """Support contract."""
    return parse_contract(_contract_data())


def _contract_with_team_override():
    """Support contract with team override."""
    data = _contract_data()
    data["columns"]["predicted_team"]["severity_overrides"] = [
        {
            "expected_value": "billing_ops",
            "candidate_value": "identity_support",
            "severity": "high",
            "reason": "Billing team misses should be reviewed.",
        }
    ]
    return parse_contract(data)


def _contract_with_critical_reason_override():
    """Support contract with critical reason override."""
    data = _contract_data()
    data["columns"]["predicted_reason"]["severity_overrides"] = [
        {
            "expected_value": "known",
            "candidate_value": "different",
            "severity": "critical",
            "reason": "Known reason changes are critical review cases.",
        }
    ]
    return parse_contract(data)


def _contract_data():
    """Support contract data."""
    return {
        "version": 1,
        "record_id_column": "record_id",
        "columns": {
            "record_id": {
                "type": "string",
                "required": True,
                "nullable": False,
            },
            "predicted_category": {
                "type": "string",
                "required": True,
                "nullable": False,
                "allowed_values": ["billing", "access"],
            },
            "predicted_team": {
                "type": "string",
                "required": True,
                "nullable": False,
                "allowed_values": ["billing_ops", "identity_support"],
            },
            "predicted_urgency": {
                "type": "string",
                "required": True,
                "nullable": False,
                "allowed_values": ["low", "high"],
                "abstention_values": ["__ABSTAIN__"],
                "critical": True,
            },
            "predicted_escalate": {
                "type": "boolean",
                "required": True,
                "nullable": False,
                "critical": True,
            },
            "predicted_reason": {
                "type": "string",
                "required": True,
                "nullable": False,
                "allowed_values": ["known", "different"],
                "critical": True,
            },
            "predicted_missing": {
                "type": "string",
                "required": True,
                "nullable": False,
            },
            "abstained": {
                "type": "boolean",
                "required": True,
                "nullable": False,
            },
        },
    }
