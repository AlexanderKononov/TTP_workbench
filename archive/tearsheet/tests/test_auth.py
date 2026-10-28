from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _login(username: str, password: str) -> AppTest:
    at = AppTest.from_file(str(APP_PATH))
    at.run()
    at.text_input[0].input(username).run()
    at.text_input[1].input(password).run()
    at.button[0].click().run()
    return at


def test_correct_credentials_log_in():
    at = _login("Alx", "Alx")
    assert not list(at.exception)
    assert at.session_state["auth_user"] == "Alx"


def test_second_user_correct_credentials_log_in():
    at = _login("Ars", "Ars")
    assert not list(at.exception)
    assert at.session_state["auth_user"] == "Ars"


def test_wrong_password_rejected():
    at = _login("Alx", "not-Alx")
    assert not list(at.exception)
    assert "auth_user" not in at.session_state
    assert any("Incorrect username or password" in e.value for e in at.error)


def test_unknown_user_rejected():
    at = _login("nobody", "nobody")
    assert not list(at.exception)
    assert "auth_user" not in at.session_state
    assert any("Incorrect username or password" in e.value for e in at.error)
