# Where Golden Data Comes From

The harness scores candidate outputs against a golden dataset. That raises an
operational question this document addresses directly: who produces golden
data, how much of it exists, and what its size does to the reliability of the
gates.

## Golden Data Is a Small, Expensive Sample

Golden labels are human judgments. Someone with domain knowledge reads the
source record and writes down the correct value for each evaluated attribute.
That work is slow and costly, so in practice a golden dataset is a small
sample of the population the AI system labels.

In the fixture domain used here, the population is every support ticket, and
the golden dataset is the subset a person has triaged by hand. Nothing about
the harness assumes golden covers the population; the design assumes it does
not.

## Versions Are Evaluated, Not Batches

The unit under evaluation is a candidate version of the system that produces
the dataset: a model swap, a prompt edit, a post-processing change, or any
other upstream modification. The harness never inspects the change itself. It
compares what the accepted version and the challenger produce for the same
golden records, and decides whether the challenger may be promoted.

This is why golden coverage is a hard requirement rather than a temporal
accident. A golden dataset is a set of (source record, label) pairs, not
labels alone. Evaluating a candidate means running it over the golden source
records — today — and scoring those fresh predictions against the stored
labels. The overlap between golden and output record IDs is manufactured on
purpose; it is not a claim that production batches contain old records. When
golden record IDs are missing from an output file, the likely causes are a
misconfigured path or a candidate run that silently dropped records, so the
harness fails loudly instead of quietly scoring whatever intersects. To
evaluate against a deliberate slice of a pooled golden dataset, filter the
golden file explicitly so the sample size stays a visible choice.

Two activities fall outside this scope by design:

- Scoring unlabeled records. Producing values for new records is inference;
  no label exists to score against at that moment. Quality work there is
  monitoring — confidence distributions, drift signals, spot-check sampling —
  not golden-set evaluation.
- Evaluating a batch of data as such. The harness gates the promotion of a
  producing-system version. The accepted baseline exists because an earlier
  version was promoted, and a passing candidate becomes the next baseline.

The short framing: this is release gating for a data-producing AI system, not
runtime monitoring of its output.

## Sample-Level and Population-Level Metrics

The harness mixes two kinds of checks, and they have different coverage:

- Population-level: contract validation and the row-level candidate
  abstention gate run over every row of the output files.
- Sample-level: attribute accuracy, regression deltas, segment metrics, and
  cell-level adjudication run only over records that have a golden label.

A sample-level accuracy of 0.94 is an estimate of population accuracy, not a
guarantee about any specific unlabeled record. The false-acceptance rate is
likewise an estimated rate; a wrong-but-accepted value in the unlabeled part
of the population is invisible to the harness by construction. The scale
fixture (`ai-data-harness generate-scale-fixture`) demonstrates this split: a
million-row candidate is contract-validated in full while semantic scoring
covers the golden sample.

## Small Samples Make Gates Unreliable

Gate thresholds behave badly when the golden sample is tiny. With 10 labeled
records, observing 8 correct gives a 95% confidence interval of roughly 44%
to 97% accuracy: one flipped record moves the point estimate by 10 points. A
regression gate such as `max_accuracy_drop: 0.0` compares two such noisy
estimates, so at that size it blocks or passes candidates mostly on sampling
noise.

There is no fixed minimum, but the arithmetic is unforgiving: at 100 labeled
records the standard error of an accuracy estimate near 0.9 is about 3
points; at 2,000 records it is under 1 point. Regression gates with tight
thresholds only start to mean something in the hundreds of labels per
attribute. Until then, treat gate results as weak evidence and lean on
human review instead.

## Growing a Golden Dataset

Teams rarely get a large golden dataset up front. Practical ways it grows:

- Pool labels across evaluation rounds. If the attribute schema is stable,
  the labeled records from every round accumulate into one versioned golden
  dataset instead of being discarded after each run.
- Harvest the review queue. Every cell the harness routes to human review
  receives a human decision. Recording that decision produces a new golden
  label at exactly the grain the harness uses (`record_id + attribute`).
  Review is not just a safety valve; it is the labeling loop.
- Label deliberately, not conveniently. Stratify new labels across segments,
  attribute values, and difficulty, so rare-but-critical cases (for example,
  tickets that should escalate) are represented well beyond their base rate.

## Failure Modes of Golden Data Itself

Golden data is an input with its own quality problems:

- Representativeness. Labels provided on demand are usually not a random
  sample; whoever requested them picked records they cared about. A biased
  sample yields precise estimates of the wrong population.
- Leakage. If candidate models or prompts were tuned against the golden
  records, scores on those records overstate quality. Hold labels out from
  tuning, or split them.
- Label drift. Correct values change as products, teams, and policies
  change. A golden dataset needs versioning and periodic review like any
  other governed dataset.
- Label error. Humans mislabel too. Disagreement between the golden label
  and a consistently confident candidate is occasionally the label's fault;
  a periodic audit of "incorrect" cells catches this.

## What This Means for Promotion Decisions

The candidate status the harness reports is only as trustworthy as the golden
sample behind it. A `PASSED` against 20 convenient labels is a much weaker
claim than a `NEEDS_REVIEW` against 2,000 stratified ones. When acting on
reports, read the per-attribute `total` columns as part of the result, not as
metadata.
