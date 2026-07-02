# Failure Modes

This catalogues the failure modes the harness is built to catch. Each one is
backed by a runnable scenario under [examples/scenarios](../examples/scenarios)
that reproduces it.
This document explains the failure conceptually; the scenario
configs and `reports/scenarios/` are the evidence, not the explanation.

## Invalid category hallucination

A model emits a value that isn't a real category — not a wrong answer, but a
value that was never a defined possibility (a typo'd, merged, or invented
label). This is a schema problem, not a semantic one: no amount of accuracy
scoring can recover from it, because there's no golden value to compare
against a category that shouldn't exist. Contract validation has to catch
this before semantic scoring even starts, or every downstream metric becomes
meaningless for that record.

Demonstrated by: `contract_validation_failure.json`.

## Coverage improvement masking false acceptance

A new prompt or model abstains less often than the one it's replacing. Lower
abstention looks like progress on a coverage dashboard. But abstention exists
because the model is uncertain — forcing it to answer anyway doesn't make the
underlying uncertainty go away, it just hides it. If even one of those newly
forced answers is wrong on a non-critical field, it gets auto-accepted under
the deterministic policy, and "improved coverage" becomes "increased risk of
silently wrong data downstream." Coverage and correctness have to be gated
separately, because a model can win on one while losing on the other.

Demonstrated by: `coverage_improves_false_acceptance_fails.json`.

## Coverage improvement on a critical attribute

Same root cause as above — abstaining less — but the wrong answers land on
attributes marked `critical` in the contract (the fields where being wrong
has real consequences, like urgency or escalation routing). The policy
response is different: critical wrong values are never auto-accepted no
matter how the false-acceptance gate is configured. They're routed to human
review instead. This is why `NEEDS_REVIEW` exists as a status distinct from
`FAILED` — the candidate didn't break any configured threshold, but it isn't
safe to publish without a human looking at the specific cells that are wrong.

Demonstrated by: `coverage_improves_critical_review.json`.

## Global improvement hiding a segment regression

A candidate's overall accuracy goes up, and every attribute-level regression
gate passes — by the numbers that get glanced at first, it's a clear win. But
averaging across all records can hide that one customer segment, region, or
tier got meaningfully worse. If nobody is enterprise customers, regular
customers improving enough can outweigh enterprise customers regressing in a
blended average. A model is not allowed to trade one segment's quality for
another's without that tradeoff being visible and explicitly gated.

Demonstrated by: `global_improves_segment_regresses.json`.

## Known confusable values routed to review without a hard gate

Some wrong answers aren't surprising — they're a specific, anticipated
confusion pattern (e.g., two adjacent categories that are easy for a model to
mix up). The contract can name these patterns explicitly and route them to
review without requiring a brand-new "is this attribute critical" judgment
call for every occurrence. By default this produces `NEEDS_REVIEW`, not a
failure — it's a way to flag a known risk pattern for a human, not to block
the run outright.

Demonstrated by: `severity_override_requires_review.json`.

## Known confusable values exceeding a review budget

The same routing as above, but now a count gate is configured (e.g., "fail if
more than zero high-severity confusions appear"). This is the difference
between *flagging* a known risk pattern and *capping* how much of it a
candidate is allowed to produce before it's blocked outright — useful when a
review queue has limited capacity and a candidate that produces too many
known-risky cells shouldn't ship even if each individual cell would otherwise
just be routed to review.

Demonstrated by: `severity_override_gate_fails.json`.

## Control case: a clean pass

Not a failure mode — the baseline every scenario above should be compared
against. No contract violations, no critical errors, no false acceptance, no
segment regressions, nothing routed to review. Every gate passes and the run
is `PASSED`. Useful for confirming that a fixture change is what triggers a
given failure mode, rather than something already broken in the baseline
setup.

Demonstrated by: `passes_all_gates.json`.
