"""Every test gets a fresh fake Supabase client instead of talking to a real
project - see tests/_fakes.py. Autoused so page-boot smoke tests
(test_app_pages.py) and the full simulated login flow (test_auth.py), which
both run app.py/pages/*.py end-to-end via AppTest, don't need real
SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY credentials to pass.
"""
from __future__ import annotations

import pytest

from src import database
from tests._fakes import FakeSupabaseClient


@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    client = FakeSupabaseClient()
    monkeypatch.setattr(database, "get_client", lambda: client)
    return client
