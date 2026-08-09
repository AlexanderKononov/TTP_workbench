"""In-memory session history, shared by all users of this running server.

This is a placeholder for Supabase persistence (BUILD_PLAN.md Phase 3): it
uses st.cache_resource to hold one shared list for the whole process, so
History/Compare work across users while the server is up. It still resets
on every server restart and won't survive a Streamlit Cloud redeploy or
multi-instance deployment - see memo principle "do not store persistent
application data locally" for why this is a Phase 2 stand-in, not the
final design.
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pandas as pd
import streamlit as st


@st.cache_resource
def _store() -> list[dict]:
    return []


def add_session(participant: str, file_name: str, trades: pd.DataFrame, stats: dict) -> str:
    session_id = str(uuid4())
    _store().append(
        {
            "id": session_id,
            "participant": participant,
            "file_name": file_name,
            "uploaded_at": datetime.now(),
            "session_date": trades["trade_time"].min(),
            "trades": trades,
            "stats": stats,
        }
    )
    return session_id


def list_sessions(participant: str | None = None) -> list[dict]:
    sessions = _store()
    if participant is not None:
        sessions = [s for s in sessions if s["participant"] == participant]
    return sorted(sessions, key=lambda s: s["uploaded_at"], reverse=True)


def get_session(session_id: str) -> dict | None:
    for s in _store():
        if s["id"] == session_id:
            return s
    return None


def list_participants() -> list[str]:
    return sorted({s["participant"] for s in _store()})
