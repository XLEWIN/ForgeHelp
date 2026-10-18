"""Competitive build recommender for ``/build [pokemon]``.

Opens a 4-category inline menu (ATK / SP.ATK / DEF / SP.DEF), then
edits the message into a paged build card with the Pokémon artwork:

  · Summary — nature, EV spread, IVs, key stats at Lv.100, items
  · Moves   — top damaging moves for that category (STAB first)
  · Back / Close

Uses the same photo + caption-edit + colored-keyboard pattern as
``/poke`` so callbacks stay fast and the picture never moves.
Callback data: ``bd|{id}|{cat}|{view}|{page}``
  cat:  atk | spatk | def | spdef
  view: menu | sum | mv | close
"""

from __future__ import annotations

import html as html_lib
import logging
import math
from typing import Optional

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import pokemon
from .emojis import E, type_line, type_tag, ui_tag
from .rich import (DANGER, PRIMARY, SUCCESS, classic_html, colored_kb_dict,
                   edit_caption, edit_message_html, fetch_image,
                   send_photo_bytes, send_photo_url, send_rich_step)

LOGGER = logging.getLogger(__name__)

_CB = "bd"

#: Moves listed per page on the Moves view.
_MOVES_PER_PAGE = 8

#: Category menu — 4 options, blue/green, plain premium-icon labels.
CATEGORIES: list[tuple[str, str, str, str]] = [
    # (key, label, style, icon_key)
    ("atk", "Best ATK", PRIMARY, "battle"),
    ("spatk", "Best SP.ATK", SUCCESS, "bolt"),
    ("def", "Best DEF", PRIMARY, "gem"),
    ("spdef", "Best SP.DEF", SUCCESS, "heart"),
]

#: Friendly titles shown on build cards.
CAT_TITLES = {
    "atk": "Physical Sweep (ATK)",
    "spatk": "Special Sweep (SP.ATK)",
    "def": "Physical Wall (DEF)",
    "spdef": "Special Wall (SP.DEF)",
}

#: Stats prioritised per category (for ranking base stats / EV notes).
CAT_FOCUS = {
    "atk": ("attack", "speed"),
    "spatk": ("sp_atk", "speed"),
    "def": ("defense", "hp"),
    "spdef": ("sp_def", "hp"),
}

#: Damage category filter for the Moves page.
CAT_MOVE_FILTER = {
    "atk": "Physical",
    "spatk": "Special",
    "def": "Status",   # walls want utility; fall back to damaging if empty
    "spdef": "Status",
}


def _esc(s) -> str:
    return html_lib.escape(str(s if s is not None else ""), quote=True)


def dex_ready() -> bool:
    return pokemon.ready()


# ── Recommendation engine ────────────────────────────────────────────────


def _best_moves(p: dict, cat: str) -> list[dict]:
    """Top moves for a category: STAB + high power first, then utility."""
    types = {str(t).lower() for t in (p.get("types") or [])}
    want = CAT_MOVE_FILTER.get(cat, "Physical")
    rows = pokemon.all_move_rows(p)

    def _score(m: dict) -> tuple:
        power = m.get("power") or 0
        mtype = str(m.get("type") or "").lower()
        category = str(m.get("category") or "")
        stab = 1 if mtype in types else 0
        # Prefer the category we asked for; still keep strong coverage.
        cat_match = 1 if category == want else 0
        if cat in ("def", "spdef"):
            # Walls: utility/status first, then reliable damaging STAB.
            is_status = 1 if category == "Status" else 0
            return (is_status, stab, power)
        return (cat_match, stab, power)

    ranked = sorted(rows, key=_score, reverse=True)

    # For attack categories keep only damaging moves of the right class
    # when we have enough; for walls keep a mix of status + STAB.
    if cat in ("atk", "spatk"):
        damaging = [m for m in ranked
                    if (m.get("power") or 0) > 0
                    and str(m.get("category")) == want]
        if len(damaging) < 4:
            extra = [m for m in ranked
                     if (m.get("power") or 0) > 0 and m not in damaging]
            damaging.extend(extra)
        return damaging[:6]
    # Walls: status moves first, then strongest STAB / coverage.
    status = [m for m in ranked if str(m.get("category")) == "Status"]
    damaging = [m for m in ranked if (m.get("power") or 0) > 0]
    return (status[:3] + damaging[:4])[:6]


def recommend_build(p: dict, cat: str) -> dict:
    """Full recommendation bundle for one category."""
    bs = p.get("base_stats") or {}
    nature = pokemon.nature_for(cat, bs)
    plus, minus = pokemon.NATURE_TABLE.get(nature, (None, None))
    evs = pokemon.recommended_evs(cat)
    items = pokemon.held_items_for(cat)
    moves = _best_moves(p, cat)
    focus1, focus2 = CAT_FOCUS.get(cat, ("attack", "speed"))

    stat_lines = []
    for stat in pokemon.STAT_ORDER:
        base = int(bs.get(stat, 0) or 0)
        ev = int(evs.get(stat, 0) or 0)
        val = pokemon.stat_at_100(
            base, stat, ev=ev,
            nature_plus=(stat == plus),
            nature_minus=(stat == minus))
        label = pokemon.stat_abbr(stat)
        mark = ""
        if stat == plus:
            mark = " +"
        elif stat == minus:
            mark = " −"
        stat_lines.append({
            "label": label,
            "base": base,
            "ev": ev,
            "value": val,
            "mark": mark,
        })

    return {
        "cat": cat,
        "title": CAT_TITLES.get(cat, cat),
        "nature": nature,
        "plus": pokemon.stat_abbr(plus) if plus else "—",
        "minus": pokemon.stat_abbr(minus) if minus else "—",
        "evs": evs,
        "ivs": "31/31/31/31/31/31",
        "items": items,
        "moves": moves,
        "stats": stat_lines,
        "focus": (pokemon.stat_abbr(focus1), pokemon.stat_abbr(focus2)),
    }


# ── HTML builders ────────────────────────────────────────────────────────


def _ev_text(evs: dict) -> str:
    order = pokemon.STAT_ORDER
    parts = []
    for s in order:
        v = int(evs.get(s, 0) or 0)
        if v:
            parts.append(f"{v} {pokemon.stat_abbr(s)}")
    return " / ".join(parts) if parts else "0"


def _summary_html(p: dict, rec: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    dex = pokemon.dex_number(p.get("id"))
    types = p.get("types") or []
    parts = [
        f"<p>{ui_tag('star')} <b>{name}</b> {dex} · "
        f"{_esc(rec['title'])}</p>",
        f"<p>{type_line(types)}</p>",
        f"<hr/>",
        f"<p>{ui_tag('heart')} <b>Nature:</b> {_esc(rec['nature'])} "
        f"(+{_esc(rec['plus'])} / −{_esc(rec['minus'])})</p>",
        f"<p>{ui_tag('bolt')} <b>EVs:</b> {_esc(_ev_text(rec['evs']))}</p>",
        f"<p>{ui_tag('gem')} <b>IVs:</b> {_esc(rec['ivs'])}</p>",
        f"<p>{ui_tag('gift')} <b>Items:</b> "
        f"{_esc(', '.join(rec['items'][:3]))}</p>",
        f"<hr/>",
        f"<p>{ui_tag('battle')} Stats at Lv.{pokemon.MAX_LEVEL}:</p>",
    ]
    for line in rec["stats"]:
        parts.append(
            f"<p><b>{_esc(line['label'])}</b>{_esc(line['mark'])} · "
            f"base {line['base']} · EV {line['ev']} · "
            f"→ {line['value']}</p>"
        )
    return "".join(parts)


def _moves_html(p: dict, rec: dict, page: int) -> str:
    name = _esc(p.get("name", "Unknown"))
    moves = rec["moves"]
    total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = moves[page * _MOVES_PER_PAGE:(page + 1) * _MOVES_PER_PAGE]
    parts = [
        f"<p>{ui_tag('battle')} <b>{name}</b> · "
        f"{_esc(rec['title'])} moves</p>",
        f"<hr/>",
    ]
    if not chunk:
        parts.append(f"<p>{ui_tag('cross')} No moves in the local dex.</p>")
    for m in chunk:
        mtype = m.get("type") or "Normal"
        mname = _esc(m.get("name", "?"))
        power = m.get("power")
        acc = m.get("accuracy")
        category = m.get("category") or "?"
        bits = [type_tag(mtype), f"<b>{mname}</b>", str(category)]
        if power is not None:
            bits.append(f"{power} power")
        if acc is not None:
            bits.append(f"{acc}%")
        source = m.get("source")
        if source:
            bits.append(_esc(source))
        parts.append(f"<p>{' · '.join(bits)}</p>")
    if total_pages > 1:
        parts.append(
            f"<footer>Page {page + 1}/{total_pages} · "
            f"{len(moves)} moves</footer>"
        )
    return "".join(parts)


def _menu_html(p: dict) -> str:
    """Rich HTML for the menu view (sendRichMessage only — has <p>)."""
    name = _esc(p.get("name", "Unknown"))
    dex = pokemon.dex_number(p.get("id"))
    return (
        f"<p>{ui_tag('sparkle')} <b>{name}</b> {dex} — pick a build "
        f"category:</p>"
        f"<p>{ui_tag('info')} Each card shows nature, EVs, IVs, items "
        f"and the best moves for that role.</p>"
    )


def _menu_classic(p: dict) -> str:
    """Classic HTML caption for the menu view (sendPhoto / editCaption safe)."""
    name = _esc(p.get("name", "Unknown"))
    dex = pokemon.dex_number(p.get("id"))
    return (
        f"{E.SPARKLE} <b>{name}</b> {dex} — pick a build category:\n\n"
        f"Each card shows nature, EVs, IVs, items and the best moves "
        f"for that role."
    )


def _summary_classic(p: dict, rec: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    lines = [
        f"<b>{name}</b> · {_esc(rec['title'])}",
        f"Nature: {_esc(rec['nature'])} (+{_esc(rec['plus'])}/−{_esc(rec['minus'])})",
        f"EVs: {_esc(_ev_text(rec['evs']))}",
        f"IVs: {_esc(rec['ivs'])}",
        f"Items: {_esc(', '.join(rec['items'][:3]))}",
        "",
        "Stats at Lv.100:",
    ]
    for line in rec["stats"]:
        lines.append(
            f"<b>{_esc(line['label'])}</b>{_esc(line['mark'])} · "
            f"base {line['base']} · EV {line['ev']} · → {line['value']}"
        )
    return "\n".join(lines)


def _moves_classic(p: dict, rec: dict, page: int) -> str:
    name = _esc(p.get("name", "Unknown"))
    moves = rec["moves"]
    total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = moves[page * _MOVES_PER_PAGE:(page + 1) * _MOVES_PER_PAGE]
    lines = [f"<b>{name}</b> · {_esc(rec['title'])} moves", ""]
    for m in chunk:
        power = m.get("power")
        acc = m.get("accuracy")
        bits = [type_tag(m.get("type") or "Normal"),
                f"<b>{_esc(m.get('name', '?'))}</b>",
                str(m.get("category") or "?")]
        if power is not None:
            bits.append(f"{power} power")
        if acc is not None:
            bits.append(f"{acc}%")
        lines.append(" · ".join(bits))
    if total_pages > 1:
        lines.append(f"\n<i>Page {page + 1}/{total_pages}</i>")
    return "\n".join(lines)


# ── Keyboards ────────────────────────────────────────────────────────────


def _menu_rows(p: dict) -> list[list[tuple]]:
    pid = p.get("id", 0)
    rows: list[list[tuple]] = []
    for key, label, style, icon in CATEGORIES:
        rows.append([(label, f"{_CB}|{pid}|{key}|sum|0", style, icon)])
    rows.append([("Close", f"{_CB}|{pid}|menu|close|0", DANGER, "cross")])
    return rows


def _build_rows(p: dict, cat: str, view: str, page: int,
                total_pages: int) -> list[list[tuple]]:
    """Summary/moves keyboard: Moves|Stats-style nav + Back + Close."""
    pid = p.get("id", 0)
    rows: list[list[tuple]] = []

    if view == "sum":
        rows.append([
            ("Moves", f"{_CB}|{pid}|{cat}|mv|0", SUCCESS, "gift"),
            ("Back", f"{_CB}|{pid}|menu|menu|0", PRIMARY, "globe"),
        ])
    elif view == "mv":
        nav: list[tuple] = []
        if page > 0:
            nav.append(("◀ Prev",
                        f"{_CB}|{pid}|{cat}|mv|{page - 1}",
                        PRIMARY, "aim"))
        if page < total_pages - 1:
            nav.append(("Next ▶",
                        f"{_CB}|{pid}|{cat}|mv|{page + 1}",
                        SUCCESS, "rocket"))
        if nav:
            rows.append(nav)
        rows.append([
            ("Summary", f"{_CB}|{pid}|{cat}|sum|0", PRIMARY, "star"),
            ("Back", f"{_CB}|{pid}|menu|menu|0", SUCCESS, "globe"),
        ])
    rows.append([
        ("Close", f"{_CB}|{pid}|{cat}|close|0", DANGER, "cross"),
    ])
    return rows


# ── Commands ─────────────────────────────────────────────────────────────


async def cmd_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/build [pokemon] — competitive build menu (ATK / SP.ATK / DEF / SP.DEF)."""
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_html(
            f"{E.CHAT} Usage: <code>/build Garchomp</code>")
        return
    if not dex_ready():
        await update.effective_message.reply_html(
            f"{E.WARN} The local Pokédex isn't loaded yet — try again "
            f"in a moment.")
        return
    p = pokemon.get_pokemon_by_name_fuzzy(query)
    if not p:
        await update.effective_message.reply_html(
            f"{E.CROSS} I don't know a Pokémon called "
            f"<code>{_esc(query)}</code>. Try /build Garchomp.")
        return

    bot = update.get_bot()
    chat_id = update.effective_chat.id
    reply_to = (update.effective_message.message_id
                if update.effective_message else None)
    # Photo captions only accept classic HTML — never <p>/<hr>.
    caption = _menu_classic(p)
    kb = colored_kb_dict(_menu_rows(p))

    art = pokemon.artwork_url(p)
    if art:
        sent = await send_photo_url(
            bot, chat_id, art, caption,
            reply_markup=kb, reply_to=reply_to)
        if sent:
            return
        data = await fetch_image(art)
        if data:
            sent = await send_photo_bytes(
                bot, chat_id, data, f"{p.get('id', 'build')}.png", caption,
                reply_markup=kb, reply_to=reply_to)
            if sent:
                return
        LOGGER.debug("build sendPhoto failed; classic text path")

    await send_rich_step(
        bot, chat_id, _menu_html(p),
        reply_markup=kb,
        reply_to=reply_to,
        classic_markup=kb,
        classic_text=caption,
    )


async def on_build_button(update: Update,
                          context: ContextTypes.DEFAULT_TYPE) -> None:
    """/build callbacks — edit caption/markup in place (photo stays).

    Callback: ``bd|{id}|{cat}|{view}|{page}``
    """
    query = update.callback_query
    data = (query.data or "").split("|")
    try:
        pid = int(data[1])
        cat = data[2]
        view = data[3]
        page = int(data[4]) if len(data) > 4 else 0
    except (IndexError, ValueError):
        await query.answer()
        return
    await query.answer()

    if view == "close":
        try:
            await query.message.delete()
        except TelegramError:
            pass
        return

    p = pokemon.get_pokemon_data(pid)
    if not p:
        p = pokemon.get_pokemon_by_name_fuzzy(str(pid))
    if not p:
        try:
            await query.message.reply_html(
                f"{E.CROSS} That Pokémon left the local dex.")
        except TelegramError:
            pass
        return

    bot = update.get_bot()
    msg = query.message
    chat_id = msg.chat_id
    mid = msg.message_id
    is_photo = bool(msg.photo) or (msg.caption is not None)

    async def _apply(caption_html: str, classic: str, kb) -> None:
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
            if status == "fail":
                LOGGER.debug("build caption edit failed")
        else:
            status = await edit_message_html(bot, chat_id, mid, classic,
                                             reply_markup=kb)
            if status == "fail":
                try:
                    await msg.edit_text(classic, parse_mode="HTML",
                                        reply_markup=kb)
                except TelegramError:
                    LOGGER.debug("build text edit failed", exc_info=True)

    # Back to the category menu.
    if cat == "menu" or view == "menu":
        kb = colored_kb_dict(_menu_rows(p))
        await _apply(_menu_html(p),
                     _menu_classic(p),
                     kb)
        return

    if cat not in CAT_TITLES:
        await _apply(_menu_html(p),
                     f"{E.CROSS} Unknown category.",
                     colored_kb_dict(_menu_rows(p)))
        return

    rec = recommend_build(p, cat)

    if view == "mv":
        moves = rec["moves"]
        total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
        page = max(0, min(page, total_pages - 1))
        kb = colored_kb_dict(
            _build_rows(p, cat, "mv", page, total_pages))
        await _apply(_moves_html(p, rec, page),
                     _moves_classic(p, rec, page),
                     kb)
        return

    # Default / "sum" — the main build card.
    kb = colored_kb_dict(
        _build_rows(p, cat, "sum", 0, 1))
    await _apply(_summary_html(p, rec),
                 _summary_classic(p, rec),
                 kb)
