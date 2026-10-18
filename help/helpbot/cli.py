"""Command-line interface: ``python -m help [run|build|check|test]``.

Every subcommand configures logging first, so failures are recorded the
same way in development and in production.
"""

from __future__ import annotations

import argparse
import sys

from . import config

# build_kb.py and selftest.py live at help/ top level, not inside the
# package — make sure they are importable no matter how we were started.
if str(config.HELP_DIR) not in sys.path:
    sys.path.insert(0, str(config.HELP_DIR))

import help  # noqa: E402  (the local package, resolved via repo root)

_EPILOG = """\
examples:
  python -m help                 start the bot (polling unless webhook URL set)
  python -m help run --rebuild   regenerate the knowledge base, then start
  python -m help check           validate config, knowledge base and handlers
  python -m help build           regenerate help/knowledge/generated only
  python -m help test --live     run the self-test including a real AI call
  python -m help run --webhook   force webhook mode (needs WEBHOOK_URL)
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m help",
        description="Forge Help Bot — an AI assistant for the Forge "
                    "Pokémon Telegram bot.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="run",
                        choices=("run", "build", "check", "test"),
                        help="run (default) | build | check | test")
    parser.add_argument("--rebuild", action="store_true",
                        help="regenerate help/knowledge/generated first")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--webhook", action="store_true",
                      help="force webhook mode (requires WEBHOOK_URL)")
    mode.add_argument("--polling", action="store_true",
                      help="force long polling even if a webhook URL is set")
    parser.add_argument("--live", action="store_true",
                        help="with 'test': also make one real AI call")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="debug logging")
    parser.add_argument("--no-log-file", action="store_true",
                        help="console logging only (containers)")
    parser.add_argument("--version", action="version",
                        version=f"forge-help-bot {help.__version__}")
    return parser


def _kb_summary() -> str:
    from .kb import KnowledgeBase
    stats = KnowledgeBase().stats()
    return (f"knowledge base: {stats['chunks']} chunks / "
            f"{stats['files']} files / {stats['commands']} commands")


def _ensure_kb(rebuild: bool) -> int:
    """Build the generated knowledge if missing (or asked for)."""
    generated = config.KNOWLEDGE_DIR / "generated" / "commands.md"
    if not rebuild and generated.is_file():
        return 0
    import build_kb
    if not generated.is_file() and not rebuild:
        print("knowledge base missing — building it now…")
    rc = build_kb.main(["--quiet"] if rebuild else [])
    if rc != 0:
        print("knowledge base build FAILED (see above)", file=sys.stderr)
        return rc
    print(_kb_summary())
    return 0


def _check() -> int:
    """Pre-flight: config consistency, KB integrity, handler registration."""
    problems: list[str] = []

    if config.TOKEN:
        print(f"[ OK ] TOKEN set ({len(config.TOKEN)} chars)")
    else:
        problems.append(
            "TOKEN is not set — edit help/helpbot/settings.py "
            "(copy settings.example.py if missing)")

    chain = config.provider_chain()
    if chain:
        print(f"[ OK ] AI providers: {config.format_chain(chain)} "
              f"({len(chain)} keys)")
    else:
        print("[WARN] no AI key — short fallback replies "
              "(set one in settings.py)")

    if config.BUG_REPORT_CHAT_ID:
        print(f"[ OK ] /bug reports → {config.BUG_REPORT_CHAT_ID}")
    if config.OWNER_IDS:
        print(f"[ OK ] owner ids: {', '.join(str(i) for i in sorted(config.OWNER_IDS))}")

    if config.WEBHOOK_URL:
        if config.WEBHOOK_URL.startswith("https://"):
            print(f"[ OK ] webhook: {config.WEBHOOK_URL} "
                  f"(listen {config.WEBHOOK_LISTEN}:{config.WEBHOOK_PORT})")
        else:
            problems.append("WEBHOOK_URL must be https:// (Telegram requirement)")

    from .kb import KnowledgeBase
    base = KnowledgeBase()
    try:
        stats = base.stats()
    except Exception as exc:                      # noqa: BLE001
        problems.append(f"knowledge base failed to load: {exc}")
        stats = None
    if stats:
        print(f"[ OK ] knowledge: {stats['chunks']} chunks, "
              f"{stats['files']} files, {stats['commands']} commands")
        if stats["commands"] < 100:
            problems.append(f"only {stats['commands']} commands extracted — "
                            "did you run 'python -m help build'?")

    if config.TOKEN:
        try:
            from .bot import build_app
            app = build_app()
            total = sum(len(h) for h in app.handlers.values())
            print(f"[ OK ] handlers registered: {total}")
        except Exception as exc:                  # noqa: BLE001
            problems.append(f"handler registration failed: {exc}")

    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return 1
    print("check passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    from . import logsetup
    logsetup.configure(verbose=args.verbose,
                       log_file=config.LOG_FILE and not args.no_log_file)

    if args.command == "build":
        import build_kb
        rc = build_kb.main([] if args.verbose else ["--quiet"])
        if rc == 0:
            print(_kb_summary())
        return rc

    if args.command == "check":
        return _check()

    if args.command == "test":
        import selftest
        test_args = []
        if args.live:
            test_args.append("--live")
        if args.rebuild:
            test_args.append("--rebuild")
        return selftest.main(test_args)

    # run (default)
    if args.webhook and not config.WEBHOOK_URL:
        print("--webhook needs WEBHOOK_URL set in help/helpbot/settings.py",
              file=sys.stderr)
        return 3
    rc = _ensure_kb(args.rebuild)
    if rc:
        return rc
    from .bot import main as bot_main
    webhook = True if args.webhook else (False if args.polling else None)
    return bot_main(webhook=webhook)


if __name__ == "__main__":
    raise SystemExit(main())
