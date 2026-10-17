"""Premium (custom) Telegram emoji helpers for the Forge help bot.

Self-contained port of Forge's emoji registry — read for IDs only, never
imported from the main bot. Display format (HTML parse mode ONLY):

    <tg-emoji emoji-id="CUSTOM_EMOJI_ID">fallback</tg-emoji>

Button labels and plain-text paths must keep the unicode fallback;
Telegram cannot render custom emoji inside inline-keyboard labels.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# ── Core formatter ────────────────────────────────────────────────────────


def custom_emoji(emoji_char: str, custom_emoji_id: str) -> str:
    """Format a custom emoji as Telegram HTML (or the plain char if no id)."""
    if not custom_emoji_id:
        return emoji_char
    return f'<tg-emoji emoji-id="{custom_emoji_id}">{emoji_char}</tg-emoji>'


def strip_custom_emoji(text: str) -> str:
    """Replace <tg-emoji> tags with their inner fallback emoji."""
    import re
    return re.sub(
        r'<tg-emoji emoji-id="\d+">(.*?)</tg-emoji>',
        lambda m: m.group(1),
        text,
    )


# ── Premium set used by the help bot ──────────────────────────────────────
#: key -> (custom emoji id, plain fallback). Semantic keys so call sites
#: read like intent (``ui_tag("sparkle")``) rather than glyph names.

UI_EMOJI_IDS: Dict[str, Tuple[str, str]] = {
    # status / feedback
    "check":     ("5917917398572211635", "✅"),
    "check_on":  ("5915613625359278584", "✅"),
    "check_done": ("5915722047513698700", "✅"),
    "cross":     ("5915894610709717241", "❌"),
    "warn":      ("5917860949817040467", "⚠️"),
    "alert":     ("5918260798387396946", "⚠️"),
    "new":       ("5917869294938497733", "🆕"),
    "plus":      ("5917908121442857117", "➕"),
    "fire":      ("5917806450977023726", "🔥"),
    "rocket":    ("5917935536219103066", "🚀"),
    "sparkle":   ("5915945987108511688", "✨"),
    # people / social
    "user":      ("5916034072592785479", "👤"),
    "rival":     ("5917987543978092091", "👤"),
    "globe":     ("5915728129187389553", "🌐"),
    "region":    ("5918273417001313756", "🌐"),
    "chat":      ("5915775824799211234", "💬"),
    "mute":      ("5915830538387595030", "🔈"),
    # rewards / shop / prestige
    "star":      ("5915719788360901158", "⭐"),
    "gift":      ("5917858965542150008", "🎁"),
    "love":      ("5918013330961735107", "😍"),
    "crown":     ("5918192804760133835", "👑"),
    "cart":      ("5917952668843648408", "🛒"),
    "trophy":    ("5915718748978814340", "🏆"),
    "heart":     ("5852755649405919501", "💙"),
    "giggle":    ("5852974147277169549", "🤭"),
    # power-ups
    "mega":      ("5917887935096561123", "💎"),
    "zmove":     ("5918152835794477491", "💎"),
    # move / stat views
    "bolt":      ("5852666434345248654", "⚡"),
    "battle":    ("5918013330961735107", "⚔️"),
    "comet":     ("5852826430466957463", "☄️"),
    "aim":       ("5852987088013633510", "➡️"),
    "pp":        ("5852755434657554545", "🔵"),
    "status":    ("5854846581219532134", "💤"),
    "gem":       ("5917887935096561123", "💎"),
}


def ui_tag(key: str, fallback: str = "") -> str:
    """``<tg-emoji…>…</tg-emoji>`` for a UI registry key (HTML only)."""
    entry = UI_EMOJI_IDS.get(str(key or "").strip().lower())
    if not entry:
        return fallback
    custom_id, plain = entry
    if not custom_id:
        return fallback
    return custom_emoji(plain or fallback, custom_id)


def ui_glyph(key: str, fallback: str = "") -> str:
    """Plain unicode glyph for a UI key — safe for button labels."""
    entry = UI_EMOJI_IDS.get(str(key or "").strip().lower())
    if not entry:
        return fallback
    _custom_id, plain = entry
    return plain or fallback


# ── Ball / type / coin / shiny — the ones AI answers mention ─────────────

BALL_EMOJI_IDS: Dict[str, str] = {
    "Poké Ball": "5852961356864561365",
    "Great Ball": "5915897634366695641",
    "Ultra Ball": "5915510236906529449",
    "Master Ball": "5916010141035013118",
    "Repeat Ball": "5915846142003781249",
    "Level Ball": "5915513002865468138",
    "Dusk Ball": "5915731968888152050",
    "Nest Ball": "5902528045419335365",
    "Safari Ball": "5915978143528656221",
}

BALL_FALLBACK: Dict[str, str] = {
    "Poké Ball": "🔴", "Great Ball": "🔵", "Ultra Ball": "⚫",
    "Master Ball": "🟣", "Repeat Ball": "🔴", "Level Ball": "🟡",
    "Dusk Ball": "🟢", "Nest Ball": "🟡", "Safari Ball": "🟢",
}

BALL_ID_TO_NAME: Dict[str, str] = {
    "pokeball": "Poké Ball", "masterball": "Master Ball",
    "greatball": "Great Ball", "ultraball": "Ultra Ball",
    "repeatball": "Repeat Ball", "levelball": "Level Ball",
    "duskball": "Dusk Ball", "nestball": "Nest Ball",
    "safariball": "Safari Ball",
}


def ball_tag(item_id: str) -> str:
    """Premium emoji HTML tag for a ball (icon only, HTML parse mode)."""
    if not item_id:
        return ""
    name = BALL_ID_TO_NAME.get(item_id.lower(), item_id.replace("-", " ").title())
    plain = BALL_FALLBACK.get(name, "🔴")
    return custom_emoji(plain, BALL_EMOJI_IDS.get(name, ""))


TYPE_EMOJI_IDS: Dict[str, str] = {
    "Normal":  "5915606195065856327",
    "Fire":    "5916011124582523123",
    "Water":   "5915535907926056421",
    "Grass":   "5915588474030792524",
    "Electric": "5915517211933417386",
    "Ice":     "5915711722412318031",
    "Fighting": "5915684543859269996",
    "Poison":  "5915673037641883235",
    "Ground":  "5915905872113967880",
    "Flying":  "5916033922268929532",
    "Psychic": "5915889053022035072",
    "Bug":     "5915989297558725418",
    "Rock":    "5915947206879223885",
    "Ghost":   "5915832011561377693",
    "Dragon":  "5915653126173498505",
    "Dark":    "5915558916065862295",
    "Steel":   "5915622945438310975",
    "Fairy":   "5915510507489467989",
}

TYPE_FALLBACK: Dict[str, str] = {
    "Normal": "🟣", "Fire": "🔥", "Water": "💧", "Grass": "🌿",
    "Electric": "⚡", "Ice": "❄️", "Fighting": "🥊", "Poison": "☠️",
    "Ground": "🌍", "Flying": "🕊️", "Psychic": "🔮", "Bug": "🐛",
    "Rock": "🪨", "Ghost": "👻", "Dragon": "🐉", "Dark": "🌑",
    "Steel": "⚙️", "Fairy": "🧚",
}


def type_tag(type_name: str) -> str:
    """Custom-emoji HTML tag for a type (the icon only)."""
    if not type_name:
        return ""
    key = str(type_name).strip().title()
    fallback = TYPE_FALLBACK.get(key, "❔")
    return custom_emoji(fallback, TYPE_EMOJI_IDS.get(key, ""))


#: Forge Coins marker.
COIN_EMOJI_ID = "5915882305628416528"


def coin_tag(fallback: str = "💰") -> str:
    """``<tg-emoji…>💰</tg-emoji>`` — the Forge Coins marker (HTML only)."""
    return custom_emoji(fallback, COIN_EMOJI_ID)


#: Shiny marker.
SHINY_EMOJI_ID = "5918098311184654030"


def shiny_tag(shiny: bool = True, fallback: str = "✨") -> str:
    """``<tg-emoji…>✨</tg-emoji>`` when shiny, else ``""``."""
    if not shiny:
        return ""
    return custom_emoji(fallback, SHINY_EMOJI_ID)


# ── Convenience constants (f{E.SPARKLE} in HTML messages) ─────────────────


class E:
    """Premium emoji constants for HTML messages only."""

    SPARKLE = ui_tag("sparkle")
    FIRE = ui_tag("fire")
    STAR = ui_tag("star")
    CHECK = ui_tag("check")
    CROSS = ui_tag("cross")
    WARN = ui_tag("warn")
    CROWN = ui_tag("crown")
    GIFT = ui_tag("gift")
    TROPHY = ui_tag("trophy")
    BATTLE = ui_tag("battle")
    REGION = ui_tag("region")
    CART = ui_tag("cart")
    GLOBE = ui_tag("globe")
    CHAT = ui_tag("chat")
    HEART = ui_tag("heart")
    ROCKET = ui_tag("rocket")
    NEW = ui_tag("new")
    USER = ui_tag("user")
    COIN = coin_tag()
    SHINY = shiny_tag()
    MEGA = ui_tag("mega")
    WELCOME = ui_tag("sparkle")  # reuse sparkle for welcome flair
