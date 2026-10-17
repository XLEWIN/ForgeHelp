#!/usr/bin/env python3
"""Backward-compatible wrapper around ``python -m help``.

    python help/run.py              # start the bot
    python help/run.py --rebuild    # regenerate the knowledge base first
    python help/run.py --check      # pre-flight validation

Prefer ``python -m help`` from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

HELP_DIR = Path(__file__).resolve().parent
for extra in (HELP_DIR, HELP_DIR.parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from helpbot.cli import main as cli_main  # noqa: E402


def main() -> int:
    # Translate the legacy --check flag into the new subcommand.
    argv = ["check" if arg == "--check" else arg for arg in sys.argv[1:]]
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
