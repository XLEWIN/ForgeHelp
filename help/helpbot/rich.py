"""Rich Message helpers (Bot API 10.1+ sendRichMessage) for the help bot.

Transport posts raw JSON straight to api.telegram.org (same approach as
Forge's utils/rich.py) — PTB's ``_post`` is not reliable for experimental
methods. Every send degrades gracefully to classic HTML + keyboard.

Rich HTML dialect (core.telegram.org/bots/api#rich-html-style):
- larger text: <h1>..<h6>
- structure:   <p> <hr/> <ul>/<ol>/<li> <table> <footer> <blockquote>
- inline:      <b> <i> <u> <s> <code> <mark> <tg-spoiler> <tg-emoji>
- buttons:     <tg-button-row> / <tg-button type="callback_data|url">
  (premium <tg-emoji> works INSIDE pill labels — classic keyboards cannot)
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Iterable, Optional, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from . import config
from .emojis import ui_glyph, ui_icon_id, ui_tag

LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"
LINK = "link"

#: Rows: list of rows; item = (label, data) or (label, data, style[, icon_key]).
#: Label may already contain <tg-emoji> HTML for rich pills.
RowItem = tuple  # (label, data[, style[, icon_key]])
Rows = Sequence[Sequence[RowItem]]


def _is_url(data: str) -> bool:
    return str(data or "").startswith(("http://", "https://"))


def _esc(text: str) -> str:
    return html_lib.escape(str(text or ""), quote=True)


# ── Colored classic inline keyboards (Bot API 10.1 style + icon) ─────────
#
# PTB 21.6's InlineKeyboardButton has no style / icon_custom_emoji_id
# fields, so we build a raw reply_markup dict and POST it ourselves.


def colored_kb_dict(rows: Iterable[Rows],
                    strip_icons: bool = False) -> dict:
    """Raw ``reply_markup`` dict with per-button ``style`` + premium icon.

    Item shape: (label, data[, style[, icon_key]]).
    Labels must be plain text (no HTML). ``icon_key`` looks up the
    premium custom-emoji id from UI_EMOJI_IDS — only those ids are
    used (never plain unicode glyphs).
    """
    board: list[list[dict]] = []
    for row in rows:
        line: list[dict] = []
        for item in row:
            label = re.sub(r"<[^>]+>", "", str(item[0] or "")).strip()
            data = str(item[1] or "")
            style = str(item[2] or "") if len(item) > 2 else ""
            icon_key = str(item[3] or "") if len(item) > 3 else ""
            btn: dict[str, Any] = {"text": label}
            if _is_url(data):
                btn["url"] = data
            else:
                btn["callback_data"] = data
            if style in (PRIMARY, SUCCESS, DANGER, LINK) and not strip_icons:
                btn["style"] = style
            if icon_key and not strip_icons:
                icon = ui_icon_id(icon_key)
                if icon:
                    btn["icon_custom_emoji_id"] = icon
            line.append(btn)
        if line:
            board.append(line)
    return {"inline_keyboard": board}


def classic_kb_dict(rows: Iterable[Rows]) -> dict:
    """Plain keyboard dict (no style / icon) — safe fallback."""
    return colored_kb_dict(rows, strip_icons=True)


def _strip_kb_markup(markup: Optional[dict]) -> Optional[dict]:
    """Drop style / icon_custom_emoji_id from a raw keyboard dict."""
    if not markup or "inline_keyboard" not in markup:
        return markup
    board: list[list[dict]] = []
    for row in markup["inline_keyboard"]:
        line: list[dict] = []
        for btn in row:
            clean = {k: v for k, v in btn.items()
                     if k not in ("style", "icon_custom_emoji_id")}
            line.append(clean)
        board.append(line)
    return {"inline_keyboard": board}


def _with_kb_fallback(payload: dict[str, Any],
                      reply_markup) -> list[dict[str, Any]]:
    """Payloads to try: colored kb first, then stripped, then bare."""
    markup = _markup_dict(reply_markup)
    variants: list[dict[str, Any]] = []
    if markup:
        with_colored = dict(payload)
        with_colored["reply_markup"] = markup
        variants.append(with_colored)
        stripped = _strip_kb_markup(markup)
        if stripped != markup:
            with_plain = dict(payload)
            with_plain["reply_markup"] = stripped
            variants.append(with_plain)
    bare = dict(payload)
    bare.pop("reply_markup", None)
    variants.append(bare)
    return variants


# ── Rich pills + classic keyboard from the same rows ──────────────────────


def rows_to_pills(rows: Iterable[Rows]) -> str:
    """``<tg-button-row>`` HTML. Labels may contain <tg-emoji> (not escaped)."""
    parts: list[str] = []
    for row in rows:
        pills: list[str] = []
        for item in row:
            label, data = item[0], item[1]
            style = f' style="{item[2]}"' if len(item) > 2 and item[2] else ""
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
    """Classic fallback keyboard from the same rows (unicode glyphs)."""
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


def _api_sync(method: str, payload: dict[str, Any]) -> tuple[bool, Any, str]:
    """POST one Bot API method as JSON. Never raises.

    Returns ``(ok, result, description)``.
    """
    url = f"{API_BASE}/bot{config.TOKEN}/{method}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        return False, None, f"HTTP {exc.code} {detail}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"
    desc = str(data.get("description") or "")
    if not data.get("ok"):
        return False, None, desc
    result = data.get("result")
    return True, (result if isinstance(result, (dict, bool)) else True), desc


async def _api(method: str, payload: dict[str, Any]) -> tuple[bool, Any, str]:
    return await asyncio.to_thread(_api_sync, method, payload)


async def send_rich(bot, chat_id: int, html: str, reply_markup=None,
                    reply_to: Optional[int] = None):
    """sendRichMessage(html=…). Returns result / True, or None on failure.

    Tries the colored keyboard first, then a stripped/plain one.
    *bot* is unused (kept for call-site compatibility) — we hit the HTTP
    API directly so experimental methods never go through PTB.
    """
    del bot  # transport is HTTP-direct
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": {"html": html},
    }
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    for attempt in _with_kb_fallback(payload, reply_markup):
        ok, result, desc = await _api("sendRichMessage", attempt)
        if ok:
            LOGGER.debug("sendRichMessage ok chat=%s", chat_id)
            return result if isinstance(result, dict) else True
        LOGGER.info("sendRichMessage rejected chat=%s: %s", chat_id, desc[:200])
    return None


async def send_rich_step(bot, chat_id: int, rich_html: str,
                         reply_markup=None, reply_to: Optional[int] = None,
                         classic_markup=None,
                         classic_text: Optional[str] = None) -> bool:
    """Send rich HTML; fall back to classic HTML + keyboard.

    ``reply_markup`` is attached to BOTH the rich send and the classic
    fallback (``classic_markup`` overrides it when provided).
    ``classic_text`` overrides the downgraded rich body for the fallback
    (optional). Returns True when the rich message went out.
    """
    if await send_rich(bot, chat_id, rich_html, reply_markup, reply_to):
        return True
    markup = classic_markup if classic_markup is not None else reply_markup
    text = classic_text if classic_text is not None else classic_html(rich_html)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    for attempt in _with_kb_fallback(payload, markup):
        ok, _res, desc = await _api("sendMessage", attempt)
        if ok:
            return False
        LOGGER.debug("classic sendMessage variant rejected: %s", desc[:200])
    LOGGER.info("classic sendMessage all variants failed chat=%s", chat_id)
    # Last resort: plain text.
    payload.pop("parse_mode", None)
    payload.pop("reply_markup", None)
    payload["text"] = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    await _api("sendMessage", payload)
    return False


async def send_photo_url(bot, chat_id: int, photo_url: str, caption: str,
                         reply_markup=None, reply_to: Optional[int] = None):
    """sendPhoto with a remote URL (Telegram fetches it — no local download).

    Tries the colored keyboard first, then a plain one, then bare.
    Returns the sent Message dict, or None on failure.
    """
    del bot
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_to:
        payload["reply_parameters"] = {"message_id": reply_to}
    last_desc = ""
    for attempt in _with_kb_fallback(payload, reply_markup):
        ok, result, desc = await _api("sendPhoto", attempt)
        if ok:
            return result if isinstance(result, dict) else True
        if "not modified" in desc.lower():
            return None
        last_desc = desc
        LOGGER.debug("sendPhoto variant rejected: %s", desc[:200])
    LOGGER.info("sendPhoto all variants failed chat=%s: %s",
                chat_id, last_desc[:200])
    return None


async def send_photo_bytes(bot, chat_id: int, data: bytes,
                           filename: str, caption: str,
                           reply_markup=None, reply_to: Optional[int] = None,
                           mime: str = "image/png"):
    """sendPhoto with local bytes (multipart). Returns Message dict / None.

    Used when Telegram cannot fetch the remote artwork URL.
    """
    del bot
    import json as _json
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_to:
        payload["reply_parameters"] = _json.dumps({"message_id": reply_to})
    markup = _markup_dict(reply_markup)
    if markup:
        payload["reply_markup"] = _json.dumps(markup, ensure_ascii=False)
    ok, result, desc = await asyncio.to_thread(
        _multipart_sync, "sendPhoto", payload,
        {"photo": (filename, data, mime)})
    if ok:
        return result if isinstance(result, dict) else True
    # Retry without reply_markup if the style keyboard was rejected.
    if markup:
        payload.pop("reply_markup", None)
        ok, result, desc = await asyncio.to_thread(
            _multipart_sync, "sendPhoto", payload,
            {"photo": (filename, data, mime)})
        if ok:
            return result if isinstance(result, dict) else True
    LOGGER.info("send_photo_bytes rejected chat=%s: %s", chat_id, desc[:200])
    return None


async def edit_caption(bot, chat_id: int, message_id: int, caption: str,
                       reply_markup=None) -> str:
    """editMessageCaption — keeps the photo, swaps only the caption.

    Tries colored keyboard, then stripped, then bare.
    Returns 'ok' | 'unchanged' | 'fail'.
    """
    del bot
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    last_desc = ""
    for attempt in _with_kb_fallback(payload, reply_markup):
        ok, _result, desc = await _api("editMessageCaption", attempt)
        if ok:
            return "ok"
        if "not modified" in desc.lower():
            return "unchanged"
        last_desc = desc
    LOGGER.info("edit_caption rejected chat=%s msg=%s: %s",
                chat_id, message_id, last_desc[:200])
    return "fail"


async def edit_markup(bot, chat_id: int, message_id: int,
                      reply_markup) -> str:
    """editMessageReplyMarkup only (caption untouched). 'ok'|'fail'."""
    del bot
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
    }
    last_desc = ""
    for attempt in _with_kb_fallback(payload, reply_markup):
        ok, _result, desc = await _api("editMessageReplyMarkup", attempt)
        if ok:
            return "ok"
        last_desc = desc
    LOGGER.info("edit_markup rejected chat=%s msg=%s: %s",
                chat_id, message_id, last_desc[:200])
    return "fail"


async def edit_message_html(bot, chat_id: int, message_id: int, text: str,
                            reply_markup=None) -> str:
    """editMessageText with HTML — for text-only (non-photo) messages.

    Tries colored keyboard, then stripped, then bare.
    Returns 'ok' | 'unchanged' | 'fail'.
    """
    del bot
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
    }
    last_desc = ""
    for attempt in _with_kb_fallback(payload, reply_markup):
        ok, _result, desc = await _api("editMessageText", attempt)
        if ok:
            return "ok"
        if "not modified" in desc.lower():
            return "unchanged"
        last_desc = desc
    LOGGER.info("edit_message_html rejected chat=%s msg=%s: %s",
                chat_id, message_id, last_desc[:200])
    return "fail"


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
        ("&ndash;", "–"), ("&apos;", "'"), ("&#39;", "'"),
    ):
        s = s.replace(rich_ent, classic_rep)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ── Rich edit + media (photo embeds) ──────────────────────────────────────


async def edit_rich(bot, chat_id: int, message_id: int, html: str,
                    reply_markup=None) -> str:
    """editMessageText(rich_message=…). Returns 'ok' | 'unchanged' | 'fail'.

    *bot* is unused — transport is HTTP-direct like send_rich.
    """
    del bot
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "rich_message": {"html": html},
    }
    markup = _markup_dict(reply_markup)
    if markup:
        payload["reply_markup"] = markup
    ok, _result, desc = await _api("editMessageText", payload)
    if ok:
        return "ok"
    if "not modified" in desc.lower():
        return "unchanged"
    LOGGER.info("edit_rich rejected chat=%s msg=%s: %s", chat_id, message_id,
                desc[:200])
    return "fail"


def _multipart_sync(method: str, data: dict[str, Any],
                    files: dict[str, tuple[str, bytes, str]],
                    timeout: float = 30.0) -> tuple[bool, Any, str]:
    """POST multipart/form-data (rich media lives inside rich_message JSON).

    Returns (ok, result, description). Never raises.
    """
    import uuid as _uuid
    boundary = f"----owhelp{_uuid.uuid4().hex}"
    body = bytearray()

    def _field(name: str, value: str) -> None:
        body.extend(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )

    for name, value in data.items():
        _field(name, value if isinstance(value, str) else str(value))
    for name, (filename, blob, mime) in files.items():
        body.extend(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        )
        body.extend(blob)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"{API_BASE}/bot{config.TOKEN}/{method}"
    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        return False, None, f"HTTP {exc.code} {detail}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"
    desc = str(payload.get("description") or "")
    if not payload.get("ok"):
        return False, None, desc
    result = payload.get("result")
    return True, (result if isinstance(result, (dict, bool)) else True), desc


def _media_parts(media: list[dict[str, Any]]):
    """Build rich_message media items + multipart file map from media dicts.

    Each media item: {"id", "filename", "data", "mime", "type"|"photo"}.
    """
    import json as _json
    items = []
    files: dict[str, tuple[str, bytes, str]] = {}
    for m in media:
        mid = m["id"]
        items.append({
            "id": mid,
            "media": {"type": m.get("type", "photo"),
                      "media": f"attach://{mid}"},
        })
        files[mid] = (
            m.get("filename", f"{mid}.png"),
            m["data"],
            m.get("mime", "image/png"),
        )
    return items, files


async def send_rich_media(bot, chat_id: int, html: str,
                          media: list[dict[str, Any]],
                          reply_markup=None,
                          reply_to: Optional[int] = None):
    """sendRichMessage with attach:// media (multipart). Returns Message / None.

    media items: {"id", "filename", "data", "mime", "type"}. HTML must
    reference each as ``tg://photo?id=<id>`` (or tg://video etc.).
    """
    del bot
    import json as _json
    items, files = _media_parts(media)
    rich = {"html": html, "media": items}
    data: dict[str, Any] = {
        "chat_id": str(chat_id),
        "rich_message": _json.dumps(rich, ensure_ascii=False),
    }
    markup = _markup_dict(reply_markup)
    if markup:
        data["reply_markup"] = _json.dumps(markup, ensure_ascii=False)
    if reply_to:
        data["reply_parameters"] = _json.dumps({"message_id": reply_to})
    ok, result, desc = await asyncio.to_thread(
        _multipart_sync, "sendRichMessage", data, files)
    if ok:
        return result if isinstance(result, dict) else True
    LOGGER.info("send_rich_media rejected chat=%s: %s", chat_id, desc[:200])
    return None


async def edit_rich_media(bot, chat_id: int, message_id: int, html: str,
                          media: list[dict[str, Any]],
                          reply_markup=None) -> str:
    """editMessageText with rich_message + attach:// media. 'ok'|'unchanged'|'fail'."""
    del bot
    import json as _json
    items, files = _media_parts(media)
    rich = {"html": html, "media": items}
    data: dict[str, Any] = {
        "chat_id": str(chat_id),
        "message_id": str(message_id),
        "rich_message": _json.dumps(rich, ensure_ascii=False),
    }
    markup = _markup_dict(reply_markup)
    if markup:
        data["reply_markup"] = _json.dumps(markup, ensure_ascii=False)
    ok, _result, desc = await asyncio.to_thread(
        _multipart_sync, "editMessageText", data, files)
    if ok:
        return "ok"
    if "not modified" in desc.lower():
        return "unchanged"
    LOGGER.info("edit_rich_media rejected chat=%s msg=%s: %s",
                chat_id, message_id, desc[:200])
    return "fail"


def fetch_image_sync(url: str, timeout: float = 20.0) -> Optional[bytes]:
    """Download image bytes for rich-media attach://. Returns None on failure."""
    if not url:
        return None
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 — degrade, never crash a handler
        LOGGER.info("fetch_image failed %s: %s", url[:80], exc)
        return None


async def fetch_image(url: str) -> Optional[bytes]:
    return await asyncio.to_thread(fetch_image_sync, url)
