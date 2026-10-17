"""``python -m help`` — entry point for the Forge help bot."""

from __future__ import annotations

import sys
from pathlib import Path

HELP_DIR = Path(__file__).resolve().parent
for _extra in (HELP_DIR, HELP_DIR.parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

if __name__ == "__main__":
    from helpbot.cli import main
    sys.exit(main())
