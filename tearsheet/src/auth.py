"""Login gate backed by streamlit-authenticator.

Credentials come from one of two places:

- Streamlit Secrets (st.secrets["auth"]) when deployed to Streamlit Cloud -
  set these in the app's Settings > Secrets, never committed to git.
- A local auth_config.yaml (gitignored) for local development - see
  auth_config.example.yaml for the template.

v1 auth per BUILD_PLAN.md §5: two known users, no public registration - add
or change users with scripts/hash_password.py. Replace with Supabase Auth in
Phase 3/5 when the app moves off a single machine.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit.errors import StreamlitSecretNotFoundError

CONFIG_PATH = Path(__file__).resolve().parents[1] / "auth_config.yaml"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "auth_config.example.yaml"


def _load_config_from_secrets() -> dict | None:
    try:
        if "auth" not in st.secrets:
            return None
    except StreamlitSecretNotFoundError:
        return None

    auth_secrets = st.secrets["auth"]
    return {
        "credentials": {
            "usernames": {
                username: dict(user_data)
                for username, user_data in auth_secrets["credentials"]["usernames"].items()
            }
        },
        "cookie": dict(auth_secrets["cookie"]),
    }


def _load_config() -> dict:
    from_secrets = _load_config_from_secrets()
    if from_secrets is not None:
        return from_secrets

    if not CONFIG_PATH.exists():
        st.error(
            f"No login credentials found. Either set Streamlit Secrets under "
            f"the `auth` key (see .streamlit/secrets.toml.example), or copy "
            f"`{EXAMPLE_CONFIG_PATH.name}` to `{CONFIG_PATH.name}` for local "
            "development (see the comments in the example file)."
        )
        st.stop()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_authenticator() -> stauth.Authenticate:
    # Not cached: Authenticate() creates a cookie-manager widget internally,
    # and Streamlit forbids widget creation inside @st.cache_* functions.
    # Reading+building this fresh each rerun is cheap for a 2-user YAML file.
    config = _load_config()
    return stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )


def require_login() -> tuple[str, str]:
    """Render the login form (if needed) and stop execution unless logged in.

    Returns (username, display_name) once authenticated.
    """
    authenticator = get_authenticator()

    if st.session_state.get("authentication_status") is not True:
        authenticator.login(location="main")

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Username or password is incorrect.")
        st.stop()
    if status is None:
        st.info("Please log in to continue.")
        st.stop()

    username = st.session_state["username"]
    name = st.session_state["name"]

    with st.sidebar:
        st.caption(f"Logged in as **{name}**")
        authenticator.logout("Log out", location="sidebar")

    return username, name
