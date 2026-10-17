# Convenience targets. On Windows without `make`, run the commands shown in README.md.
PYTHON ?= python

.PHONY: install install-optional lint format test ui api demo bench clean

install:
	$(PYTHON) -m pip install -r requirements.txt

install-optional:
	$(PYTHON) -m pip install -r requirements-optional.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check . --fix
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest

ui:
	$(PYTHON) -m streamlit run app/streamlit_app.py

api:
	$(PYTHON) -m uvicorn app.api.main:app --reload --port 8000

demo:
	$(PYTHON) scripts/run_demo.py

bench:
	$(PYTHON) scripts/evaluate_benchmarks.py

clean:
	rm -rf demo_output .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
