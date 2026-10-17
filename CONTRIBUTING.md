# Contributing to ACWM

Thanks for helping improve the Automatic Context Window Manager.

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

## Before opening a pull request

```bash
ruff check . && ruff format --check .
pytest
python scripts/run_demo.py
```

All three must succeed. CI (`.github/workflows/tests.yml`) runs the same steps.

## Guidelines

- **Shared service layer.** Business logic belongs in `app/services/acwm_service.py` and the
  modules it calls. FastAPI routes and the Streamlit UI must stay thin.
- **Determinism.** Rankings and selections must be identical for identical inputs. Always
  break ties explicitly (for example by path).
- **Honest outputs.** Never report a metric, a provider status or a semantic score that was
  not actually computed. Use `None`/"N/A" with an explanation instead.
- **Security.** Never execute repository code, follow symlinks out of the root, or log file
  contents or credentials. Add a test for every new exclusion rule.
- **Tests.** New behaviour needs meaningful tests that use temporary directories. Do not
  write tests that only assert `True`.
- **Benchmarks.** If you change ranking or optimizer heuristics, run
  `python scripts/evaluate_benchmarks.py` and update `docs/evaluation.md` with the measured
  numbers. Do not edit ground-truth labels to improve scores.
