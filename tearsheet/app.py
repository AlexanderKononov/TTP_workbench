"""Entry point: branding + login gate + shared header + page navigation.

Phase 2 per BUILD_PLAN.md - multipage app with local auth. See src/auth.py
for the login mechanism and src/session_store.py for the (in-memory, Phase-3-
pending) session history shared across users of this running server.

This is the single script Streamlit actually runs - st.navigation() below
dispatches to the individual page scripts in pages/, but everything above
that call (the logo, the login gate, the header) executes on every
navigation, so it renders once per page view rather than being duplicated in
every page file.

st.navigation() is called unconditionally on every run (logged in or not,
just with a different page list) rather than only after a successful login.
Streamlit falls back to auto-discovering pages/*.py as independent
classic-mode pages - bypassing this login gate entirely - on any run where
st.navigation() isn't reached, so the login form itself is wired up as a
single hidden-nav "page" rather than gating before st.navigation() runs.
"""
from __future__ import annotations

import streamlit as st

from src.activity import compute_daily_activity
from src.auth import current_user, render_header, render_login_form, render_logo
from src.session_store import list_sessions
from src.visualisation import activity_timeline_chart

st.set_page_config(page_title="TTP Tearsheet", layout="wide")
render_logo()

username = current_user()

if username:
    name = username
    render_header(name)

    def _home() -> None:
        st.subheader(f"{name} Trade Statistics")

        my_sessions = list_sessions(participant=username)
        daily = compute_daily_activity(my_sessions)

        if daily.empty:
            st.info("No sessions uploaded yet - upload a trade export to see your trading activity timeline.")
        else:
            total_trades = int(daily["trade_count"].sum())
            active_days = int((daily["trade_count"] > 0).sum())
            summary_cols = st.columns(4)
            summary_cols[0].metric("Sessions", len(my_sessions))
            summary_cols[1].metric("Total Trades", total_trades)
            summary_cols[2].metric("Active Trading Days", active_days)
            summary_cols[3].metric("Last Upload", my_sessions[0]["uploaded_at"].strftime("%Y-%m-%d"))

            st.plotly_chart(activity_timeline_chart(daily), use_container_width=True)

        st.divider()
        st.subheader("Navigate")
        links = [
            ("pages/1_Upload.py", "Upload", ":material/upload_file:", "Upload a trade export CSV and see its statistics."),
            ("pages/2_Session_Details.py", "Session Details", ":material/history:", "Revisit a previously uploaded session."),
            ("pages/3_History.py", "History", ":material/query_stats:", "All your sessions, with monthly rollups."),
            ("pages/4_Compare.py", "Compare", ":material/compare_arrows:", "Side-by-side stats for both participants."),
        ]
        cols = st.columns(2)
        for i, (target, label, icon, description) in enumerate(links):
            with cols[i % 2], st.container(border=True):
                st.page_link(target, label=f"**{label}**", icon=icon)
                st.caption(description)

        st.caption(
            "Session history currently lives in server memory only (Phase 2) and resets "
            "on server restart - persistent storage (Supabase) is Phase 3 of the build plan."
        )

    pages = st.navigation(
        [
            st.Page(_home, title="Home", url_path="home", default=True),
            st.Page("pages/1_Upload.py", title="Upload"),
            st.Page("pages/2_Session_Details.py", title="Session Details"),
            st.Page("pages/3_History.py", title="History"),
            st.Page("pages/4_Compare.py", title="Compare"),
        ]
    )
else:
    pages = st.navigation(
        [st.Page(render_login_form, title="Log in", url_path="login", default=True)],
        position="hidden",
    )

pages.run()
