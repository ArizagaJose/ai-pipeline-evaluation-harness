# Architecture

The harness evaluates already-produced AI-generated analytical outputs. It does
not generate candidate data and does not call external APIs in the evaluation
path.

## Implemented MVP Flow

1. A JSON evaluation config is loaded from `examples/`.
2. Local CSV or Parquet rows are read for the golden dataset, baseline output,
   and candidate output.
3. Baseline and candidate outputs are validated against a JSON output contract.
4. If either output fails contract validation, semantic metrics and gates are
   skipped and the evaluation fails.
5. If candidate record IDs are usable, candidate cells are adjudicated against
   golden labels to produce the admissibility decision and human-review routing.
6. If both outputs pass the contract, baseline-vs-candidate regression-context
   metrics are computed against the golden dataset.
7. Regression gates fail when `baseline_accuracy - candidate_accuracy` exceeds
   the configured `max_accuracy_drop`.
8. The candidate abstention-rate gate fails when the row-level candidate
   abstention rate exceeds the configured maximum.
9. The run status is `PASSED`, `NEEDS_REVIEW`, or `FAILED`. Candidates that
   pass contracts and gates but have review-required adjudicated cells are
   `NEEDS_REVIEW`, not `PASSED`.
10. A Markdown report is written with the candidate admissibility decision first,
    followed by contract results, regression context, gate results, and a concise
    human-review recommendation.
11. The CLI returns exit code `0` only for `PASSED`, `1` for `NEEDS_REVIEW` or
    `FAILED`, and `2` for execution or config errors.

## Module Boundaries

- `config.py`: JSON evaluation config parsing and validation.
- `io.py`: local CSV loading plus PyArrow-backed Parquet loading.
- `contracts.py`: JSON output contract parsing and deterministic row validation.
- `metrics.py`: golden-vs-output attribute metrics. Scoring is sample-level:
  every golden record ID must be covered by the output rows, and output rows
  without a golden label are ignored.
- `gates.py`: baseline-vs-candidate regression, row-level abstention, and
  adjudicated false-acceptance gate checks.
- `evaluation.py`: orchestration across validation, metrics, and gates.
- `reporting.py`: deterministic Markdown and run-summary rendering.
- `synthetic.py`: deterministic population-scale synthetic fixture generation.
- `cli.py`: standard-library `argparse` command interface.

The MVP intentionally avoids pandas, Pydantic, Typer, cloud services, model
calls, and dashboarding. PyArrow is used only for local Parquet input support.
