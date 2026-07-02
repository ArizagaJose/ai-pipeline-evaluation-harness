# Human Review Boundaries

The harness adjudicates candidate outputs at `record_id x attribute` grain before
promotion decisions. Each configured cell is classified as one of:

- `correct`
- `incorrect`
- `abstained`
- `invalid`
- `missing`

Each adjudication row also carries explicit routing and acceptance flags:

- `accepted`: whether the candidate value is accepted under the current policy.
- `requires_review`: whether the cell must be sent to human review.
- `critical`: whether the predicted column is marked critical in the contract.

Correct valid attempted values are accepted. Valid wrong values for non-critical
columns are accepted by the MVP policy and counted as false acceptance risk.
Valid wrong values for non-critical columns can also be routed to review by an
optional per-column `severity_overrides` entry in the output contract. Valid
wrong values for critical columns are not accepted; they are routed to human
review and counted as critical wrong predictions. Cells also require review when
the candidate abstains, emits an invalid value, or omits a configured value.

False acceptance has one meaning: an adjudicated cell has
`outcome=incorrect` and `accepted=true`. Values routed to human review are not
false acceptances.

Severity overrides are exact expected-value/candidate-value confusion policies.
They are diagnostic review-routing rules, not weighted scores. Each override
must provide non-empty `expected_value`, `candidate_value`, `severity`, and
`reason` fields. Supported severities are `medium`, `high`, and `critical`. The
candidate value must be an allowed value when `allowed_values` is configured,
and it cannot be a configured abstention value because abstentions already
require review.

By default, severity overrides can produce `NEEDS_REVIEW` but do not fail a run.
An evaluation config can opt into count-based `severity_review_gates` such as
`{"severity": "high", "max_count": 0}`. These gates count only cells matched by
contract-defined severity overrides for that severity.

The core adjudicated cell-level admissibility rates are:

- `adjudicated_cell_accuracy`: `correct / total`
- `cell_level_abstention_rate`: `abstained / total`
- `invalid_rate`: `invalid / total`
- `false_acceptance_rate`: `incorrect accepted cells / total`
- `human_review_rate`: `requires_review cells / total`
- `critical_wrong_rate`: `incorrect critical cells / total critical cells`

The harness also reports review queue composition, which breaks
`requires_review_cells` down by why each cell needs review:

- `review_incorrect_rate`: `review-routed incorrect cells / requires_review cells`
- `review_abstained_rate`: `abstained cells / requires_review cells`
- `review_invalid_rate`: `invalid cells / requires_review cells`
- `review_missing_rate`: `missing cells / requires_review cells`

These four rates always sum to 1.0 when `requires_review_cells > 0`. A queue
dominated by `review_incorrect_rate` is worth prioritizing; one dominated by
`review_abstained_rate` may reflect a model being appropriately cautious
rather than wrong. The run summary documents this under
`metric_groups.review_queue_composition`.

The JSON artifacts use `cell_level_abstention_rate` for adjudicated
admissibility metrics and row-level abstention names such as
`candidate_row_level_abstention_rate` for regression context. The run summary
also includes a `metric_groups.review_routing` block so human-review routing
semantics are explicit and separate from deterministic gate failures.

Per-column `abstention_values` are treated as cell-level abstentions. The legacy
row-level `abstained=true` flag is still supported and maps every configured
attribute on that row to an `abstained` adjudication.

The Markdown report leads with the candidate admissibility decision and includes
admissibility and human-review rates before regression context. When
configured, `paths.adjudication` writes the same adjudications and metrics as a
deterministic JSON artifact for downstream review queues or regression checks.
When configured, `paths.summary` writes a compact run-level JSON artifact with
overall status, contract status, key metrics, metric deltas, metric-family and
review-routing metadata, failed gates, and artifact paths for automation.

When severity overrides match adjudicated cells, the Markdown report,
adjudication JSON, and run summary JSON include grouped severity review counts
by `attribute x expected_value x candidate_value x severity x reason`.

Human review is part of the top-level status model. A run is `NEEDS_REVIEW`
when contracts and gates pass but one or more adjudicated cells require human
review. `NEEDS_REVIEW` means the candidate is not publishable without human
review; it is not necessarily `FAILED`. A run is `PASSED` only when contracts
and gates pass and no adjudicated cells require review.
