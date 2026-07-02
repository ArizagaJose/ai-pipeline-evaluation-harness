# What This Is Not

This project is not another general LLM evaluation
framework. Tools such as Promptfoo and DeepEval already cover prompt, model,
RAG, chatbot, agent, red-team, and LLM-as-judge evaluation workflows.

The stronger positioning is narrower:

> A local-first data engineering harness for deciding whether AI-generated
> structured outputs are safe to admit into downstream analytical pipelines.

Promptfoo and DeepEval help decide whether an LLM application behaves well.
This harness helps decide whether an AI-generated analytical dataset is
admissible as governed downstream data.

## What "Admissible" Means Here

This harness scores a candidate run (a model, prompt, or pipeline version)
against a held-out golden dataset before that candidate is promoted to become
the accepted baseline that downstream consumers receive. It does not score
individual live records that lack a golden label — there is no such label at
inference time.

That is a real constraint, not a loophole: the question this harness answers
is "is this candidate's output good enough, on a representative golden set, to
replace the dataset currently trusted downstream?" not "is this specific
unlabeled record correct?" Those are different questions. The harness is
deliberately narrow about which one it answers.

This is not a generic candidate-model evaluation framework.
It is a focused data engineering application of that idea:
gating the promotion of an AI-generated dataset using the same kind of
golden-set, regression-gate, and human-review discipline a data engineering
team already applies to schema changes and pipeline releases.
