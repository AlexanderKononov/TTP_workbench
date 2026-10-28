"""Minimal login gate for the app's 2 known users.

By explicit request this is intentionally as simple as possible: a fixed
username/password pair per person, checked in-process, no hashing/cookies/
external config. This is a name-gate, not real security - fine for a
private 2-person tool, not for anything sensitive. Session state resets on
page reload (no persistent cookie), which is an accepted trade-off for the
simplicity.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

USERS = {
    "Alx": "Alx",
    "Ars": "Ars",
}

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.svg"


def current_user() -> str | None:
    """Return the logged-in username from session state, or None."""
    return st.session_state.get("auth_user")


def render_logo() -> None:
    """Show the app's branding in the upper-left corner (app.py and sidebar).

    Call this unconditionally, before checking login state, so it also
    appears on the login screen.
    """
    st.logo(str(LOGO_PATH), size="large")


def render_login_form() -> None:
    """Render the login form. Only call this when current_user() is None.

    Used as the sole page in app.py's st.navigation() call while logged out,
    so st.navigation() still runs on every request (logged in or not) - it
    must run unconditionally, or Streamlit falls back to auto-discovering
    pages/*.py as independent classic-mode pages that never pass through
    this login gate at all.
    """
    st.subheader("Log in")
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


def render_header(name: str) -> None:
    """Render a user/log-out chip in the top-right, alongside Streamlit's
    own Deploy/menu toolbar. App branding (top-left) is handled separately
    by render_logo().

    Meant to be called exactly once, in app.py, before st.navigation() so it
    appears once per page load rather than being re-rendered per page.

    There's no public Streamlit API for adding controls into the top-right
    toolbar itself, so this chip is a small fixed-position CSS overlay
    pinned next to it, offset far enough left to clear the Deploy button and
    menu icon. A future Streamlit layout change could require adjusting that
    offset.
    """
    st.markdown(
        """
        <style>
        div.st-key-ttp_user_chip {
            position: fixed;
            top: 0;
            right: 8.5rem;
            width: fit-content;
            height: 3.75rem;
            z-index: 999995;
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 0.75rem;
            pointer-events: none;
        }
        div.st-key-ttp_user_chip * {
            pointer-events: auto;
        }
        div.st-key-ttp_user_chip [data-testid="stMarkdownContainer"] p {
            margin: 0;
            font-size: 0.9rem;
            color: rgba(49, 51, 63, 0.85);
            white-space: nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="ttp_user_chip"):
        st.markdown(f"Signed in as **{name}**")
        if st.button("Log out", key="ttp_logout_btn", type="tertiary"):
            del st.session_state["auth_user"]
            st.rerun()
