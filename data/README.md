# Synthetic Fixture Data

This directory contains small, synthetic support-ticket datasets for local
evaluation examples.

The checked-in fixtures use CSV so they can be reviewed in normal text diffs.
The evaluation config also accepts Parquet paths for golden labels, source
records, baseline outputs, candidate outputs, and scenario datasets. Keep CSV as
the canonical format for these small synthetic examples, and use Parquet when a
larger analytical workflow benefits from a columnar local file format.

## Grain

Each file has one row per `record_id`.

## Files

- `synthetic/support_ticket_source_records.csv`: synthetic ticket text and
  segment columns.
- `golden/support_ticket_golden.csv`: trusted labels for evaluated attributes.
- `runs/support_ticket_baseline_outputs.csv`: current accepted baseline outputs.
- `runs/support_ticket_candidate_outputs.csv`: candidate outputs to compare
  against the baseline.

## Scenario Fixtures

Named scenarios under `scenarios/support_ticket/` reuse the same source records,
golden labels, and output contract while varying baseline and candidate run
outputs:

- `passes_all_gates`: candidate labels exactly match golden labels and the run
  is expected to pass.
- `contract_validation_failure`: candidate contains an unsupported
  `predicted_issue_category` value and fails contract validation.
- `coverage_improves_false_acceptance_fails`: candidate removes an abstention
  but preserves a wrong non-critical value, failing the false-acceptance gate.
- `global_improves_segment_regresses`: candidate improves global urgency
  accuracy while regressing urgency for `customer_tier=enterprise`.
- `coverage_improves_critical_review`: candidate removes an abstention but
  preserves wrong critical values, routing the run to human review.

## Domain

The fixtures use customer support ticket triage. This keeps the project in a
safe analytical-data domain and avoids healthcare, legal, contract, OCR, PDF, or
document-extraction examples.
