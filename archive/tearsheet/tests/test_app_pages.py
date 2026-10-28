"""Boot-smoke tests: every entry point should render (unauthenticated) with
no exceptions. Regression coverage for bugs like caching st.Authenticate()
(which creates a widget internally and isn't safe to cache).
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    ROOT / "app.py",
    ROOT / "pages" / "1_Upload.py",
    ROOT / "pages" / "2_Session_Details.py",
    ROOT / "pages" / "3_History.py",
    ROOT / "pages" / "4_Compare.py",
]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_boots_without_exception(page):
    at = AppTest.from_file(str(page))
    at.run()
    assert not list(at.exception), [e.message for e in at.exception]
