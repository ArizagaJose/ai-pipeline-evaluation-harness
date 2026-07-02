.PHONY: install-dev install-hooks pre-commit validate-json test lint format check clean scale-demo

install-dev:
	python -m pip install -e ".[dev]"

install-hooks:
	pre-commit install

pre-commit:
	pre-commit run --all-files

validate-json:
	pre-commit run check-json --all-files

test:
	python -m pytest

lint:
	python -m ruff check .

format:
	python -m ruff format .

check: lint validate-json test

# The evaluate step is expected to exit 1 (NEEDS_REVIEW); only exit 2
# (execution or configuration error) fails the target.
scale-demo:
	PYTHONPATH=src python -m ai_data_harness.cli generate-scale-fixture \
		--output-dir data/generated/scale
	PYTHONPATH=src python -m ai_data_harness.cli evaluate \
		--config examples/scale_fixture_evaluation.json; \
		status=$$?; if [ $$status -eq 2 ]; then exit $$status; fi

clean:
	rm -rf .pytest_cache .ruff_cache build dist htmlcov
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
