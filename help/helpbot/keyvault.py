"""AI API-key vault: ordered failover, per-key health, masked views.

All provider credentials live here. ``ai.py`` walks ``chain()`` for one
answer and reports every outcome with ``record()``, so ``/keymenu``
shows real per-key usage and health.

Failover order (``AI_PROVIDER = "auto"``): OpenRouter 1st → 2nd → 3rd,
then OpenAI, then Groq. The chain is walked in order inside one answer;
the first success wins. A 429 pauses that key 60s, an auth error
(401/402/403) pauses it 5 minutes — during a pause the next key is
tried instead.

Raw keys never leave this module: display goes through ``masked`` /
``snapshot()`` only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config

LOGGER = logging.getLogger(__name__)

#: Seconds a rate-limited key (429) steps aside.
COOLDOWN_429 = 60.0
#: Seconds a rejected/unpaid key (401/402/403) steps aside.
COOLDOWN_AUTH = 300.0

#: OpenRouter wants an app referer; every OpenRouter key gets these
#: (identical training — only the token differs between keys).
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://t.me/forge",
    "X-Title": "Forge Help Bot",
}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/120.0.0.0 Safari/537.36")


def _mask(key: str) -> str:
    """``sk-or-v1-…888c7`` — at most first 9 + last 4 characters."""
    if not key:
        return ""
    if len(key) <= 14:
        return "…" + key[-2:]
    return f"{key[:9]}…{key[-4:]}"


@dataclass
class Key:
    id: str                      # or1 / or2 / or3 / oa1 / gq1
    label: str                   # "OpenRouter #1"
    provider: str                # openrouter | openai | groq
    key: str                     # raw — Authorization header only
    base: str
    model: str
    headers: dict = field(default_factory=dict)
    # ── health stats (updated by record()) ──
    uses: int = 0
    ok: int = 0
    fail: int = 0
    last_used: float = 0.0
    last_ok: float = 0.0
    last_error: str = ""
    last_error_at: float = 0.0
    cooldown_until: float = 0.0

    @property
    def masked(self) -> str:
        return _mask(self.key)

    @property
    def cooling(self) -> bool:
        return self.cooldown_until > time.time()

    @property
    def state(self) -> str:
        """healthy | cooling | failing | new"""
        if self.cooling:
            return "cooling"
        if self.uses == 0:
            return "new"
        if self.last_error and self.last_error_at >= self.last_ok:
            return "failing"
        return "healthy"


_CACHE: list[Key] = []
_BUILT = False


def _build() -> list[Key]:
    keys: list[Key] = []
    for i, raw in enumerate(config.openrouter_keys(), 1):
        keys.append(Key(
            id=f"or{i}", label=f"OpenRouter #{i}", provider="openrouter",
            key=raw, base=config.OPENROUTER_BASE_URL,
            model=config.OPENROUTER_MODEL, headers=dict(OPENROUTER_HEADERS),
        ))
    if config.OPENAI_API_KEY:
        keys.append(Key(
            id="oa1", label="OpenAI", provider="openai",
            key=config.OPENAI_API_KEY, base=config.OPENAI_BASE_URL,
            model=config.OPENAI_MODEL,
        ))
    if config.GROQ_API_KEY:
        keys.append(Key(
            id="gq1", label="Groq", provider="groq",
            key=config.GROQ_API_KEY, base=config.GROQ_BASE_URL,
            model=config.GROQ_MODEL,
        ))
    return keys


def all_keys() -> list[Key]:
    """Every configured key in failover order (cached — keeps stats)."""
    global _BUILT
    if not _BUILT:
        _CACHE.extend(_build())
        _BUILT = True
    return _CACHE


def _wanted() -> list[Key]:
    """Keys allowed by AI_PROVIDER, in failover order."""
    wanted = config.AI_PROVIDER
    keys = all_keys()
    if wanted == "none":
        return []
    if wanted in ("", "auto"):
        return keys
    order = [k for k in keys if k.provider == wanted]
    if not order:
        if wanted in ("openrouter", "openai", "groq"):
            LOGGER.warning("AI_PROVIDER=%s has no API key configured.", wanted)
        else:
            LOGGER.warning("AI_PROVIDER=%s is not a known provider.", wanted)
    return order


def chain() -> list[Key]:
    """Live keys for one answer: failover order, cooling keys skipped.

    When *every* key is cooling, the full list is returned anyway —
    trying a cooling key still beats failing the answer outright.
    """
    keys = _wanted()
    if not keys:
        return []
    live = [k for k in keys if not k.cooling]
    return live or keys


def record(k: Key, ok: bool, error: str = "") -> None:
    """Book one call outcome against *k* (updates stats + cooldowns)."""
    now = time.time()
    k.uses += 1
    k.last_used = now
    if ok:
        k.ok += 1
        k.last_ok = now
        k.cooldown_until = 0.0
        return
    k.fail += 1
    k.last_error = (error or "error").strip()[:160]
    k.last_error_at = now
    low = k.last_error.lower()
    if "429" in low or "rate limit" in low or "rate_limit" in low:
        k.cooldown_until = now + COOLDOWN_429
    elif "401" in low or "402" in low or "403" in low:
        k.cooldown_until = now + COOLDOWN_AUTH


def snapshot() -> list[dict]:
    """Masked per-key view for /keymenu — never contains a raw key."""
    now = time.time()
    return [{
        "id": k.id,
        "label": k.label,
        "provider": k.provider,
        "model": k.model,
        "masked": k.masked,
        "state": k.state,
        "uses": k.uses,
        "ok": k.ok,
        "fail": k.fail,
        "last_used": k.last_used,
        "last_ok": k.last_ok,
        "cooldown_left": max(0.0, k.cooldown_until - now),
        "last_error": k.last_error,
    } for k in all_keys()]


async def test(k: Key) -> tuple[bool, str]:
    """1-token ping against one key. Returns (ok, error); records it."""

    def _post() -> None:
        payload = json.dumps({
            "model": k.model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{k.base.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _UA,
                **k.headers,
                "Authorization": f"Bearer {k.key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(
                request, timeout=min(config.AI_TIMEOUT, 20)) as resp:
            json.loads(resp.read().decode("utf-8"))

    try:
        await asyncio.to_thread(_post)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:                          # noqa: BLE001
            pass
        err = f"HTTP {exc.code} {detail}".strip()
        record(k, False, err)
        return False, err
    except Exception as exc:                       # noqa: BLE001 — network/JSON
        err = f"{type(exc).__name__}: {exc}"
        record(k, False, err)
        return False, err
    record(k, True)
    return True, ""


async def test_all() -> list[tuple[Key, bool, str]]:
    """Ping every configured key in parallel (for /keymenu's Test)."""
    results = await asyncio.gather(*(test(k) for k in all_keys()))
    return [(k, ok, err)
            for k, (ok, err) in zip(all_keys(), results)]
