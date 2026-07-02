# Quality Model

This project separates schema validity from semantic correctness.

A candidate output can pass the output contract and still be wrong. Contract
validation answers whether the output has an admissible shape. Adjudicated
cell-level admissibility metrics answer whether candidate values are publishable,
must be reviewed, or represent false acceptance risk. Baseline-vs-candidate
attribute metrics provide regression context; they are not the primary
admissibility decision.

## Current Metrics

The current metric implementation compares golden rows with one output run at a
time. Rows must share the same `record_id` grain with no missing or duplicate
IDs.

For each configured attribute mapping, the harness computes regression-context
metrics:

- `total`: number of records evaluated
- `correct`: records where expected and predicted values match exactly
- `incorrect`: records where expected and predicted values differ
- `accuracy`: `correct / total`
- `abstained`: records where the output row has `abstained == "true"`
- `candidate_row_level_abstention_rate`: `abstained / total` in public
  candidate run-summary JSON
- `baseline_row_level_abstention_rate`: `abstained / total` in public
  baseline-vs-candidate delta JSON

These abstention rates are row-level legacy abstention, not cell-level
admissibility abstention. A later regression-gate stage can decide how much
row-level candidate abstention is acceptable for a candidate run.

When `segment_columns` and `paths.source` are configured, the harness also
computes the same totals, accuracy, and abstention rates for each configured
`segment_column x segment_value x attribute`. Source, golden, and output rows
must all share the same `record_id` set with no missing or duplicate IDs.

Record-level adjudication uses one row per `record_id x attribute`. Each row
separates:

- `outcome`: one of `correct`, `incorrect`, `abstained`, `invalid`, or
  `missing`
- `accepted`: whether the value would be published under the current policy
- `requires_review`: whether the value should go to human review
- `review_severity`: optional configured severity for exact confusion overrides
- `reason`: a short deterministic explanation

The adjudicated cell-level admissibility rates are intentionally minimal:

- `adjudicated_cell_accuracy`: `correct / total`
- `cell_level_abstention_rate`: `abstained / total`
- `invalid_rate`: `invalid / total`
- `false_acceptance_rate`: `incorrect accepted cells / total`
- `human_review_rate`: `requires_review cells / total`
- `critical_wrong_rate`: `incorrect critical cells / total critical cells`

`false_acceptance_rate` answers how often a wrong value was auto-accepted. A
separate, complementary breakdown answers what the review queue itself is made
of: cells with `requires_review=true` are either review-routed incorrect
values, abstentions, invalid values, or missing values, and these four
categories always sum to the full review queue. The harness reports this as
review queue composition:

- `review_incorrect_rate`: `review-routed incorrect cells / requires_review cells`
- `review_abstained_rate`: `abstained cells / requires_review cells`
- `review_invalid_rate`: `invalid cells / requires_review cells`
- `review_missing_rate`: `missing cells / requires_review cells`

This distinguishes a review queue that is mostly genuine wrong answers (worth a
reviewer's time) from one that is mostly cautious abstentions or contract
noise (lower urgency, different remediation).

The public JSON artifacts use `cell_level_abstention_rate` for adjudicated
cell-level admissibility metrics. Row-level regression-context abstention uses
explicit `candidate_row_level_abstention_rate` and
`baseline_row_level_abstention_rate` names so it is not confused with
cell-level review routing.

The harness also summarizes wrong critical predictions as compact confusion
counts grouped by `attribute x expected_value x candidate_value`. These counts
are diagnostic context for audit and human review; they do not currently act as
regression gates or weighted scores.

Contracts can opt into severity-aware review routing with exact
`expected_value x candidate_value` overrides on a predicted column. Matching
valid wrong values require review and are excluded from false acceptance counts.
The harness reports matched override counts grouped by
`attribute x expected_value x candidate_value x severity x reason`. These counts
are diagnostic only; status still changes through the existing
`requires_review` semantics.

When adjudication is available and the candidate contract passes, the harness
also computes diagnostic confidence bucket summaries for the candidate output.
The default confidence column is `model_confidence`, configurable with
`confidence_column`. Confidence values are grouped into fixed buckets and
reported with cell-level accuracy, abstention rate, and false acceptance rate.
These diagnostics are report-only and never determine acceptance by themselves.
