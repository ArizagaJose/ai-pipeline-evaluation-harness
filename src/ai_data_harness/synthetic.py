"""Deterministic synthetic scale-fixture generation.

This module generates a population-sized synthetic support-ticket run
(baseline and candidate Parquet outputs) plus a small golden CSV sample,
so contract validation can be exercised at population scale while semantic
scoring stays explicitly sample-level. Values match
``contracts/support_ticket_output_contract.json``.
"""

import csv
import random
from dataclasses import dataclass
from pathlib import Path

ISSUE_CATEGORIES = (
    "access",
    "billing",
    "feedback",
    "how_to",
    "integration",
    "performance",
)
PRODUCT_AREAS = (
    "account_admin",
    "analytics",
    "api",
    "authentication",
    "mobile",
    "notifications",
    "payments",
    "permissions",
    "reporting",
    "subscriptions",
)
URGENCIES = ("low", "medium", "high", "critical")
ROUTING_TEAMS = (
    "analytics_support",
    "app_support",
    "billing_ops",
    "customer_enablement",
    "identity_support",
    "platform_integrations",
    "product_feedback",
    "security_response",
)
ABSTENTION_VALUE = "unknown"

OUTPUT_COLUMNS = (
    "record_id",
    "predicted_issue_category",
    "predicted_product_area",
    "predicted_urgency",
    "predicted_routing_team",
    "predicted_should_escalate",
    "model_confidence",
    "abstained",
)
GOLDEN_COLUMNS = (
    "record_id",
    "expected_issue_category",
    "expected_product_area",
    "expected_urgency",
    "expected_routing_team",
    "expected_should_escalate",
)


@dataclass(frozen=True)
class RunQualityProfile:
    """Error and abstention rates used to derive one output run from truth."""

    correct_rate: float
    attribute_abstention_rate: float
    row_abstention_rate: float


BASELINE_PROFILE = RunQualityProfile(
    correct_rate=0.90,
    attribute_abstention_rate=0.03,
    row_abstention_rate=0.02,
)
CANDIDATE_PROFILE = RunQualityProfile(
    correct_rate=0.94,
    attribute_abstention_rate=0.015,
    row_abstention_rate=0.01,
)


@dataclass(frozen=True)
class ScaleFixturePaths:
    """Paths written by one scale-fixture generation run."""

    golden_path: Path
    baseline_output_path: Path
    candidate_output_path: Path


def generate_scale_fixture(
    output_dir: str | Path,
    *,
    rows: int = 1_000_000,
    golden_rows: int = 2_000,
    seed: int = 20260702,
) -> ScaleFixturePaths:
    """Generate a population-sized synthetic run with a small golden sample.

    The same seed always produces the same files. Baseline and candidate
    outputs cover the full population; the golden CSV covers a deterministic
    random sample of it, so evaluations run with sample-level semantic
    scoring over population-level files.

    Args:
        output_dir: Directory to write the generated files into.
        rows: Population size for baseline and candidate outputs.
        golden_rows: Golden sample size; must not exceed ``rows``.
        seed: Seed for the deterministic random generator.

    Returns:
        Paths of the golden, baseline, and candidate files.

    Raises:
        ValueError: If ``rows`` or ``golden_rows`` are out of range.
        OSError: If the output files cannot be written.
    """
    if rows < 1:
        msg = "rows must be at least 1."
        raise ValueError(msg)
    if not 1 <= golden_rows <= rows:
        msg = "golden_rows must be between 1 and rows."
        raise ValueError(msg)

    rng = random.Random(seed)
    golden_indexes = frozenset(rng.sample(range(rows), golden_rows))

    golden: list[dict[str, str]] = []
    baseline = _empty_columns()
    candidate = _empty_columns()
    for index in range(rows):
        record_id = f"TKT-{index:07d}"
        truth = _generate_truth(rng)
        if index in golden_indexes:
            golden.append(_golden_row(record_id, truth))
        _append_output_row(baseline, record_id, truth, BASELINE_PROFILE, rng)
        _append_output_row(candidate, record_id, truth, CANDIDATE_PROFILE, rng)

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = ScaleFixturePaths(
        golden_path=target_dir / "support_ticket_scale_golden.csv",
        baseline_output_path=target_dir / "support_ticket_scale_baseline.parquet",
        candidate_output_path=target_dir / "support_ticket_scale_candidate.parquet",
    )
    _write_golden_csv(paths.golden_path, golden)
    _write_output_parquet(paths.baseline_output_path, baseline)
    _write_output_parquet(paths.candidate_output_path, candidate)
    return paths


def _generate_truth(rng: random.Random) -> dict[str, str]:
    """Draw one record's true attribute values."""
    return {
        "issue_category": rng.choice(ISSUE_CATEGORIES),
        "product_area": rng.choice(PRODUCT_AREAS),
        "urgency": rng.choice(URGENCIES),
        "routing_team": rng.choice(ROUTING_TEAMS),
        "should_escalate": rng.choice(("true", "false")),
    }


def _golden_row(record_id: str, truth: dict[str, str]) -> dict[str, str]:
    """Build one golden CSV row from a record's truth."""
    return {
        "record_id": record_id,
        "expected_issue_category": truth["issue_category"],
        "expected_product_area": truth["product_area"],
        "expected_urgency": truth["urgency"],
        "expected_routing_team": truth["routing_team"],
        "expected_should_escalate": truth["should_escalate"],
    }


def _empty_columns() -> dict[str, list[str | bool | float]]:
    """Build empty output column buffers."""
    return {column: [] for column in OUTPUT_COLUMNS}


def _append_output_row(
    columns: dict[str, list[str | bool | float]],
    record_id: str,
    truth: dict[str, str],
    profile: RunQualityProfile,
    rng: random.Random,
) -> None:
    """Append one predicted output row derived from a record's truth."""
    predicted = {
        "issue_category": _predict(
            truth["issue_category"], ISSUE_CATEGORIES, profile, rng, abstains=True
        ),
        "product_area": _predict(
            truth["product_area"], PRODUCT_AREAS, profile, rng, abstains=True
        ),
        "urgency": _predict(truth["urgency"], URGENCIES, profile, rng, abstains=False),
        "routing_team": _predict(
            truth["routing_team"], ROUTING_TEAMS, profile, rng, abstains=False
        ),
        "should_escalate": _predict(
            truth["should_escalate"], ("true", "false"), profile, rng, abstains=False
        ),
    }
    all_correct = all(predicted[name] == truth[name] for name in predicted)
    confidence_floor = 0.75 if all_correct else 0.5
    columns["record_id"].append(record_id)
    columns["predicted_issue_category"].append(predicted["issue_category"])
    columns["predicted_product_area"].append(predicted["product_area"])
    columns["predicted_urgency"].append(predicted["urgency"])
    columns["predicted_routing_team"].append(predicted["routing_team"])
    columns["predicted_should_escalate"].append(predicted["should_escalate"] == "true")
    columns["model_confidence"].append(round(rng.uniform(confidence_floor, 0.99), 2))
    columns["abstained"].append(rng.random() < profile.row_abstention_rate)


def _predict(
    truth: str,
    allowed_values: tuple[str, ...],
    profile: RunQualityProfile,
    rng: random.Random,
    *,
    abstains: bool,
) -> str:
    """Draw one predicted value from truth given a run quality profile."""
    draw = rng.random()
    if draw < profile.correct_rate:
        return truth
    if abstains and draw < profile.correct_rate + profile.attribute_abstention_rate:
        return ABSTENTION_VALUE
    wrong_values = [value for value in allowed_values if value != truth]
    return rng.choice(wrong_values)


def _write_golden_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write golden rows as CSV."""
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=GOLDEN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_output_parquet(
    path: Path, columns: dict[str, list[str | bool | float]]
) -> None:
    """Write output columns as Parquet with native scalar types."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table(columns), path)
