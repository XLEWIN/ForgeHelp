"""Pokedex UI for /mv and /poke — rich messages + colored inline buttons.

Colour scheme (Bot API 10.1 button styles + premium icon_custom_emoji_id):
  primary  (blue)  — IVs, Level-Up, Prev, Back
  success  (green) — Moves, Tutor, TMs, Next
  danger   (red)   — Close only

Callback data: ``pk|{id}|{view}|{page}``
  (view: main|ivs|mvmenu|levelup|tutor|tms|egg|mvpage|close).
Pagination is stateless like Forge's /data — every callback carries the
full key; the current view's own button is hidden (edit-in-place).

/poke uses sendPhoto by URL (Telegram fetches the art — no local download)
and edits only the caption + markup so the photo stays put and every
callback is fast.
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
    """Only Prev (blue) / Next (green) buttons — data carries the dex id."""
    pid = p.get("id", 0)
    rows: list[list[tuple]] = []
    nav: list[tuple] = []
    if page > 0:
        nav.append(("◀ Prev", f"{_CB}|{pid}|mvpage|{page - 1}",
                    PRIMARY, "aim"))
    if page < total_pages - 1:
        nav.append(("Next ▶", f"{_CB}|{pid}|mvpage|{page + 1}",
                    SUCCESS, "rocket"))
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
    # Colored prev/next keyboard — attached to BOTH the rich send and
    # the classic fallback so buttons always show up.
    kb = (colored_kb_dict(_mv_rows(p, 0, total_pages))
          if total_pages > 1 else None)
    await send_rich_step(
        bot, chat_id, rich,
        reply_markup=kb,
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
    """Main buttons minus the current view. blue/green, red Close.

    Item shape: (label, callback, style, icon_key).
    """
    pid = p.get("id", 0)
    has_tutor = bool(p.get("tutor_moves"))
    has_egg = bool(p.get("egg_moves"))
    rows: list[list[tuple]] = [
        [
            ("IVs", f"{_CB}|{pid}|ivs|0", PRIMARY, "gem"),
            ("Moves", f"{_CB}|{pid}|mvmenu|0", SUCCESS, "gift"),
        ],
        [
            ("Level-Up", f"{_CB}|{pid}|levelup|0", PRIMARY, "fire"),
            ("TMs", f"{_CB}|{pid}|tms|0", SUCCESS, "star"),
        ],
    ]
    if has_tutor or has_egg:
        row: list[tuple] = []
        if has_tutor:
            row.append(("Tutor", f"{_CB}|{pid}|tutor|0", PRIMARY, "crown"))
        if has_egg:
            row.append(("Egg", f"{_CB}|{pid}|egg|0", SUCCESS, "heart"))
        rows.append(row)
    rows.append([("Close", f"{_CB}|{pid}|close|0", DANGER, "cross")])
    if hide:
        rows = [r for r in (
            [b for b in row if _cb_view(b[1]) != hide]
            for row in rows
        ) if r]
    return rows


def _back_row(p: dict) -> list[tuple]:
    return [("Back", f"{_CB}|{p.get('id', 0)}|main|0", PRIMARY, "globe")]


def _sub_rows(p: dict, hide: str, page: int = 0, category: str = ""):
    """Sub-page: main buttons (minus current) + optional nav + Back."""
    rows = _poke_rows(p, hide=hide)
    if category:
        moves = pokemon.moves_for(p, category)
        total_pages = max(1, math.ceil(len(moves) / _MOVES_PER_PAGE))
        nav: list[tuple] = []
        if page > 0:
            nav.append(("◀ Prev",
                        f"{_CB}|{p.get('id', 0)}|{category}|{page - 1}",
                        PRIMARY, "aim"))
        if page < total_pages - 1:
            nav.append(("Next ▶",
                        f"{_CB}|{p.get('id', 0)}|{category}|{page + 1}",
                        SUCCESS, "rocket"))
        if nav:
            rows = [nav] + rows
    rows.append(_back_row(p))
    return rows


def _poke_caption(p: dict, view: str = "main", page: int = 0) -> str:
    """Caption/body HTML for a given view (no buttons in the body)."""
    if view == "main":
        return _poke_main_html(p)
    if view == "ivs":
        return _poke_ivs_html(p)
    if view == "mvmenu":
        return (f"<p>{ui_tag('chat')} <b>{_esc(p.get('name'))}</b> — pick "
                f"a move list:</p>")
    if view in ("levelup", "tutor", "tms", "egg"):
        return _move_list_html(p, view, page)
    return _poke_main_html(p)


def _poke_classic_caption(p: dict, view: str = "main", page: int = 0) -> str:
    if view == "main":
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
    if view == "ivs":
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
        lines.append(
            f"Best natures: {', '.join(pokemon.best_natures(base_stats))}")
        lines.append(
            f"EV yield: {pokemon.ev_yield_display(p.get('ev_yields') or {})}")
        lines.append(f"Catch rate: {p.get('catch_rate', '—')}")
        lines.append(f"Gender: {pokemon.gender_display(p.get('gender_rate'))}")
        return "\n".join(lines)
    if view == "mvmenu":
        return (f"{E.CHAT} <b>{_esc(p.get('name'))}</b> — pick a "
                f"move list: Level-Up, TMs, Tutor, Egg.")
    if view in ("levelup", "tutor", "tms", "egg"):
        return _move_list_classic(p, view, page)
    return _poke_classic_caption(p, "main", page)


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
    # Captions only accept the classic HTML subset — never <p>/<hr>.
    caption = _poke_classic_caption(p, "main")
    kb = colored_kb_dict(_poke_rows(p))

    # 1) sendPhoto by URL (Telegram fetches; zero local work).
    art = pokemon.artwork_url(p)
    if art:
        sent = await send_photo_url(
            bot, chat_id, art, caption,
            reply_markup=kb, reply_to=reply_to)
        if sent:
            return
        # 2) Download once and multipart-upload — covers blocked URLs.
        data = await fetch_image(art)
        if data:
            sent = await send_photo_bytes(
                bot, chat_id, data, f"{p.get('id', 'poke')}.png", caption,
                reply_markup=kb, reply_to=reply_to)
            if sent:
                return
        LOGGER.debug("sendPhoto path failed; classic text fallback")

    # 3) Text-only fallback (rich if the server accepts it).
    await send_rich_step(
        bot, chat_id, _poke_main_html(p),
        reply_markup=kb,
        reply_to=reply_to,
        classic_markup=kb,
        classic_text=caption,
    )


async def on_poke_button(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    """/poke + /mv inline callbacks — edit-in-place like Forge's /data.

    Callback data: ``pk|{id}|{view}|{page}``.
      view: main | ivs | mvmenu | levelup | tutor | tms | egg | mvpage | close

    If the original message has a photo, only the caption + markup are
    edited so the picture stays put.
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
    is_photo = bool(msg.photo) or (msg.caption is not None)

    # Classic edits only — Bot API editMessageText rejects <p>/<hr>/etc.
    async def _edit_text(body_rich: str, body_classic: str, kb) -> None:
        """Edit a text message with classic HTML + keyboard."""
        text = body_classic or classic_html(body_rich)
        status = await edit_message_html(bot, chat_id, mid, text,
                                         reply_markup=kb)
        if status == "fail":
            try:
                await msg.edit_text(text, parse_mode="HTML",
                                    reply_markup=kb)
            except TelegramError:
                LOGGER.debug("text edit failed", exc_info=True)

    if view == "mvpage":
        # /mv pagination — same flat list, new page.
        total = len(pokemon.all_move_rows(p))
        total_pages = max(1, math.ceil(total / _MV_PER_PAGE))
        page = max(0, min(page, total_pages - 1))
        body = _mv_page_html(p, page)
        classic = _mv_classic_text(p, page)
        kb = (colored_kb_dict(_mv_rows(p, page, total_pages))
              if total_pages > 1 else None)
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
            if status == "fail":
                LOGGER.debug("mv page caption edit failed")
        else:
            await _edit_text(body, classic, kb)
        return

    if view == "main":
        body = _poke_caption(p, "main")
        classic = _poke_classic_caption(p, "main")
        kb = colored_kb_dict(_poke_rows(p))
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
            if status == "fail":
                LOGGER.debug("poke main caption edit failed")
        else:
            await _edit_text(body, classic, kb)
        return

    if view == "ivs":
        body = _poke_caption(p, "ivs")
        classic = _poke_classic_caption(p, "ivs")
        kb = colored_kb_dict(_sub_rows(p, hide="ivs"))
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
            if status == "fail":
                LOGGER.debug("poke ivs caption edit failed")
        else:
            await _edit_text(body, classic, kb)
        return

    if view == "mvmenu":
        classic = _poke_classic_caption(p, "mvmenu")
        # Menu hides "mvmenu" itself and shows all four list buttons + Back.
        rows = [
            [
                ("Level-Up", f"{_CB}|{pid}|levelup|0", PRIMARY, "fire"),
                ("TMs", f"{_CB}|{pid}|tms|0", SUCCESS, "star"),
            ],
            [
                ("Tutor", f"{_CB}|{pid}|tutor|0", PRIMARY, "crown"),
                ("Egg", f"{_CB}|{pid}|egg|0", SUCCESS, "heart"),
            ],
            _back_row(p),
        ]
        kb = colored_kb_dict(rows)
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
        else:
            await _edit_text(_poke_caption(p, "mvmenu"), classic, kb)
        return

    if view in ("levelup", "tutor", "tms", "egg"):
        body = _move_list_html(p, view, page)
        classic = _move_list_classic(p, view, page)
        kb = colored_kb_dict(_sub_rows(p, hide=view, page=page,
                                       category=view))
        if is_photo:
            status = await edit_caption(bot, chat_id, mid, classic,
                                        reply_markup=kb)
            if status == "fail":
                LOGGER.debug("poke %s caption edit failed", view)
        else:
            await _edit_text(body, classic, kb)
        return
