#!/usr/bin/env python3
"""Build the Forge help-bot knowledge base from the repository source.

Reads the real code (no imports, no network, no database) and writes
markdown the help bot retrieves from:

    help/knowledge/generated/commands.md      every registered /command
    help/knowledge/generated/help-menu.md     the in-bot /help menu
    help/knowledge/generated/manifest.json    counts + file list

Source of truth:

* ``CommandHandler("name", handler)`` registrations across ``forge/``
* the handler's docstring (first line) as the description
* the file's module comment / docstring as the module summary
* ``_MODULES`` in ``forge/modules/core/help.py`` for the curated menu

After writing it runs a secret scan over EVERY markdown file under
``help/knowledge/`` and fails loudly if a bot token, database URL or
credential-looking literal ended up in the knowledge base.

Usage:
    python help/build_kb.py            # build + verify
    python help/build_kb.py --quiet    # only print problems
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HELP_DIR = Path(__file__).resolve().parent
ROOT = HELP_DIR.parent
#: Source of truth for command extraction. The help bot is standalone —
#: point FORGE_SOURCE_DIR at a local clone of the main Forge repo when
#: regenerating. Default: sibling ``forge/`` directory (when present).
FORGE_DIR = Path(os.environ.get("FORGE_SOURCE_DIR", "") or (ROOT / "forge"))
OUT_DIR = HELP_DIR / "knowledge" / "generated"
KNOWLEDGE_DIR = HELP_DIR / "knowledge"

#: Files whose commands are deliberately NOT published. Empty by default:
#: admin/owner commands are documented too (they are restricted, not
#: secret) — only credentials are filtered, by the secret scan below.
EXCLUDE_FILES: set[str] = set()

#: Display order for module areas in commands.md.
AREA_TITLES = OrderedDict([
    ("start", "Getting started"),
    ("core", "Core & help"),
    ("spawn", "Wild spawns & encounters"),
    ("battle", "Battles & gyms"),
    ("pokedex", "Pokédex & Pokémon data"),
    ("collection", "Collection, PC & storage"),
    ("regions", "Regions, travel & Safari"),
    ("economy", "Economy, shop & items"),
    ("trading", "Trading & gifts"),
    ("profile", "Profile & leaderboards"),
    ("games", "Mini-games"),
    ("faction", "Factions"),
    ("quests", "Quests"),
    ("achievements", "Achievements"),
    ("seasons", "Ranked seasons"),
    ("gym", "Gym league"),
    ("zmove", "Z-Moves"),
    ("antibot", "Anti-bot verification"),
    ("maintenance", "Maintenance (sudo)"),
    ("admin", "Admin & moderation (owner/sudo)"),
    ("utils", "Utilities"),
    ("messages", "Message strings"),
    ("database", "Database helpers"),
    ("shop", "Web shop"),
    ("rich", "Rich message helpers"),
    ("scripts", "Repository scripts"),
])

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv"}

# ── Secret patterns ──────────────────────────────────────────────────────
# Anything matching one of these in a knowledge file aborts the build.
SECRET_PATTERNS = [
    ("bot token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
    ("database URL with credentials",
     re.compile(r"mongodb(?:\+srv)?://[^\s'\"`]*:[^\s'\"`]+@", re.I)),
    ("api hash", re.compile(r"\b[a-f0-9]{32}\b")),           # telegram api_hash
    ("bearer/sk key", re.compile(r"\b(?:sk|key|ghp|xoxb)[-_][A-Za-z0-9]{16,}\b")),
    ("credential assignment",
     re.compile(r"^\s*(?:TOKEN|API_HASH|MONGO_URL|SECRET|PASSWORD)\s*=\s*\S",
                re.M)),
]


# ── Source walking ───────────────────────────────────────────────────────

def iter_py_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def area_of(relpath: str) -> str:
    """forge/modules/battle/commands.py -> battle; forge/__main__.py -> start."""
    parts = relpath.split("/")
    if len(parts) > 2 and parts[1] == "modules":
        return parts[2]
    if len(parts) == 2 and parts[1].endswith(".py"):
        # Top-level file: forge/__main__.py is the getting-started entry
        # point, everything else at that level is plumbing.
        return "start" if parts[1] == "__main__.py" else "core"
    if len(parts) > 1:
        return parts[1]
    return "core"


def clean_desc(cmd: str, desc: str) -> str:
    """Turn 'Handle /battle — challenge another trainer…' into its description.

    Source docstrings are written as handler routing notes
    ('Handle /data <pokemon> command.', 'Redirect /setteam — show help'),
    so the command name, its argument placeholders and the routing verbs
    are stripped away before the remainder is used as the player-facing
    description.
    """
    if not desc:
        return ""
    token = rf"/{re.escape(cmd)}"
    d = desc.strip()
    for _ in range(4):
        before = d
        # routing verbs may name a different (primary) command
        d = re.sub(r"^(?:handle|redirect|for)\s+/?[a-z0-9_]+\b", "", d, flags=re.I)
        d = re.sub(rf"^{token}\b", "", d)
        # argument placeholders and "(aliases: ...)" notes
        d = re.sub(r"^\s*(?:\([^)]*\)|<[^>]*>|\[[^\]]*\])", "", d)
        d = re.sub(r"^\s*(?:—|-|:|,)\s*", "", d)
        d = d.strip()
        if d == before:
            break
    # leftovers that are scaffolding, not a description
    if re.match(r"^(?:the\s+)?(?:command|cmd|entry point)\.?\s*$", d, flags=re.I):
        d = ""
    d = re.sub(r"^(?:command|cmd|entry point)\s*(?:—|-|:)\s*", "", d,
               flags=re.I).strip()
    return d


def file_summary(tree: ast.AST, raw: str) -> str:
    """Module docstring, else the leading comment block (one tidy line)."""
    doc = ast.get_docstring(tree) if isinstance(tree, (ast.Module,)) else None
    if doc:
        line = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
        if line:
            return _tidy(line, 240)

    for raw_line in raw.splitlines()[:40]:
        line = raw_line.strip()
        if not line.startswith("#"):
            if line:
                break          # hit real code before any comment
            continue
        line = line.lstrip("#").strip()
        if not line or not _is_prose(line):
            continue
        return _tidy(line, 240)
    return ""


def _is_prose(line: str) -> bool:
    """Skip banner rules, box drawing and lone emoji/arrow decorations."""
    letters = sum(ch.isalpha() for ch in line)
    return len(line) >= 12 and letters >= 8


def _tidy(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text[: limit - 1] + "…" if len(text) > limit else text


def extract(path: Path):
    """Return (module_summary, {handler_name: docstring}, [(cmd, handler)])."""
    # utf-8-sig: a good share of the repo files start with a BOM, which
    # ast.parse rejects as "invalid non-printable character U+FEFF".
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        tree = ast.parse(raw, filename=str(path))
    except SyntaxError:
        return "", {}, []

    summary = file_summary(tree, raw)

    funcs: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            first = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
            if first and node.name not in funcs:
                funcs[node.name] = _tidy(first, 240)

    commands = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "CommandHandler" or not node.args:
            continue
        arg0 = node.args[0]
        # CommandHandler("cmd", ...) or CommandHandler(["cmd", "alias"], ...)
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
            names = [arg0.value]
        elif isinstance(arg0, (ast.List, ast.Tuple)):
            names = [e.value for e in arg0.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        else:
            continue
        handler = ""
        if len(node.args) > 1 and isinstance(node.args[1], ast.Name):
            handler = node.args[1].id
        elif len(node.args) > 1 and isinstance(node.args[1], ast.Lambda):
            handler = "<lambda>"
        for i, cmd_name in enumerate(names):
            commands.append((cmd_name.lower(), handler, i > 0))
    return summary, funcs, commands


def extract_help_menu() -> list[dict]:
    """Literal _MODULES from the real /help module (curated descriptions)."""
    path = FORGE_DIR / "modules" / "core" / "help.py"
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
    except SyntaxError:
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "_MODULES" in targets:
                try:
                    return list(ast.literal_eval(node.value))
                except (ValueError, SyntaxError):
                    return []
    return []


# ── Rendering ────────────────────────────────────────────────────────────

def _count(n: int) -> str:
    return f"{n} command" if n == 1 else f"{n} commands"


def render_commands(entries) -> str:
    """entries: area -> list of (cmd, description, relpath), sorted."""
    total = sum(len(v) for v in entries.values())
    lines = [
        "# Forge — complete command index",
        "",
        f"Every slash command registered by the bot ({total} commands).",
        "Generated by `python help/build_kb.py` from the source tree —",
        "do not edit by hand.",
        "",
        "Prefix is `/`. Anything marked (owner/sudo) is restricted to",
        "moderators and will not work for regular players.",
        "",
    ]
    for area, title in AREA_TITLES.items():
        rows = entries.get(area)
        if not rows:
            continue
        lines.append(f"## {title} ({_count(len(rows))})")
        lines.append("")
        for cmd, desc, src in rows:
            detail = desc or "no description in source"
            lines.append(f"- `/{cmd}` — {detail}  [{src}]")
        lines.append("")
    # Any area not in the ordering table still gets published.
    for area in sorted(set(entries) - set(AREA_TITLES)):
        rows = entries[area]
        lines.append(f"## {area} ({_count(len(rows))})")
        lines.append("")
        for cmd, desc, src in rows:
            lines.append(f"- `/{cmd}` — {desc or 'no description in source'}  [{src}]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_help_menu(modules) -> str:
    """Markdown version of the bot's own /help menu."""
    lines = [
        "# Forge — /help menu (as shown inside the bot)",
        "",
        "The bot's built-in `/help` menu. Each module is a page of",
        "commands with a one-line description and examples.",
        "",
    ]
    for mod in modules:
        lines.append(f"## {mod.get('title') or mod.get('short')}")
        lines.append("")
        for header, cmds in mod.get("sections", []):
            lines.append(f"### {header}")
            lines.append("")
            for row in cmds:
                left, sep, right = row.partition(" — ")
                left = (left.replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&amp;", "&"))
                right = (right.replace("&lt;", "<").replace("&gt;", ">")
                         .replace("&amp;", "&"))
                if sep:
                    lines.append(f"- `{left}` — {right}")
                else:
                    lines.append(f"- `{left}`")
            lines.append("")
        notes = mod.get("notes") or []
        if notes:
            lines.append("Notes:")
            lines.append("")
            for note in notes:
                lines.append(f"- {note.replace('• ', '')}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ── Secret scan ──────────────────────────────────────────────────────────

def scan_for_secrets(paths) -> list[str]:
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                snippet = match.group(0)
                # A bare 32-hex string only matters next to hash-ish words;
                # api_hash lookalikes in prose (ids, colours) are noise.
                if label == "api hash":
                    start = max(0, match.start() - 40)
                    context = text[start:match.end() + 40].lower()
                    if not any(w in context for w in ("hash", "api_id", "api hash")):
                        continue
                line_no = text.count("\n", 0, match.start()) + 1
                problems.append(
                    f"{path.relative_to(ROOT).as_posix()}:{line_no}: "
                    f"{label} -> {snippet[:24]}…"
                )
    return problems


# ── Main ─────────────────────────────────────────────────────────────────

def build(quiet: bool = False) -> int:
    if not FORGE_DIR.is_dir():
        # Standalone repo: no forge source checked in. Keep the committed
        # generated indexes and just re-run the secret scan so knowledge
        # files stay clean.
        if not quiet:
            print(f"note: {FORGE_DIR} not found — skipping source extraction; "
                  "keeping committed generated/ indexes.")
        kb_files = sorted(p for p in KNOWLEDGE_DIR.rglob("*.md"))
        problems = scan_for_secrets(kb_files)
        if problems:
            print("SECRET SCAN FAILED — knowledge base must stay clean:",
                  file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        if not quiet:
            print(f"secret scan: clean ({len(kb_files)} markdown files checked)")
        return 0

    # relpath -> (summary, funcs, commands)
    per_file = {}
    for path in iter_py_files(FORGE_DIR):
        per_file[rel(path)] = extract(path)

    # Help-menu descriptions keyed by bare command name ("/buy x" -> "buy")
    modules = extract_help_menu()
    menu_index: dict[str, str] = {}
    for mod in modules:
        for _header, cmds in mod.get("sections", []):
            for row in cmds:
                left, sep, right = row.partition(" — ")
                if not sep or not right:
                    continue
                desc = (right.replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&amp;", "&"))
                desc = _tidy(desc, 200)
                # "/tradecancel · /canceltrade — Cancel a pending trade"
                # puts the description on every command in the left cell.
                for name in re.findall(r"/([a-z0-9_]+)", left.lower()):
                    menu_index.setdefault(name, desc)

    entries: dict[str, list] = defaultdict(list)
    seen: set[str] = set()
    for relpath, (summary, funcs, commands) in sorted(per_file.items()):
        if relpath in EXCLUDE_FILES:
            continue
        area = area_of(relpath)
        for cmd, handler, is_alias in commands:
            key = cmd.split("@")[0]
            if not key or key in seen:
                continue
            seen.add(key)
            doc = clean_desc(key, funcs.get(handler) or "")
            menu = menu_index.get(key, "")
            # A cleaned docstring wins when it is a real sentence; short
            # leftovers like "command." fall back to the curated menu text.
            desc = doc if len(doc) >= 20 else (menu or doc)
            if not desc:
                first = re.match(r"/([a-z0-9_]+)", summary or "")
                if first and first.group(1).lower() == key:
                    desc = summary
            if is_alias:
                desc = f"{desc} (alias)" if desc else "alias of the same command"
            entries[area].append((key, _tidy(desc, 220), relpath))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    commands_md = OUT_DIR / "commands.md"
    menu_md = OUT_DIR / "help-menu.md"
    manifest = OUT_DIR / "manifest.json"

    commands_md.write_text(render_commands(entries), encoding="utf-8")
    menu_md.write_text(render_help_menu(modules), encoding="utf-8")

    kb_files = sorted(p for p in KNOWLEDGE_DIR.rglob("*.md"))
    manifest.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_root": "forge/",
        "commands": sum(len(v) for v in entries.values()),
        "commands_by_area": {k: len(v) for k, v in sorted(entries.items())},
        "help_menu_modules": len(modules),
        "knowledge_files": [p.relative_to(HELP_DIR).as_posix() for p in kb_files],
    }, indent=2) + "\n", encoding="utf-8")

    problems = scan_for_secrets(kb_files)
    if problems:
        print("SECRET SCAN FAILED — knowledge base must stay clean:",
              file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if not quiet:
        total = sum(len(v) for v in entries.values())
        print(f"knowledge base written:")
        print(f"  {commands_md.relative_to(ROOT).as_posix()}  "
              f"{total} commands in {len(entries)} areas")
        print(f"  {menu_md.relative_to(ROOT).as_posix()}  {len(modules)} menu modules")
        print(f"  {manifest.relative_to(ROOT).as_posix()}")
        print(f"secret scan: clean ({len(kb_files)} markdown files checked)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true",
                        help="only print problems")
    args = parser.parse_args(argv)
    return build(quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
