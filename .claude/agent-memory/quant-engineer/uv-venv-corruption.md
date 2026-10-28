---
name: uv-venv-corruption
description: How to recover when an interrupted uv add/sync leaves null-byte files in uv.lock, .venv and the uv cache (Owner's Windows PC)
metadata:
  type: reference
---

A session restart during `uv add` (2026-10-28) left `uv.lock` all NUL bytes, null-byte `.py`/RECORD files in `.venv/Lib/site-packages`, and corrupt entries in the uv cache ("Metadata field Name not found").
Recovery: `git checkout -- uv.lock` then `uv lock`; delete the broken package dirs + dist-info in site-packages; `uv cache clean <pkgs> ttp`; `uv sync`. `--refresh`/`--reinstall-package` alone do not fix a corrupt cache.
`uv add`/`uv sync` can exceed the 2-minute Bash timeout here; run with a longer timeout and log to a file.
