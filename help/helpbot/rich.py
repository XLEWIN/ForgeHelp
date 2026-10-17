"""Rich Message helpers (Bot API 10.1+ sendRichMessage) for the help bot.

Ported from Forge's rich transport — self-contained, no httpx, no forge
import. Every send degrades gracefully to classic HTML + keyboard.

Rich HTML dialect (core.telegram.org/bots/api#rich-html-style):
- larger text: <h1>..<h6>
- structure:   <p> <hr/> <ul>/<ol>/<li> <table> <footer> <blockquote>
- inline:      <b> <i> <u> <s> <code> <mark> <tg-spoiler> <tg-emoji>
- buttons:     <tg-button-row> / <tg-button type="callback_data|url">
  (premium <tg-emoji> works INSIDE pill labels — classic keyboards cannot)
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from typing import Any, Iterable, Optional, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .emojis import ui_glyph, ui_tag

LOGGER = logging.getLogger(__name__)

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"
LINK = "link"

#: Rows: list of rows; item = (label, data) or (label, data, style).
#: Label may already contain <tg-emoji> HTML for rich pills.
RowItem = tuple  # (label, data[, style])
Rows = Sequence[Sequence[RowItem]]


def _is_url(data: str) -> bool:
    return str(data or "").startswith(("http://", "https://"))


def _esc(text: str) -> str:
    return html_lib.escape(str(text or ""), quote=True)


# ── Rich pills + classic keyboard from the same rows ──────────────────────


def rows_to_pills(rows: Iterable[Rows]) -> str:
    """``<tg-button-row>`` HTML. Labels may contain <tg-emoji> (not escaped)."""
    parts: list[str] = []
    for row in rows:
        pills: list[str] = []
        for item in row:
            label, data = item[0], item[1]
            style = f' style="{item[2]}"' if len(item) > 2 and item[2] else ""
            # label is trusted builder HTML (ui_tag + escaped text).
            if _is_url(data):
                pills.append(
                    f'<tg-button type="url" url="{_esc(data)}"{style}>'
                    f"{label}</tg-button>"
                )
            else:
                pills.append(
                    f'<tg-button type="callback_data" data="{_esc(data)}"{style}>'
                    f"{label}</tg-button>"
                )
        parts.append(f"<tg-button-row>{''.join(pills)}</tg-button-row>")
    return "".join(parts)


def rows_to_kb(rows: Iterable[Rows],
               glyph_labels: bool = True) -> InlineKeyboardMarkup:
    """Classic fallback keyboard from the same rows.

    Strips <tg-emoji> and keeps the unicode glyph (Telegram button labels
    cannot render custom emoji).
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        line: list[InlineKeyboardButton] = []
        for item in row:
            label, data = item[0], item[1]
            plain = re.sub(r"<[^>]+>", "", label).strip()
            if _is_url(data):
                line.append(InlineKeyboardButton(plain, url=data))
            else:
                line.append(InlineKeyboardButton(plain, callback_data=data))
        buttons.append(line)
    return InlineKeyboardMarkup(buttons)


def pill_label(icon_key: str, text: str) -> str:
    """``<tg-emoji…>🎁</tg-emoji> Guides`` — premium icon + escaped text."""
    tag = ui_tag(icon_key)
    return f"{tag} {_esc(text)}" if tag else _esc(text)


def glyph_label(icon_key: str, text: str) -> str:
    """``🎁 Guides`` — plain glyph for classic buttons."""
    g = ui_glyph(icon_key)
    return f"{g} {text}" if g else text


# ── Transport ─────────────────────────────────────────────────────────────


def _markup_dict(reply_markup) -> Optional[dict]:
    if reply_markup is None:
        return None
    if hasattr(reply_markup, "to_dict"):
        return reply_markup.to_dict()
    return reply_markup


async def send_rich(bot, chat_id: int, html: str, reply_markup=None,
                    reply_to: Optional[int] = None):
    """sendRichMessage(html=…). Returns result dict / True, or None on failure."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
    }
    markup = _markup_dict(reply_markup)
    if markup:
        payload["reply_markup"] = markup
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    try:
        result = await bot._post("sendRichMessage", payload)
        return result if isinstance(result, dict) else True
    except Exception as exc:  # noqa: BLE001 — degrade, never crash
        LOGGER.debug("sendRichMessage failed (%s)", exc)
        return None


async def send_rich_step(bot, chat_id: int, rich_html: str,
                         reply_markup=None, reply_to: Optional[int] = None,
                         classic_markup=None) -> bool:
    """Send rich HTML; fall back to classic HTML + keyboard.

    ``classic_markup`` defaults to ``reply_markup``. Returns True when the
    rich message went out.
    """
    if await send_rich(bot, chat_id, rich_html, reply_markup, reply_to):
        return True
    markup = classic_markup if classic_markup is not None else reply_markup
    text = classic_html(rich_html)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    m = _markup_dict(markup)
    if m:
        payload["reply_markup"] = m
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    try:
        await bot._post("sendMessage", payload)
        return False
    except Exception:
        # Last resort: plain text.
        try:
            payload.pop("parse_mode", None)
            payload["text"] = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
            await bot._post("sendMessage", payload)
        except Exception:
            LOGGER.exception("classic sendMessage fallback failed")
        return False


def classic_html(rich: str) -> str:
    """Downgrade Rich HTML to the classic Bot API HTML subset."""
    s = rich
    s = re.sub(r"<hr\s*/?>", "━━━━━━━━━━━━", s)
    s = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", r"<b>\2</b>", s, flags=re.S)
    s = re.sub(r"<p>(.*?)</p>", r"\1\n", s, flags=re.S)
    s = re.sub(r"<li>(.*?)</li>", r"• \1\n", s, flags=re.S)
    for tag in ("ul", "ol"):
        s = s.replace(f"<{tag}>", "").replace(f"</{tag}>", "")
    # Drop pill rows: the classic keyboard carries the same buttons.
    s = re.sub(r"<tg-button-row[^>]*>.*?</tg-button-row>", "", s, flags=re.S)
    s = re.sub(r"<tg-button[^>]*>(.*?)</tg-button>", r"\1", s, flags=re.S)
    s = re.sub(r"<footer>(.*?)</footer>", r"\1\n", s, flags=re.S)
    s = re.sub(r"<mark>(.*?)</mark>", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</?(?:figure|figcaption|img|video|audio)\b[^>]*>", "", s)
    for rich_ent, classic_rep in (
        ("&nbsp;", " "), ("&hellip;", "…"), ("&mdash;", "—"),
        ("&ndash;", "–"), ("&apos;", "'"),
    ):
        s = s.replace(rich_ent, classic_rep)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
