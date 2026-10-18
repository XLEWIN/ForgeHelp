"""Production logging: console + rotating file, with secrets redacted.

Anything that could ever carry a credential — a bot token inside a
Telegram API URL, an ``Authorization: Bearer …`` header, an API key in a
provider error body — is stripped before the record reaches a handler.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from . import config

#: Console format kept short; the file gets the same, both UTF-8.
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
#: 5 MiB × 5 rotated files is plenty for a chat bot.
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
#: Loggers that are chatty at INFO in a long-running service.
_QUIET = ("httpx", "httpcore", "apscheduler", "telegram.ext.updater")

LOGGER = logging.getLogger("helpbot")


def reconfigure_streams() -> None:
    """Make stdout/stderr UTF-8 with replacement for un-encodable chars.

    Windows defaults to a legacy codepage (cp1252) where characters like
    ``→`` crash ``print`` and garble log lines. UTF-8 output is safe on
    every modern terminal; anything the terminal cannot show degrades to
    ``?`` instead of raising UnicodeEncodeError mid-run.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass                              # redirected/non-TTY stream


class _RedactFilter(logging.Filter):
    """Replace known credentials with ``***`` in every record."""

    def __init__(self) -> None:
        super().__init__()
        # TOKEN + every configured AI key (all OpenRouter backups too).
        self._secrets = [s for s in config.all_api_keys() if len(s) > 8]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:                     # noqa: BLE001 — never drop a record
            return True
        changed = False
        for secret in self._secrets:
            if secret in message:
                message = message.replace(secret, "***REDACTED***")
                changed = True
        if changed:
            record.msg = message
            record.args = None
        return True


def configure(verbose: bool = False, log_file: bool = True,
              log_dir: Path | None = None) -> Path | None:
    """Install handlers on the root logger. Safe to call once per process."""
    reconfigure_streams()
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):       # idempotent: replace ours
        if getattr(handler, "_helpbot_handler", False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    redact = _RedactFilter()

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(redact)
    console._helpbot_handler = True           # type: ignore[attr-defined]
    root.addHandler(console)

    log_path: Path | None = None
    if log_file:
        directory = log_dir or (config.HELP_DIR / "logs")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            log_path = directory / "helpbot.log"
            rotating = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT,
                encoding="utf-8")
            rotating.setFormatter(formatter)
            rotating.addFilter(redact)
            rotating._helpbot_handler = True  # type: ignore[attr-defined]
            root.addHandler(rotating)
        except OSError as exc:                # read-only install: console only
            root.warning("cannot open log file (%s); console logging only", exc)
            log_path = None

    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
    return log_path
