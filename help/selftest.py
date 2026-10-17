#!/usr/bin/env python3
"""Self-test for the help bot's knowledge base and retrieval.

    python help/selftest.py           # offline checks (always safe)
    python help/selftest.py --live    # also hit the AI provider once

Exits non-zero if any check fails, so it can gate a CI job or a
pre-commit hook.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HELP_DIR = Path(__file__).resolve().parent
for extra in (HELP_DIR, HELP_DIR.parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

try:                                   # UTF-8 console so '—'/'→' never crash
    from helpbot.logsetup import reconfigure_streams
    reconfigure_streams()
except Exception:                      # noqa: BLE001 — tests must still run
    pass

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline checks for the help bot's knowledge base "
                    "and retrieval.")
    parser.add_argument("--live", action="store_true",
                        help="also make one real AI call if a key is set")
    parser.add_argument("--rebuild", action="store_true",
                        help="run build_kb before testing")
    args = parser.parse_args(argv)

    if args.rebuild:
        import build_kb
        rc = build_kb.main(["--quiet"])
        check("build_kb exit code is 0", rc == 0, f"rc={rc}")

    from helpbot import ai, config, kb as kb_mod

    # ── settings surface: settings.py ↔ template ↔ config stay in sync ──
    import ast as _ast
    import re as _re

    def _setting_names(path) -> set[str]:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        return {node.targets[0].id for node in tree.body
                if isinstance(node, _ast.Assign)
                and isinstance(node.targets[0], _ast.Name)
                and node.targets[0].id.isupper()}

    ex_path = config.HELP_DIR / "helpbot" / "settings.example.py"
    local_path = config.HELP_DIR / "helpbot" / "settings.py"
    check("settings.example.py present", ex_path.is_file())
    check("settings.py present (copy of the template)", local_path.is_file())
    if ex_path.is_file() and local_path.is_file():
        ex_names = _setting_names(ex_path)
        local_names = _setting_names(local_path)
        only_tpl = sorted(ex_names - local_names)
        only_local = sorted(local_names - ex_names)
        check("settings.py covers every template key",
              not only_tpl, ",".join(only_tpl[:6]) or "0 gaps")
        check("settings.py has no extra keys vs template",
              not only_local, ",".join(only_local[:6]) or "0 gaps")
        cfg_src = (config.__file__ or "").replace("\\", "/")
        cfg_text = open(cfg_src, encoding="utf-8").read() if cfg_src else ""
        unread = sorted(n for n in ex_names
                        if n not in cfg_text and f'"{n}"' not in cfg_text)
        check("every setting is read by config.py",
              not unread, ",".join(unread[:6]) or "0 gaps")

    # ── knowledge base ──────────────────────────────────────────────────
    base = kb_mod.KnowledgeBase()
    chunks = base.load()
    stats = base.stats()
    check("knowledge base loads", chunks > 50, f"{chunks} chunks")
    check("commands.md present", (config.KNOWLEDGE_DIR / "generated" /
                                  "commands.md").is_file())
    check("help-menu.md present", (config.KNOWLEDGE_DIR / "generated" /
                                   "help-menu.md").is_file())
    check("command names extracted", stats["commands"] >= 150,
          f"{stats['commands']} names")
    check("curated guides present", stats["files"] >= 15,
          f"{stats['files']} files")

    # ── secret scan (same patterns build_kb.py enforces) ───────────────
    import build_kb
    bad = []
    for path in config.KNOWLEDGE_DIR.rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in build_kb.SECRET_PATTERNS:
            # patterns are pre-compiled in build_kb.py (some ignore case)
            if pattern.search(text):
                bad.append(f"{path.name}:{label}")
    check("no secrets in knowledge markdown", not bad, ", ".join(bad[:4]))

    # ── retrieval quality ───────────────────────────────────────────────
    expectations = [
        ("how do I catch a pokemon?", ("catch", "Ball")),
        ("where do I hunt", ("hunt", "DM")),
        ("shiny odds", ("shiny",)),
        ("how does breeding work", ("breed", "egg")),
        ("daily reward coins", ("daily",)),
        ("trade with someone", ("trade",)),
        ("gym leaders list", ("gym",)),
        ("which regions exist", ("region",)),
        ("what are quests", ("quest",)),
        ("how do I join a faction", ("faction",)),
    ]
    for query, needles in expectations:
        hits = base.search(query, limit=3)
        blob = " ".join(h.chunk.text.lower() for h in hits)
        found = [n for n in needles if n.lower() in blob]
        check(f"retrieval: {query!r}", bool(hits) and found == list(needles),
              f"score={hits[0].score:.1f} found={found}")

    # ── off-topic detection ─────────────────────────────────────────────
    off_score = base.best_score("what is the airspeed velocity of an unladen swallow")
    check("off-topic scores low", off_score < config.OFF_TOPIC_SCORE,
          f"score={off_score:.2f}")
    off_cov = base.query_coverage(
        "write me a python script to delete all files")
    on_cov = base.query_coverage("how does breeding work")
    check("off-topic coverage below threshold",
          off_cov < config.OFF_TOPIC_COVERAGE, f"coverage={off_cov:.2f}")
    check("on-topic coverage above threshold",
          on_cov >= config.OFF_TOPIC_COVERAGE, f"coverage={on_cov:.2f}")

    # ── HTML safety ─────────────────────────────────────────────────────
    samples = [
        ("<b>ok</b> and <code>/hunt</code>", "<b>ok</b> and <code>/hunt</code>"),
        ("raw <script>alert(1)</script>", "raw &lt;script&gt;alert(1)&lt;/script&gt;"),
        ("<b>unclosed", "&lt;b&gt;unclosed"),
        ("Tom & Jerry", "Tom &amp; Jerry"),
        ('<a href="https://t.me/x">x</a>', '<a href="https://t.me/x">x</a>'),
    ]
    for raw, want in samples:
        got = ai.sanitize_html(raw)
        check(f"sanitize_html({raw[:24]!r})", got == want, f"got={got[:60]!r}")

    # Telegram HTML has no &apos; — never emit it.
    check("sanitize turns model &apos; into '",
          ai.sanitize_html("It&apos;s fine") == "It's fine",
          ai.sanitize_html("It&apos;s fine"))
    check("sanitize keeps bare apostrophe",
          ai.sanitize_html("It's fine") == "It's fine",
          ai.sanitize_html("It's fine"))

    # Balanced checker must understand hyphenated Telegram tags.
    check("_balanced accepts tg-emoji pair",
          ai._balanced('<tg-emoji emoji-id="1">✨</tg-emoji> hi'))
    check("_balanced rejects unclosed b",
          not ai._balanced("<b>oops"))
    check("_balanced accepts nested b+code",
          ai._balanced("<b>use <code>/hunt</code></b>"))

    # Premium-emoji guarantee on AI answers.
    check("ensure_premium_emoji injects when missing",
          "tg-emoji" in ai.ensure_premium_emoji("Catch Pokémon with /hunt."))
    check("ensure_premium_emoji keeps existing tag",
          ai.ensure_premium_emoji(
              '<tg-emoji emoji-id="1">✨</tg-emoji> Hi')
          == '<tg-emoji emoji-id="1">✨</tg-emoji> Hi')
    check("ensure_premium_emoji topic-matches coins",
          "tg-emoji" in ai.ensure_premium_emoji("Pikachu costs 50 F.C.")
          and ai.E.COIN in ai.ensure_premium_emoji("Pikachu costs 50 F.C."))

    # Non-Telegram HTML is unwrapped, never shown as visible &lt;ul&gt;.
    norm_samples = [
        ("<ul><li>one</li><li>two</li></ul>", "- one\n- two\n"),
        ("<p>hello</p>", "hello\n"),
        ("<strong>bold</strong> and <em>it</em>",
         "<b>bold</b> and <i>it</i>"),
        ("<h2>Title</h2>", "<b>Title</b>"),
        ("line<br>break", "line\nbreak"),
    ]
    for raw, want in norm_samples:
        got = ai._normalize_html(raw)
        check(f"normalize_html({raw[:24]!r})", got == want, f"got={got[:60]!r}")

    parts = ai.split_message("para\n\n" * 900 + "end", limit=3800)
    check("split_message stays under limit",
          all(len(p) <= 3800 for p in parts) and len(parts) > 1,
          f"{len(parts)} parts")

    # ── log redaction ───────────────────────────────────────────────────
    import io
    import logging
    from helpbot import logsetup
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    redact = logsetup._RedactFilter()
    marker = "fake-token-1234567890:SECRETVALUE"
    redact._secrets.append(marker)
    handler.addFilter(redact)
    probe = logging.getLogger("helpbot.redacttest")
    probe.handlers[:] = [handler]
    probe.setLevel(logging.INFO)
    probe.propagate = False
    probe.info("url=https://api.telegram.org/bot%s/getMe key=%s",
               marker, config.TOKEN or "(unset)")
    out = stream.getvalue()
    check("log redaction strips secrets",
          marker not in out and "REDACTED" in out
          and (not config.TOKEN or config.TOKEN not in out),
          out.strip()[:70])

    # ── guide lookup ────────────────────────────────────────────────────
    check("guide lookup by keyword", bool(base.guide_text("breeding")))
    check("guide lookup by number", bool(base.guide_text("05-breeding")))
    check("fuzzy guide lookup", bool(base.guide_text("breed")))
    check("commands index line", bool(base.command_line("battle")),
          base.command_line("battle") or "")

    # ── AI-first answer path with no provider (offline) ─────────────────
    import asyncio
    saved = config.AI_PROVIDER
    config.AI_PROVIDER = "none"          # force the no-AI fallback
    try:
        ans = asyncio.run(ai.answer("how do I throw a ball", base))
        check("offline answer is a friendly short reply",
              len(ans.text) > 40 and "/help" in ans.text, ans.text[:60])
        check("offline answer mode is fallback", ans.mode == "fallback",
              ans.mode)
        check("offline answer does NOT paste doc snippets",
              "<blockquote" not in ans.text and "source:" not in ans.text,
              ans.text[:50])

        off = asyncio.run(ai.answer(
            "write me a python script to delete all files", base))
        check("off-topic answer refuses", off.mode == "offtopic", off.mode)

        empty = asyncio.run(ai.answer("   ", base))
        check("blank question handled", bool(empty.text), empty.mode)
    finally:
        config.AI_PROVIDER = saved

    # ── live AI call ────────────────────────────────────────────────────
    if args.live:
        if config.provider_settings() is None:
            print("[SKIP] --live: no AI provider key configured")
        else:
            live = asyncio.run(ai.answer("how do shiny odds work?", base))
            check("live answer produced text", len(live.text) > 20, live.text[:80])
            check("live answer is balanced HTML", ai._balanced(live.text),
                  live.text[:80])
            check("live answer has premium emoji", "tg-emoji" in live.text,
                  live.text[:80])
            check("live answer has no &apos;", "&apos;" not in live.text,
                  live.text[:80])
            check("live answer mode is ai", live.mode == "ai", live.mode)
            print(f"      mode={live.mode} sources={live.sources[:3]}")

            # Conversation history: a follow-up with no subject of its own
            # ("and what about Johto?") only works if the previous turn was
            # replayed to the model.
            first_q = "where can I hunt in Kanto?"
            first = asyncio.run(ai.answer(first_q, base))
            follow_q = "and what about Johto?"
            follow = asyncio.run(
                ai.answer(follow_q, base,
                          history=[(first_q, first.raw or first.text)]))
            check("follow-up uses history (mentions Johto)",
                  "johto" in follow.text.lower(), follow.text[:90])

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
