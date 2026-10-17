# Test fixtures

Static inputs for tests. Most tests build isolated repositories in `tmp_path`
(see `tests/conftest.py`). Files here use a `.txt` suffix so that linters and
pytest never import them.

- `malformed_module.py.txt`: Python source with a syntax error.
