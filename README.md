# AI Pipeline Evaluation Harness

![CI](https://github.com/ArizagaJose/ai-pipeline-evaluation-harness/actions/workflows/ci.yml/badge.svg)

A local-first deterministic harness for deciding whether AI-generated analytical
data is safe to promote into downstream data workflows.

The problem it addresses: a candidate dataset can pass every schema and
allowed-value check, and even improve on the current baseline's overall
accuracy, and still be unsafe to promote. The working principle is that AI
models may generate candidate data, deterministic systems decide whether that
data is admissible, and humans handle the judgment cases where automation is
unsafe.

This is not an LLM/prompt/RAG evaluator, an extraction pipeline, a dashboard, or
a model server. Tools such as Promptfoo and DeepEval evaluate whether an LLM
application behaves well. This harness answers a narrower operational question:
whether an already-produced AI-generated dataset is admissible as governed
downstream data.

## What This Catches

- Structural failures, before semantic scoring. Contract validation runs first;
  if it fails, scoring stops instead of reporting accuracy on a structurally
  broken output.
- Coverage gains that raise false acceptance. A candidate that abstains less
  looks more complete while shipping more wrong values as if they were good.
- Global improvements that hide segment regressions.
- Wrong values on critical fields. These are routed to human review rather than
  auto-accepted, even when every configured gate passes.

## Current Capabilities

**Input & contracts**

- JSON evaluation configs and JSON output contracts
- local CSV and PyArrow-backed Parquet loading of already-produced fixtures
- required-column, nullability, type, allowed-value, duplicate-ID, and missing-ID
  validation
- deterministic population-scale fixture generation (`generate-scale-fixture`)

**Scoring**

- golden-vs-output attribute metrics
- baseline-vs-candidate accuracy deltas
- cell-level adjudication at `record_id + evaluated attribute` grain

**Safety gates**

- per-attribute regression gates
- row-level candidate abstention-rate checks
- false-acceptance gates
- severity-based human-review routing and optional count gates
- segment-level regression scenarios

**Promotion artifacts**

- deterministic Markdown report, adjudication JSON, and run-summary JSON
- review queue composition (incorrect vs. abstained vs. invalid vs. missing share
  of cells routed to human review)

**CI / automation**

- exit codes usable as local CI promotion gates (see [Exit Codes](#exit-codes))

The example domain is synthetic customer support ticket triage. It is a fixture
only; the harness is about evaluating AI-generated analytical fields, not support
automation.

## Decision Model

Every evaluation returns one top-level candidate status:

- `PASSED`: contracts pass, deterministic gates pass, and no adjudicated cells
  require human review.
- `NEEDS_REVIEW`: contracts and gates pass, but one or more adjudicated cells are
  routed to human review before promotion.
- `FAILED`: contract validation or a configured deterministic gate fails.

`NEEDS_REVIEW` is not a generic gate failure. It is a routing outcome: the
candidate is not auto-promotable, but the deterministic thresholds did not fail.

The adjudication unit is `record_id + evaluated attribute`, not a whole row.
Each adjudicated cell compares one candidate value with its golden value and
carries an `outcome` (`correct`, `incorrect`, `abstained`, `invalid`, or
`missing`), whether it is `accepted` automatically, whether it `requires_review`,
and a deterministic `reason`. False acceptance has one specific meaning here: a
cell that is incorrect and accepted automatically. Incorrect values routed to
human review are not false acceptances.

## Quick Start

Install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
```

Run the canonical evaluation:

```bash
ai-data-harness evaluate --config examples/support_ticket_evaluation.json
```

From an uninstalled source checkout:

```bash
PYTHONPATH=src python -m ai_data_harness.cli evaluate \
  --config examples/support_ticket_evaluation.json
```

The canonical example writes:

- [reports/support_ticket_evaluation.md](reports/support_ticket_evaluation.md)
- `reports/support_ticket_adjudication.json`
- `reports/support_ticket_run_summary.json`

It exits `1` with status `NEEDS_REVIEW` on purpose (see the sample below). For a
clean pass:

```bash
PYTHONPATH=src python -m ai_data_harness.cli evaluate \
  --config examples/scenarios/passes_all_gates.json
```

That scenario exits `0` with status `PASSED`.

## Sample Report Output

In the canonical run, contract validation passes for baseline and candidate,
every configured gate passes, and the candidate improves accuracy against the
baseline (`urgency` +0.250, `routing_team` +0.167, `false_acceptance_rate`
0.000). The run still ends as `NEEDS_REVIEW` because two critical cells are
wrong. From the generated report's Critical Confusion Counts:

```markdown
Overall status: NEEDS_REVIEW

| Attribute       | Expected | Candidate | Count |
| --------------- | -------- | --------- | ----- |
| should_escalate | true     | false     | 1     |
| urgency         | critical | medium    | 1     |
```

A ticket that should escalate was marked not to, and a critical ticket was
downgraded to medium. Both cells are routed to human review instead of being
auto-accepted, so the candidate is not auto-promotable even though no gate
failed. The full report is at
[reports/support_ticket_evaluation.md](reports/support_ticket_evaluation.md).

## Exit Codes

The CLI is meant to be used as a promotion gate in CI:

| Exit code | Meaning                                                      |
| --------: | ----------------------------------------------------------- |
|       `0` | `PASSED` — safe to auto-promote                             |
|       `1` | do not auto-promote — the run is `FAILED` or `NEEDS_REVIEW` |
|       `2` | execution or configuration error (bad config, missing file, malformed input) |

Exit code `1` covers both a hard gate failure (`FAILED`) and a routing outcome
(`NEEDS_REVIEW`); both mean the candidate is not auto-promotable. To tell them
apart programmatically, read the `status` field in the run-summary JSON, which
distinguishes `PASSED`, `NEEDS_REVIEW`, and `FAILED`.

## Demonstrated Failure Modes

Scenario configs under [examples/scenarios](examples/scenarios) exercise the
cases from [What This Catches](#what-this-catches) plus severity-policy
variants:

- contract validation failure
- candidate improves coverage but increases false acceptance
- candidate improves globally while a segment regresses
- severity-based human-review routing
- severity-based human-review count gate failure
- critical-review routing even when configured gates pass

The scenarios are small and synthetic so the evaluation behavior is easy to
inspect in diffs and reports.

## Scale Fixture

The committed fixtures are intentionally tiny. To exercise the harness at a
realistic population size, generate a synthetic million-row run:

```bash
make scale-demo
```

This generates a 1,000,000-row baseline and candidate (Parquet) plus a
2,000-row golden sample (CSV) under `data/generated/scale/`, then evaluates
the candidate. Generation and evaluation are deterministic for a fixed seed.

The run demonstrates the sample-vs-population split: contract validation and
the row-level abstention gate cover all million rows, while semantic scoring
and adjudication cover the 2,000 golden-labeled records. Every golden record
ID must be present in the output files; output rows without a golden label
are contract-validated but not scored. The demo exits `1` with
`NEEDS_REVIEW`, like the canonical example: gates pass and accuracy improves
on every attribute, but wrong critical cells in the golden sample are routed
to review. The golden-coverage requirement reflects how golden data is used:
evaluating a candidate means running it over the golden records and scoring
those fresh predictions against the stored labels, so the ID overlap is
deliberate, not a temporal coincidence. Row counts and sample size are
configurable:

```bash
PYTHONPATH=src python -m ai_data_harness.cli generate-scale-fixture \
  --output-dir data/generated/scale --rows 1000000 --golden-rows 2000 --seed 7
```

See [docs/golden_provenance.md](docs/golden_provenance.md) for why golden
samples are small in practice and what sample size does to gate reliability.

## How The Evaluation Works

1. Load a JSON evaluation config.
2. Load local golden, baseline, candidate, and optional source records.
3. Validate baseline and candidate outputs against an explicit output contract.
4. Stop semantic scoring when contract validation fails.
5. Compare candidate and baseline attributes against the golden dataset.
6. Compute regression deltas and gate results.
7. Adjudicate candidate cells for admissibility and review routing.
8. Render Markdown and JSON artifacts.
9. Return the exit code described in [Exit Codes](#exit-codes).

## Repository Map

- [src/ai_data_harness](src/ai_data_harness): core evaluation package
- [contracts](contracts): output contracts and severity policy contracts
- [examples](examples): runnable evaluation configs and scenario configs
- [data](data): synthetic golden, baseline, candidate, and source fixtures
- [reports](reports): generated Markdown and JSON evaluation artifacts
- [docs](docs): architecture, quality model, gates, calibration, review
  boundaries, failure modes, and non-goals
- [tests](tests): unit and integration coverage for the deterministic harness

## Local Checks

```bash
make test
make lint
make validate-json
```

Or run the full configured check target:

```bash
make check
```

## Further Reading

- [docs/architecture.md](docs/architecture.md): implemented MVP flow and module
  boundaries
- [docs/quality_model.md](docs/quality_model.md): validity vs semantic quality
- [docs/regression_gates.md](docs/regression_gates.md): why improving candidates
  can still fail
- [docs/human_review_boundaries.md](docs/human_review_boundaries.md): when
  deterministic automation should stop
- [docs/golden_provenance.md](docs/golden_provenance.md): where golden data
  comes from and how sample size affects gate reliability
- [docs/what_this_is_not.md](docs/what_this_is_not.md): positioning and non-goals

## License

This project is open source under the MIT License. See [LICENSE](LICENSE) for
the full terms.
