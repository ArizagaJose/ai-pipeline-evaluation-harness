# Calibration

The harness now includes diagnostic confidence bucket summaries for candidate
outputs. These summaries compare model-provided row-level confidence with
observed cell-level adjudication outcomes.

Confidence diagnostics are intentionally report-only. They do not affect
contract validation, regression gates, false-acceptance gates, human-review
routing, or the final run status.

## Buckets

The default confidence column is `model_confidence`. A config may override it
with `confidence_column`, which must be a non-empty string.

Candidate confidence values must be numeric and in the closed range `0` to `1`.
Invalid, blank, missing, or out-of-range values stop the run with a clear
configuration/data error when diagnostics are computed.

The fixed buckets are:

- `0.00-0.50`: `0.0 <= confidence < 0.5`
- `0.50-0.75`: `0.5 <= confidence < 0.75`
- `0.75-0.90`: `0.75 <= confidence < 0.9`
- `0.90-1.00`: `0.9 <= confidence <= 1.0`

## Grain

Adjudication is at `record_id x attribute` grain. Confidence is currently
row-level, so every adjudicated attribute cell for a candidate row contributes
to the bucket for that row's confidence value.

For each bucket, reports include adjudicated cell metrics:

- `total_cells`
- `correct_cells`
- `abstained_cells`
- `false_acceptance_cells`
- `adjudicated_cell_accuracy`
- `cell_level_abstention_rate`
- `false_acceptance_rate`

`false_acceptance_cells` counts cells that were both incorrect and accepted
under the current deterministic admissibility policy. Critical wrong cells that
are routed to review are not counted as false acceptances.

## Interpretation

These diagnostics help reviewers identify patterns such as high-confidence
wrong accepted values, low-confidence correct values, or abstentions
concentrated in specific confidence ranges.

They are not a statistically complete calibration analysis. The MVP uses fixed
buckets and synthetic fixtures, and it does not compare baseline confidence,
estimate uncertainty, or tune thresholds.
