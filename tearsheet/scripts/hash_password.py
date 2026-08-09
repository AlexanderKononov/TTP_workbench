"""One-off helper: hash a plain-text password for auth_config.yaml.

Usage:
    python scripts/hash_password.py "my-new-password"

Paste the printed hash into auth_config.yaml under the user's `password` field.
Never commit plain-text passwords or auth_config.yaml itself (it's gitignored).
"""
import sys

import streamlit_authenticator as stauth


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    print(stauth.Hasher.hash(sys.argv[1]))


if __name__ == "__main__":
    main()
