"""Drive the Streamlit UI headlessly with Streamlit's AppTest harness."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[2] / "app" / "streamlit_app.py")


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def test_main_workflow():
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    click(at, "Index / re-index repository")
    assert not at.exception and any("Indexed" in s.value for s in at.success)
    click(at, "Build Context")
    assert not at.exception and not at.error
    assert any("Built context" in s.value for s in at.success)
    labels = [m.label for m in at.metric]
    assert "Usable budget" in labels and "Utilization" in labels
    assert at.get("download_button")
    click(at, "Run comparison")
    assert not at.exception and not at.error


def test_invalid_path_shows_error():
    at = AppTest.from_file(APP, default_timeout=60).run()
    # The filesystem root ("C:\\" or "/") is outside the allowed roots on every OS.
    at.text_input[0].set_value(Path(APP).anchor).run()
    click(at, "Index / re-index repository")
    assert not at.exception
    assert any("allowed roots" in e.value for e in at.error)
