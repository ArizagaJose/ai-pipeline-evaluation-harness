# Evaluation Report

Overall status: **NEEDS_REVIEW**

## Candidate Admissibility Decision

Final status: **NEEDS_REVIEW**

NEEDS_REVIEW is a safe routing outcome: configured gates passed, but one or more requires_review cells must be reviewed before promotion.

| Adjudicated cell metric | Value |
| --- | ---: |
| adjudicated_cell_accuracy | 0.967 |
| cell_level_abstention_rate | 0.000 |
| cell_level_invalid_rate | 0.000 |
| false_acceptance_rate | 0.000 |
| human_review_rate | 0.033 |
| critical_wrong_rate | 0.056 |
| total_cells | 60 |
| critical_cells | 36 |
| correct_cells | 58 |
| incorrect_cells | 2 |
| abstained_cells | 0 |
| invalid_cells | 0 |
| missing_cells | 0 |
| accepted_cells | 58 |
| requires_review_cells | 2 |
| incorrect_accepted_cells | 0 |
| critical_wrong_cells | 2 |

### Review Queue Composition

Breakdown of requires_review_cells by outcome: how much of the review queue is wrong values worth a reviewer's time versus abstentions, invalid values, or missing data.

| Review composition metric | Value |
| --- | ---: |
| review_incorrect_cells | 2 |
| review_incorrect_rate | 1.000 |
| review_abstained_rate | 0.000 |
| review_invalid_rate | 0.000 |
| review_missing_rate | 0.000 |

### Outcome Counts

| Outcome | Count |
| --- | ---: |
| correct | 58 |
| incorrect | 2 |
| abstained | 0 |
| invalid | 0 |
| missing | 0 |

### Critical Confusion Counts

| Attribute | Expected | Candidate | Count |
| --- | --- | --- | ---: |
| should_escalate | true | false | 1 |
| urgency | critical | medium | 1 |

### Severity Review Counts

Severity review counts: none

## Contract Validation

### Baseline

Status: **PASSED**
Issue count: 0

### Candidate

Status: **PASSED**
Issue count: 0

## Baseline-vs-Candidate Regression Context

These are comparison metrics for regression checks, not cell-level routing or admissibility metrics.

### Attribute Regression Context

| Attribute | Total | baseline_attribute_regression_accuracy | candidate_attribute_regression_accuracy | attribute_regression_accuracy_delta | baseline_row_level_abstention_rate | candidate_row_level_abstention_rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| issue_category | 12 | 0.917 | 1.000 | +0.083 | 0.000 | 0.000 |
| product_area | 12 | 0.917 | 1.000 | +0.083 | 0.000 | 0.000 |
| urgency | 12 | 0.667 | 0.917 | +0.250 | 0.000 | 0.000 |
| routing_team | 12 | 0.833 | 1.000 | +0.167 | 0.000 | 0.000 |
| should_escalate | 12 | 0.917 | 0.917 | +0.000 | 0.000 | 0.000 |

### Segment Regression Context

Segment regression was not configured for this run.

## Confidence Diagnostics

| Bucket | Total cells | adjudicated_cell_accuracy | cell_level_abstention_rate | false_acceptance_rate | Correct | Abstained | False acceptance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00-0.50 | 0 | 0.000 | 0.000 | 0.000 | 0 | 0 | 0 |
| 0.50-0.75 | 15 | 0.867 | 0.000 | 0.000 | 13 | 0 | 0 |
| 0.75-0.90 | 30 | 1.000 | 0.000 | 0.000 | 30 | 0 | 0 |
| 0.90-1.00 | 15 | 1.000 | 0.000 | 0.000 | 15 | 0 | 0 |

## Regression Gates

Human review routing is reported under review_routing metadata and requires_review_cells; it can produce NEEDS_REVIEW separately from gate failure.

| Gate | Metric family | Subject | Status | Threshold | Observed | Details |
| --- | --- | --- | --- | ---: | ---: | --- |
| max_accuracy_drop | baseline-vs-candidate attribute regression metrics | issue_category | PASSED | 0.000 | -0.083 | issue_category baseline-vs-candidate attribute regression accuracy drop -0.083 is within threshold 0.000. |
| max_accuracy_drop | baseline-vs-candidate attribute regression metrics | product_area | PASSED | 0.000 | -0.083 | product_area baseline-vs-candidate attribute regression accuracy drop -0.083 is within threshold 0.000. |
| max_accuracy_drop | baseline-vs-candidate attribute regression metrics | urgency | PASSED | 0.000 | -0.250 | urgency baseline-vs-candidate attribute regression accuracy drop -0.250 is within threshold 0.000. |
| max_accuracy_drop | baseline-vs-candidate attribute regression metrics | routing_team | PASSED | 0.000 | -0.167 | routing_team baseline-vs-candidate attribute regression accuracy drop -0.167 is within threshold 0.000. |
| max_accuracy_drop | baseline-vs-candidate attribute regression metrics | should_escalate | PASSED | 0.000 | 0.000 | should_escalate baseline-vs-candidate attribute regression accuracy drop 0.000 is within threshold 0.000. |
| max_candidate_abstention_rate | row-level candidate abstention | candidate | PASSED | 0.100 | n/a | row-level candidate abstention rate 0.000 is within threshold 0.100. |
| max_false_acceptance_rate | adjudicated admissibility false_acceptance_rate | candidate | PASSED | 0.100 | 0.000 | adjudicated admissibility false_acceptance_rate 0.000 is within threshold 0.100. |

## Human Review Recommendation

Send the candidate to human review before promotion. One or more adjudicated cells require review.
