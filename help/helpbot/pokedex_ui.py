"""Pokedex UI for /mv and /poke — rich messages + styled pill buttons.

Colour scheme (rich pills only — classic keyboards cannot carry styles):
  primary  (blue)  — IVs, Level-Up, Prev, Back
  success  (green) — Moves, Tutor, TMs, Next
  danger   (red)   — Close only

Callback data: ``pk|{id}|{view}|{page}`` (view: main|ivs|mv|levelup|tutor|tms|egg).
Pagination is stateless like Forge's /data — every callback carries the
full key; the current view's own button is hidden (edit-in-place).
"""

from __future__ import annotations

import html as html_lib
import logging
import math
from typing import Optional

from telegram import InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import pokemon
from .emojis import E, type_label, type_line, type_tag, ui_tag
from .rich import (DANGER, PRIMARY, SUCCESS, classic_html, edit_rich,
                   fetch_image, pill_label, rows_to_kb, rows_to_pills,
                   send_rich, send_rich_media, send_rich_step)

LOGGER = logging.getLogger(__name__)

#: Callback prefix — keep short (Telegram limit is 64 bytes).
_CB = "pk"

#: Moves per page on /poke sub-lists.
_MOVES_PER_PAGE = 10

#: Moves per page on /mv (flat list).
_MV_PER_PAGE = 12


def _esc(s) -> str:
    return html_lib.escape(str(s if s is not None else ""), quote=True)


def dex_ready() -> bool:
    return pokemon.ready()


# ── /mv — all moves, flat, paginated, prev/next only ──────────────────────


def _mv_page_html(p: dict, page: int) -> str:
    """One /mv page: header + move lines (type emoji + name + stats)."""
    name = _esc(p.get("name", "Unknown"))
    types = p.get("types") or []
    rows = pokemon.all_move_rows(p)
    total_pages = max(1, math.ceil(len(rows) / _MV_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    start = page * _MV_PER_PAGE
    chunk = rows[start:start + _MV_PER_PAGE]

    parts = [
        f"<p>{ui_tag('battle')} <b>{name}</b> · {type_line(types)}</p>",
        f"<hr/>",
    ]
    for m in chunk:
        power = m["power"] if m["power"] is not None else "—"
        acc = f"{m['accuracy']}%" if m["accuracy"] is not None else "—"
        parts.append(
            f"<p>{type_tag(m['type'])} <b>{_esc(m['name'])}</b> "
            f"· {_esc(power)} · {_esc(acc)} · {_esc(m['source'])}</p>"
        )
    if not chunk:
        parts.append(f"<p>{ui_tag('cross')} No moves in the local dex.</p>")
    if total_pages > 1:
        parts.append(
            f"<footer>Page {page + 1}/{total_pages} · "
            f"{len(rows)} moves</footer>"
        )
    return "".join(parts)


def _mv_rows(p: dict, page: int, total_pages: int) -> list[list[tuple]]:
    """Only Prev (blue) / Next (green) pills — data carries the dex id."""
    pid = p.get("id", 0)
    rows: list[list[tuple]] = []
    nav: list[tuple] = []
    if page > 0:
        nav.append(("◀ Prev", f"{_CB}|{pid}|mvpage|{page - 1}", PRIMARY))
    if page < total_pages - 1:
        nav.append(("Next ▶", f"{_CB}|{pid}|mvpage|{page + 1}", SUCCESS))
    if nav:
        rows.append(nav)
    return rows


def _mv_classic_text(p: dict, page: int) -> str:
    """Plain-HTML fallback body for /mv."""
    name = _esc(p.get("name", "Unknown"))
    types = p.get("types") or []
    rows = pokemon.all_move_rows(p)
    total_pages = max(1, math.ceil(len(rows) / _MV_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = rows[page * _MV_PER_PAGE:(page + 1) * _MV_PER_PAGE]
    lines = [f"<b>{name}</b> · {type_line(types)}", ""]
    for m in chunk:
        power = m["power"] if m["power"] is not None else "—"
        acc = f"{m['accuracy']}%" if m["accuracy"] is not None else "—"
        lines.append(
            f"{type_tag(m['type'])} <b>{_esc(m['name'])}</b> "
            f"· {power} · {acc} · {_esc(m['source'])}"
        )
    if total_pages > 1:
        lines.append(f"\n<i>Page {page + 1}/{total_pages}</i>")
    return "\n".join(lines)


async def cmd_mv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mv [pokemon] — all moves with type, power, accuracy, source."""
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_html(
            f"{E.CHAT} Usage: <code>/mv Garchomp</code>")
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
            f"<code>{_esc(query)}</code>. Try /mv Pikachu.")
        return

    total = len(pokemon.all_move_rows(p))
    total_pages = max(1, math.ceil(total / _MV_PER_PAGE))
    bot = update.get_bot()
    chat_id = update.effective_chat.id
    reply_to = (update.effective_message.message_id
                if update.effective_message else None)
    rich = _mv_page_html(p, 0)
    classic = _mv_classic_text(p, 0)
    kb = rows_to_kb(_mv_rows(p, 0, total_pages)) if total_pages > 1 else None
    await send_rich_step(
        bot, chat_id, rich,
        reply_markup=None,
        reply_to=reply_to,
        classic_markup=kb,
        classic_text=classic,
    )


# ── /poke — photo + name/types/max level + sub-pages ──────────────────────


def _poke_main_html(p: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    types = p.get("types") or []
    dex = pokemon.dex_number(p.get("id"))
    legendary = bool(p.get("is_legendary"))
    mythical = bool(p.get("is_mythical"))
    tag_bits = []
    if legendary:
        tag_bits.append(ui_tag("crown") + " Legendary")
    if mythical:
        tag_bits.append(ui_tag("sparkle") + " Mythical")
    tags = (" · " + " · ".join(tag_bits)) if tag_bits else ""
    return (
        f"<p>{ui_tag('star')} <b>{name}</b> {dex}{tags}</p>"
        f"<p>{type_line(types)}</p>"
        f"<p>{ui_tag('level')} Max Level: {pokemon.MAX_LEVEL}</p>"
        f"<p>{ui_tag('info')} Tap a button below — IVs, moves, "
        f"and more.</p>"
    )


def _poke_ivs_html(p: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    base_stats = p.get("base_stats") or {}
    parts = [
        f"<p>{ui_tag('gem')} <b>{name}</b> · Max IVs "
        f"(Lv.{pokemon.MAX_LEVEL})</p>",
        f"<hr/>",
    ]
    for stat in pokemon.STAT_ORDER:
        base = int(base_stats.get(stat, 0) or 0)
        label = pokemon.stat_abbr(stat)
        maxv = base * 2 + 31 + 63 + pokemon.MAX_LEVEL
        parts.append(
            f"<p><b>{label}</b> · base {base} · max {maxv}</p>"
        )
    parts.append(f"<p>{ui_tag('bolt')} Stat range at Lv.50:</p>")
    for stat in pokemon.STAT_ORDER:
        base = int(base_stats.get(stat, 0) or 0)
        lo, hi = pokemon.calculate_stat_range(base, stat)
        parts.append(
            f"<p><b>{pokemon.stat_abbr(stat)}</b> · {lo} – {hi}</p>"
        )
    natures = ", ".join(pokemon.best_natures(base_stats))
    evs = pokemon.ev_yield_display(p.get("ev_yields") or {})
    catch = p.get("catch_rate", "—")
    gender = pokemon.gender_display(p.get("gender_rate"))
    parts.append(f"<p>{ui_tag('heart')} Best natures: {natures}</p>")
    parts.append(f"<p>{ui_tag('bolt')} EV yield: {evs}</p>")
    parts.append(f"<p>{ui_tag('circle')} Catch rate: {catch}</p>")
    parts.append(f"<p>{ui_tag('user')} Gender: {gender}</p>")
    return "".join(parts)


def _move_list_html(p: dict, category: str, page: int) -> str:
    name = _esc(p.get("name", "Unknown"))
    moves = pokemon.moves_for(p, category)
    title = pokemon.CATEGORY_TITLES.get(category, category)
    total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = moves[page * _MOVES_PER_PAGE:(page + 1) * _MOVES_PER_PAGE]
    parts = [
        f"<p>{ui_tag('battle')} <b>{name}</b> · {title}</p>",
        f"<hr/>",
    ]
    if not chunk:
        parts.append(f"<p>{ui_tag('cross')} No {title.lower()} in the "
                     f"local dex.</p>")
    for m in chunk:
        mtype = m.get("type") or "Normal"
        mname = _esc(m.get("name", "?"))
        power = m.get("power")
        acc = m.get("accuracy")
        level = m.get("level")
        bits = [type_tag(mtype), f"<b>{mname}</b>"]
        if power is not None:
            bits.append(f"{power} power")
        if acc is not None:
            bits.append(f"{acc}%")
        if category == "levelup" and level:
            bits.append(f"Lv.{level}")
        parts.append(f"<p>{' · '.join(bits)}</p>")
    if total_pages > 1:
        parts.append(
            f"<footer>Page {page + 1}/{total_pages} · "
            f"{len(moves)} moves</footer>"
        )
    return "".join(parts)


def _move_list_classic(p: dict, category: str, page: int) -> str:
    name = _esc(p.get("name", "Unknown"))
    moves = pokemon.moves_for(p, category)
    title = pokemon.CATEGORY_TITLES.get(category, category)
    total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
    page = max(0, min(page, total_pages - 1))
    chunk = moves[page * _MOVES_PER_PAGE:(page + 1) * _MOVES_PER_PAGE]
    lines = [f"<b>{name}</b> · {title}", ""]
    for m in chunk:
        mtype = m.get("type") or "Normal"
        mname = _esc(m.get("name", "?"))
        power = m.get("power")
        acc = m.get("accuracy")
        level = m.get("level")
        bits = [type_tag(mtype), f"<b>{mname}</b>"]
        if power is not None:
            bits.append(f"{power} power")
        if acc is not None:
            bits.append(f"{acc}%")
        if category == "levelup" and level:
            bits.append(f"Lv.{level}")
        lines.append(" · ".join(bits))
    if total_pages > 1:
        lines.append(f"\n<i>Page {page + 1}/{total_pages}</i>")
    return "\n".join(lines)


def _cb_view(data: str) -> str:
    parts = str(data or "").split("|")
    return parts[2] if len(parts) > 2 else ""


def _poke_rows(p: dict, hide: str = "") -> list[list[tuple]]:
    """Main pills minus the current view. blue/green contrast, red Close."""
    pid = p.get("id", 0)
    has_tutor = bool(p.get("tutor_moves"))
    has_egg = bool(p.get("egg_moves"))
    rows: list[list[tuple]] = [
        [
            (pill_label("gem", "IVs"), f"{_CB}|{pid}|ivs|0", PRIMARY),
            (pill_label("gift", "Moves"), f"{_CB}|{pid}|mvmenu|0", SUCCESS),
        ],
        [
            (pill_label("fire", "Level-Up"), f"{_CB}|{pid}|levelup|0", PRIMARY),
            (pill_label("star", "TMs"), f"{_CB}|{pid}|tms|0", SUCCESS),
        ],
    ]
    if has_tutor or has_egg:
        row: list[tuple] = []
        if has_tutor:
            row.append((pill_label("crown", "Tutor"),
                        f"{_CB}|{pid}|tutor|0", PRIMARY))
        if has_egg:
            row.append((pill_label("heart", "Egg"),
                        f"{_CB}|{pid}|egg|0", SUCCESS))
        rows.append(row)
    rows.append([(pill_label("cross", "Close"), f"{_CB}|{pid}|close|0",
                  DANGER)])
    if hide:
        rows = [r for r in (
            [b for b in row if _cb_view(b[1]) != hide]
            for row in rows
        ) if r]
    return rows


def _poke_classic_kb(p: dict, hide: str = "") -> InlineKeyboardMarkup:
    """Classic fallback keyboard — plain labels (no styles)."""
    pid = p.get("id", 0)
    rows: list[list[tuple]] = [
        [("IVs", f"{_CB}|{pid}|ivs|0"), ("Moves", f"{_CB}|{pid}|mvmenu|0")],
        [("Level-Up", f"{_CB}|{pid}|levelup|0"),
         ("TMs", f"{_CB}|{pid}|tms|0")],
    ]
    if p.get("tutor_moves") or p.get("egg_moves"):
        row = []
        if p.get("tutor_moves"):
            row.append(("Tutor", f"{_CB}|{pid}|tutor|0"))
        if p.get("egg_moves"):
            row.append(("Egg", f"{_CB}|{pid}|egg|0"))
        rows.append(row)
    rows.append([("Close", f"{_CB}|{pid}|close|0")])
    if hide:
        # hide "mv" also hides "mvmenu" (the Moves button).
        rows = [r for r in (
            [b for b in row
             if _cb_view(b[1]) != hide
             and not (hide == "mv" and _cb_view(b[1]) == "mvmenu")]
            for row in rows
        ) if r]
    return rows_to_kb(rows)


def _back_row(p: dict) -> list[tuple]:
    return [(pill_label("globe", "Back"), f"{_CB}|{p.get('id', 0)}|main|0",
             PRIMARY)]


def _sub_rows(p: dict, hide: str, page: int = 0, category: str = ""):
    """Sub-page: main pills (minus current) + optional nav + Back."""
    rows = _poke_rows(p, hide=hide)
    if category:
        moves = pokemon.moves_for(p, category)
        total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
        nav: list[tuple] = []
        if page > 0:
            nav.append(("◀ Prev",
                        f"{_CB}|{p.get('id', 0)}|{category}|{page - 1}",
                        PRIMARY))
        if page < total_pages - 1:
            nav.append(("Next ▶",
                        f"{_CB}|{p.get('id', 0)}|{category}|{page + 1}",
                        SUCCESS))
        if nav:
            rows = [nav] + rows
    rows.append(_back_row(p))
    return rows


async def cmd_poke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/poke [pokemon] — photo + types + max level + interactive pages."""
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_html(
            f"{E.CHAT} Usage: <code>/poke Garchomp</code>")
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
            f"<code>{_esc(query)}</code>. Try /poke Pikachu.")
        return

    bot = update.get_bot()
    chat_id = update.effective_chat.id
    reply_to = (update.effective_message.message_id
                if update.effective_message else None)
    rich = _poke_main_html(p)
    classic = (
        f"{E.STAR} <b>{_esc(p.get('name', 'Unknown'))}</b> "
        f"{pokemon.dex_number(p.get('id'))}\n"
        f"{type_line(p.get('types') or [])}\n"
        f"Max Level: {pokemon.MAX_LEVEL}"
    )
    kb = _poke_classic_kb(p)

    # Rich media path: embed official artwork via attach://.
    art = pokemon.artwork_url(p)
    if art:
        data = await fetch_image(art)
        if data:
            media = [{
                "id": "poke",
                "filename": f"{p.get('id', 'poke')}.png",
                "data": data,
                "mime": "image/png",
                "type": "photo",
            }]
            body = (
                f'<p><img src="tg://photo?id=poke"/></p>'
                + rich
                + rows_to_pills(_poke_rows(p))
            )
            sent = await send_rich_media(
                bot, chat_id, body, media,
                reply_markup=None, reply_to=reply_to)
            if sent:
                return
            LOGGER.debug("send_rich_media failed; classic photo path")

    # Classic path: send_photo with caption + keyboard.
    try:
        if art:
            await update.effective_message.reply_photo(
                photo=art, caption=classic, parse_mode="HTML",
                reply_markup=kb)
            return
    except TelegramError:
        LOGGER.debug("reply_photo failed; falling back to text", exc_info=True)
    await send_rich_step(
        bot, chat_id, rich,
        reply_markup=None,
        reply_to=reply_to,
        classic_markup=kb,
        classic_text=classic,
    )


async def on_poke_button(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """/poke + /mv inline callbacks — edit-in-place like Forge's /data.

    Callback data: ``pk|{id}|{view}|{page}``.
      view: main | ivs | mvmenu | levelup | tutor | tms | egg | mvpage | close
    """
    query = update.callback_query
    data = (query.data or "").split("|")
    # pk|{id}|{view}|{page}
    try:
        pid = int(data[1])
        view = data[2]
        page = int(data[3]) if len(data) > 3 else 0
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

    if view == "mvpage":
        # /mv pagination — same flat list, new page.
        total = len(pokemon.all_move_rows(p))
        total_pages = max(1, math.ceil(total / _MV_PER_PAGE))
        page = max(0, min(page, total_pages - 1))
        body = _mv_page_html(p, page)
        classic = _mv_classic_text(p, page)
        kb = (rows_to_kb(_mv_rows(p, page, total_pages))
              if total_pages > 1 else None)
        status = await edit_rich(bot, chat_id, mid, body, reply_markup=kb)
        if status != "ok":
            try:
                await msg.edit_text(
                    classic_html(body), parse_mode="HTML", reply_markup=kb)
            except TelegramError:
                LOGGER.debug("mv page edit failed", exc_info=True)
        return

    if view == "main":
        body = _poke_main_html(p) + rows_to_pills(_poke_rows(p))
        status = await edit_rich(bot, chat_id, mid, body,
                                 reply_markup=_poke_classic_kb(p))
        if status != "ok":
            try:
                await msg.edit_text(
                    _poke_main_classic(p),
                    parse_mode="HTML",
                    reply_markup=_poke_classic_kb(p))
            except TelegramError:
                LOGGER.debug("poke main edit failed", exc_info=True)
        return

    if view == "ivs":
        body = _poke_ivs_html(p) + rows_to_pills(_sub_rows(p, hide="ivs"))
        status = await edit_rich(bot, chat_id, mid, body,
                                 reply_markup=_poke_classic_kb(p, hide="ivs"))
        if status != "ok":
            try:
                await msg.edit_text(
                    _poke_ivs_classic(p),
                    parse_mode="HTML",
                    reply_markup=_poke_classic_kb(p, hide="ivs"))
            except TelegramError:
                LOGGER.debug("poke ivs edit failed", exc_info=True)
        return

    if view == "mvmenu":
        body = (
            f"<p>{ui_tag('chat')} <b>{_esc(p.get('name'))}</b> — pick a "
            f"move list:</p>"
            + rows_to_pills([
                [(pill_label("fire", "Level-Up"),
                  f"{_CB}|{pid}|levelup|0", PRIMARY),
                 (pill_label("star", "TMs"),
                  f"{_CB}|{pid}|tms|0", SUCCESS)],
                [(pill_label("crown", "Tutor"),
                  f"{_CB}|{pid}|tutor|0", PRIMARY),
                 (pill_label("heart", "Egg"),
                  f"{_CB}|{pid}|egg|0", SUCCESS)],
                _back_row(p),
            ])
        )
        status = await edit_rich(bot, chat_id, mid, body,
                                 reply_markup=_poke_classic_kb(p, hide="mv"))
        if status != "ok":
            try:
                await msg.edit_text(
                    f"{E.CHAT} <b>{_esc(p.get('name'))}</b> — pick a "
                    f"move list: Level-Up, TMs, Tutor, Egg.",
                    parse_mode="HTML",
                    reply_markup=_poke_classic_kb(p, hide="mv"))
            except TelegramError:
                pass
        return

    if view in ("levelup", "tutor", "tms", "egg"):
        body = (
            _move_list_html(p, view, page)
            + rows_to_pills(_sub_rows(p, hide=view, page=page,
                                      category=view))
        )
        kb = _poke_classic_kb(p, hide=view)
        status = await edit_rich(bot, chat_id, mid, body, reply_markup=kb)
        if status != "ok":
            try:
                await msg.edit_text(
                    _move_list_classic(p, view, page),
                    parse_mode="HTML",
                    reply_markup=kb)
            except TelegramError:
                LOGGER.debug("poke %s edit failed", view, exc_info=True)
        return


def _poke_main_classic(p: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    tags = []
    if p.get("is_legendary"):
        tags.append("Legendary")
    if p.get("is_mythical"):
        tags.append("Mythical")
    tag_str = (" · " + " · ".join(tags)) if tags else ""
    return (
        f"<b>{name}</b> {pokemon.dex_number(p.get('id'))}{tag_str}\n"
        f"{type_line(p.get('types') or [])}\n"
        f"Max Level: {pokemon.MAX_LEVEL}\n\n"
        f"Tap a button below — IVs, moves, and more."
    )


def _poke_ivs_classic(p: dict) -> str:
    name = _esc(p.get("name", "Unknown"))
    base_stats = p.get("base_stats") or {}
    lines = [f"<b>{name}</b> · Max IVs (Lv.{pokemon.MAX_LEVEL})", ""]
    for stat in pokemon.STAT_ORDER:
        base = int(base_stats.get(stat, 0) or 0)
        maxv = base * 2 + 31 + 63 + pokemon.MAX_LEVEL
        lines.append(f"<b>{pokemon.stat_abbr(stat)}</b> · base {base} · "
                     f"max {maxv}")
    lines.append("")
    lines.append("Stat range at Lv.50:")
    for stat in pokemon.STAT_ORDER:
        base = int(base_stats.get(stat, 0) or 0)
        lo, hi = pokemon.calculate_stat_range(base, stat)
        lines.append(f"<b>{pokemon.stat_abbr(stat)}</b> · {lo} – {hi}")
    lines.append("")
    lines.append(f"Best natures: {', '.join(pokemon.best_natures(base_stats))}")
    lines.append(f"EV yield: {pokemon.ev_yield_display(p.get('ev_yields') or {})}")
    lines.append(f"Catch rate: {p.get('catch_rate', '—')}")
    lines.append(f"Gender: {pokemon.gender_display(p.get('gender_rate'))}")
    return "\n".join(lines)
