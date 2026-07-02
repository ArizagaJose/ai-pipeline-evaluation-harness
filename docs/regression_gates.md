# Regression Gates

Regression gates are deterministic acceptance rules applied after both baseline
and candidate outputs pass contract validation.

## Implemented Gates

The MVP supports five gate types through the JSON evaluation config. Each gate
reports the metric family it evaluates:

- Per-attribute `max_accuracy_drop`: fails when
  `baseline_accuracy - candidate_accuracy > max_accuracy_drop` in
  baseline-vs-candidate attribute regression metrics.
- Per-segment `segment_regression_gates`: fails when the same accuracy drop
  threshold is exceeded inside baseline-vs-candidate segment regression metrics.
- `max_candidate_abstention_rate`: fails when the row-level candidate abstention
  rate exceeds the configured threshold.
- `max_false_acceptance_rate`: fails when valid wrong candidate cells accepted
  without human review exceed the configured share of all evaluated cells in
  adjudicated admissibility `false_acceptance_rate`.
- `severity_review_gates`: fails when cells routed to human review by
  contract-defined severity overrides exceed a configured per-severity count.

The support-ticket example config uses zero tolerated accuracy drop for each
mapped attribute, allows up to `0.1` candidate abstention rate, allows up to
`0.1` false acceptance rate. The current MVP policy routes valid wrong critical
values to human review instead of accepting them, so those cells increase
`critical_wrong_rate` and `human_review_rate` but not
`false_acceptance_rate`.

## Evaluation Semantics

Contract validation is an admissibility prerequisite for baseline-vs-candidate
accuracy metrics, segment metrics, and accuracy-drop gates. Candidate-vs-golden
adjudication still runs when candidate record IDs are usable, so invalid,
missing, abstained, and wrong values can be counted deterministically.

Segment regression checks are opt-in. Configure:

- `paths.source`: CSV with one row per `record_id` and segment metadata.
- `segment_columns`: source columns to evaluate, such as `customer_tier`,
  `region`, or `source_channel`.
- `segment_regression_gates`: objects with `attribute`, `segment_column`,
  `segment_value`, `max_accuracy_drop`, and `min_segment_size`.

For segment-enabled runs, source, golden, baseline output, and candidate output
must contain the same `record_id` set. Segment gates whose observed segment
size is below `min_segment_size` are reported as skipped and do not fail the
run.

Severity review gates are opt-in. Configure:

```json
"severity_review_gates": [
  { "severity": "critical", "max_count": 0 },
  { "severity": "high", "max_count": 1 }
]
```

Supported severities are `medium`, `high`, and `critical`. Counts are based
only on contract-configured severity override matches, not all wrong critical
cells. Omitted `severity_review_gates` preserves the default behavior: severity
overrides route matching cells to review and can produce `NEEDS_REVIEW`, but
they do not fail gates.

A candidate can improve most attributes and still fail if one gated attribute
regresses beyond its threshold. A candidate can also fail solely because it
abstains too often, even when predictions are otherwise valid.
A candidate can also pass global gates and fail because a configured segment
regresses beyond its threshold. A candidate can also fail when configured
severity-routed human review counts exceed their thresholds.

Passing all gates does not automatically produce a `PASSED` run. If the
candidate has one or more adjudicated cells that require human review, the run
status is `NEEDS_REVIEW`. This review status is driven by
`requires_review_cells`; it is separate from gate failure. `NEEDS_REVIEW` is a
safe routing outcome: the candidate is not publishable without human review, but
it is not a failed regression or threshold gate.
