"""Supabase-backed persistent trade storage (see SUPABASE_PLAN.md).

Replaces src/session_store.py's in-memory, process-local store. The key
design point: statistics are never saved as a snapshot. Every read here
(get_all_trades, list_sessions, get_session_trades) recomputes
src.statistics.compute_stats() over whatever trades are currently in
Postgres for a participant, so "yesterday's trades + today's upload" is
handled just by there being more rows to query - no merge/incremental-math
logic needed.

The one real piece of logic is dedup: uploads can overlap (the same trade
appearing in two exports), so each trade gets a deterministic trade_hash
and a `unique (participant_id, trade_hash)` constraint (see supabase/schema.sql)
makes re-inserting the same trade a no-op via upsert(ignore_duplicates=True).
"""
from __future__ import annotations

import hashlib
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from src.statistics import compute_stats

load_dotenv()

TRADE_COLUMNS = ["trade_time", "market", "symbol", "direction", "profit", "profit_pct", "fee", "net_pnl"]


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY aren't available."""


def _credentials() -> tuple[str, str]:
    url = key = None
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["service_role_key"]
    except Exception:
        pass
    url = url or os.environ.get("SUPABASE_URL")
    key = key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SupabaseNotConfiguredError(
            "Supabase credentials not found. Copy .env.example to .env (or "
            ".streamlit/secrets.toml.example to .streamlit/secrets.toml) and "
            "fill in SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY."
        )
    return url, key


@st.cache_resource
def get_client() -> Client:
    url, key = _credentials()
    return create_client(url, key)


def _trade_hash(participant_id: str, row: pd.Series) -> str:
    key = f"{participant_id}|{row['trade_time']}|{row['symbol']}|{row['direction']}|{row['profit']}|{row['fee']}"
    return hashlib.sha256(key.encode()).hexdigest()


def _to_naive(value) -> pd.Timestamp:
    """Supabase's timestamptz columns round-trip as tz-aware (UTC-offset)
    values, but the rest of the app (CSV parsing, activity.py's
    pd.Timestamp.now()) works entirely in naive timestamps. Normalizing to
    UTC and dropping tzinfo here restores the original naive value (it was
    stored as UTC in the first place - see save_upload) instead of leaking
    tz-awareness into code that isn't expecting to compare against it.
    """
    result = pd.to_datetime(value, utc=True)
    return result.dt.tz_localize(None) if isinstance(result, pd.Series) else result.tz_localize(None)


def _rows_to_trades_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=TRADE_COLUMNS)
    if df.empty:
        return df
    df["trade_time"] = _to_naive(df["trade_time"])
    for col in ("profit", "profit_pct", "fee", "net_pnl"):
        df[col] = pd.to_numeric(df[col])
    return df.sort_values("trade_time").reset_index(drop=True)


def ensure_participant(username: str, client: Client | None = None) -> str:
    client = client or get_client()
    existing = client.table("participants").select("id").eq("username", username).execute()
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("participants").insert({"username": username}).execute()
    return created.data[0]["id"]


def save_upload(username: str, file_name: str, file_format: str, trades: pd.DataFrame) -> dict:
    """Persist a processed upload: one sessions row + dedup-inserted trades.

    Returns {"session_id", "participant_id", "trade_count", "inserted_count",
    "duplicate_count"}.
    """
    client = get_client()
    participant_id = ensure_participant(username, client)

    session = (
        client.table("sessions")
        .insert(
            {
                "participant_id": participant_id,
                "file_name": file_name,
                "file_format": file_format,
                "trade_count": len(trades),
            }
        )
        .execute()
        .data[0]
    )
    session_id = session["id"]

    rows = [
        {
            "participant_id": participant_id,
            "session_id": session_id,
            "trade_time": row["trade_time"].isoformat(),
            "market": row["market"],
            "symbol": row["symbol"],
            "direction": row["direction"],
            "profit": float(row["profit"]),
            "profit_pct": None if pd.isna(row["profit_pct"]) else float(row["profit_pct"]),
            "fee": float(row["fee"]),
            "net_pnl": float(row["net_pnl"]),
            "trade_hash": _trade_hash(participant_id, row),
        }
        for _, row in trades.iterrows()
    ]

    inserted_count = 0
    if rows:
        result = (
            client.table("trades")
            .upsert(rows, on_conflict="participant_id,trade_hash", ignore_duplicates=True)
            .execute()
        )
        inserted_count = len(result.data or [])

    client.table("sessions").update({"inserted_count": inserted_count}).eq("id", session_id).execute()

    return {
        "session_id": session_id,
        "participant_id": participant_id,
        "trade_count": len(trades),
        "inserted_count": inserted_count,
        "duplicate_count": len(trades) - inserted_count,
    }


def get_all_trades(username: str) -> pd.DataFrame:
    client = get_client()
    participant_id = ensure_participant(username, client)
    result = (
        client.table("trades")
        .select(",".join(TRADE_COLUMNS))
        .eq("participant_id", participant_id)
        .order("trade_time")
        .execute()
    )
    return _rows_to_trades_df(result.data)


def get_session_trades(session_id: str) -> pd.DataFrame:
    client = get_client()
    result = (
        client.table("trades")
        .select(",".join(TRADE_COLUMNS))
        .eq("session_id", session_id)
        .order("trade_time")
        .execute()
    )
    return _rows_to_trades_df(result.data)


def list_sessions(participant: str) -> list[dict]:
    """Sessions for one participant, newest first - same shape as the retired
    session_store.list_sessions() (id, participant, file_name, uploaded_at,
    session_date, trades, stats) so callers (app.py's activity timeline,
    2_Session_Details.py, 3_History.py) didn't need to change.

    Sessions with zero inserted trades (e.g. a fills file with no closed
    trades) are skipped, matching the old store's behavior of only saving
    sessions that had trades in the first place.
    """
    client = get_client()
    participant_id = ensure_participant(participant, client)
    rows = (
        client.table("sessions")
        .select("id, file_name, uploaded_at")
        .eq("participant_id", participant_id)
        .order("uploaded_at", desc=True)
        .execute()
        .data
    )

    sessions = []
    for row in rows:
        trades = get_session_trades(row["id"])
        if trades.empty:
            continue
        sessions.append(
            {
                "id": row["id"],
                "participant": participant,
                "file_name": row["file_name"],
                "uploaded_at": _to_naive(row["uploaded_at"]).to_pydatetime(),
                "session_date": trades["trade_time"].min(),
                "trades": trades,
                "stats": compute_stats(trades),
            }
        )
    return sessions


def list_participants() -> list[str]:
    client = get_client()
    rows = client.table("participants").select("username").execute().data
    return sorted(row["username"] for row in rows)
