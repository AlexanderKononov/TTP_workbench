"""Minimal login gate for the app's 2 known users.

By explicit request this is intentionally as simple as possible: a fixed
username/password pair per person, checked in-process, no hashing/cookies/
external config. This is a name-gate, not real security - fine for a
private 2-person tool, not for anything sensitive. Session state resets on
page reload (no persistent cookie), which is an accepted trade-off for the
simplicity.
"""
from __future__ import annotations

import streamlit as st

USERS = {
    "Alx": "Alx",
    "Ars": "Ars",
}


def require_login() -> tuple[str, str]:
    """Render a login form (if needed) and stop execution unless logged in.

    Returns (username, username) once authenticated - kept as a pair for
    compatibility with pages that unpack (username, display_name).
    """
    username = st.session_state.get("auth_user")
    if username:
        with st.sidebar:
            st.caption(f"Logged in as **{username}**")
            if st.button("Log out"):
                del st.session_state["auth_user"]
                st.rerun()
        return username, username

    st.title("Log in")
    with st.form("login_form"):
        entered_username = st.text_input("Username")
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        if USERS.get(entered_username) == entered_password:
            st.session_state["auth_user"] = entered_username
            st.rerun()
        else:
            st.error("Incorrect username or password.")

    st.stop()
