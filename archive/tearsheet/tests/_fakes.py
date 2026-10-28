"""A minimal in-memory stand-in for the postgrest-py query builder that
src.database drives (table().select/insert/upsert/update().eq().order().execute()).

Shared by tests/conftest.py (so every test, including AppTest-driven page
smoke tests, runs without a live Supabase project) and tests/test_database.py
(which also inspects the fake tables directly).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store: list[dict]):
        self._store = store
        self._op = None
        self._payload: list[dict] = []
        self._filters: dict = {}
        self._order_col = None
        self._order_desc = False
        self._on_conflict = None
        self._ignore_duplicates = False

    def select(self, _cols):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload if isinstance(payload, list) else [payload]
        return self

    def upsert(self, payload, on_conflict=None, ignore_duplicates=False):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        self._ignore_duplicates = ignore_duplicates
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def execute(self) -> FakeResult:
        if self._op == "select":
            rows = [r for r in self._store if all(r.get(k) == v for k, v in self._filters.items())]
            if self._order_col:
                rows = sorted(rows, key=lambda r: r[self._order_col], reverse=self._order_desc)
            return FakeResult(rows)

        if self._op == "insert":
            inserted = []
            for row in self._payload:
                row = dict(row)
                row.setdefault("id", str(uuid4()))
                row.setdefault("uploaded_at", _now_iso())
                row.setdefault("created_at", _now_iso())
                self._store.append(row)
                inserted.append(row)
            return FakeResult(inserted)

        if self._op == "upsert":
            conflict_cols = (self._on_conflict or "").split(",")
            inserted = []
            for row in self._payload:
                row = dict(row)
                is_duplicate = conflict_cols and any(
                    all(existing.get(c) == row.get(c) for c in conflict_cols) for existing in self._store
                )
                if is_duplicate and self._ignore_duplicates:
                    continue
                row.setdefault("id", str(uuid4()))
                row.setdefault("created_at", _now_iso())
                self._store.append(row)
                inserted.append(row)
            return FakeResult(inserted)

        if self._op == "update":
            matched = [r for r in self._store if all(r.get(k) == v for k, v in self._filters.items())]
            for r in matched:
                r.update(self._payload)
            return FakeResult(matched)

        raise AssertionError(f"unsupported op {self._op}")


class FakeSupabaseClient:
    def __init__(self):
        self.tables = {"participants": [], "sessions": [], "trades": []}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables[name])
