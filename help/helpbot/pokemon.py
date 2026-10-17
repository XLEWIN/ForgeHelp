"""Offline Pokémon dex for the help bot.

Self-contained loader over Forge's bundled generation JSON
(``gen_01..09.json``, by_id + by_name). Never imports ``forge`` — the
data directory is resolved from settings or a default sibling path.

Data shape per pokemon (from PokéAPI dump):
  id, name, types, base_stats, ev_yields, catch_rate, gender_rate,
  growth_rate, habitat, height, weight, genus, flavor_text,
  moves (level-up), tm_moves, tutor_moves, egg_moves,
  sprites (official_artwork, ...), is_legendary, is_mythical, ...
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Optional

from . import config

LOGGER = logging.getLogger(__name__)

# ── Stat names ────────────────────────────────────────────────────────────

STAT_MAP = {
    "hp": "HP", "attack": "ATK", "defense": "DEF",
    "sp_atk": "SP.ATK", "sp_def": "SP.DEF", "speed": "SPD",
}
STAT_ORDER = ["hp", "attack", "defense", "sp_atk", "sp_def", "speed"]

#: Game max level shown on /poke headers.
MAX_LEVEL = 100

# ── Loader state ──────────────────────────────────────────────────────────

_BY_ID: dict = {}
_BY_NAME: dict = {}
_LOADED = False
_LOAD_FAILED = False


def _candidate_dirs() -> list[Path]:
    """Search order: setting override → sibling forge-main → in-repo copy."""
    dirs: list[Path] = []
    override = Path(str(config.POKEMON_DATA_DIR or "").strip())
    if override.is_dir():
        dirs.append(override)
    # ForgeHelp/forge-main/forge/data/generations (sibling of the repo)
    dirs.append(config.ROOT.parent / "forge-main" / "forge" / "data" / "generations")
    # In-repo copy, if someone drops the JSONs under help/data.
    dirs.append(config.ROOT / "data" / "generations")
    # De-dupe while keeping order.
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def data_dir() -> Optional[Path]:
    for d in _candidate_dirs():
        if d.is_dir() and any(d.glob("gen_*.json")):
            return d
    return None


def _register_arceus_forms() -> None:
    """Synthesize Arceus elemental form entries (port of Forge's loader)."""
    base = _BY_ID.get("493")
    if not base:
        return
    art = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/493.png"
    base["sprite"] = art
    base.setdefault("sprites", {})["official_artwork"] = art
    base["sprites"]["official_artwork_shiny"] = (
        "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/shiny/493.png"
    )
    home = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/home"
    for t in (
        "Normal", "Fire", "Water", "Grass", "Electric", "Ice",
        "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
        "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
    ):
        form_name = "Arceus" if t == "Normal" else f"Arceus ({t})"
        entry = dict(base)
        entry["name"] = form_name
        entry["types"] = [t]
        slug = t.lower()
        entry["sprite"] = f"{home}/493.png" if t == "Normal" else f"{home}/493-{slug}.png"
        entry["sprites"] = dict(base.get("sprites", {}))
        entry["sprites"]["home"] = entry["sprite"]
        entry["sprites"]["official_artwork"] = art
        _BY_NAME[form_name.lower()] = entry
        _BY_NAME[f"arceus-{slug}"] = entry


def load() -> bool:
    """Load all gen_*.json files once. Returns True when the dex is ready."""
    global _LOADED, _LOAD_FAILED
    if _LOADED:
        return True
    if _LOAD_FAILED:
        return False
    directory = data_dir()
    if directory is None:
        LOGGER.warning(
            "pokedex: no gen_*.json found (set POKEMON_DATA_DIR or keep "
            "forge-main next to this repo) — /mv and /poke stay disabled")
        _LOAD_FAILED = True
        return False
    count = 0
    try:
        for gen_file in sorted(directory.glob("gen_*.json")):
            raw = json.loads(gen_file.read_text(encoding="utf-8"))
            _BY_ID.update(raw.get("by_id", {}))
            _BY_NAME.update(raw.get("by_name", {}))
            count += 1
        _register_arceus_forms()
        _LOADED = True
        LOGGER.info(
            "pokedex: loaded %s gen files, %s pokemon from %s",
            count, len(_BY_ID), directory)
        return True
    except Exception:
        LOGGER.exception("pokedex: failed to load dex from %s", directory)
        _LOAD_FAILED = True
        return False


def ready() -> bool:
    return _LOADED or load()


def count() -> int:
    return len(_BY_ID)


# ── Lookups ───────────────────────────────────────────────────────────────


def get_pokemon_data(pokemon_id: int) -> Optional[dict]:
    if not ready():
        return None
    return _BY_ID.get(str(pokemon_id))


def get_pokemon_by_name(name: str) -> Optional[dict]:
    if not ready() or not name:
        return None
    return _BY_NAME.get(name.lower())


def _norm(s: str) -> str:
    return " ".join(
        s.replace("-", " ").replace(".", " ").replace("'", "").split()
    )


def get_pokemon_by_name_fuzzy(name: str) -> Optional[dict]:
    """Exact match, then prefix/normalized variants (port of Forge)."""
    if not ready() or not name:
        return None
    dex = get_pokemon_by_name(name)
    if dex:
        return dex
    low = name.lower().strip()
    if not low:
        return None
    nlow = _norm(low)
    variants = (low, nlow, low.replace("-", ""), nlow.replace(" ", ""))
    # Direct key hits first (O(1)).
    for key, entry in _BY_NAME.items():
        if key.startswith(variants) or _norm(key) in variants:
            return entry
    # Numeric id fallback ("445", "#445").
    digits = re.sub(r"^\D+|\D+$", "", low)
    if digits.isdigit():
        return get_pokemon_data(int(digits))
    return None


def artwork_url(pokemon: dict, shiny: bool = False) -> str:
    """Official artwork URL (PNG) for rich-media / photo embedding."""
    sprites = pokemon.get("sprites") or {}
    if shiny:
        return (sprites.get("official_artwork_shiny")
                or sprites.get("home_shiny")
                or sprites.get("shiny")
                or sprites.get("official_artwork")
                or pokemon.get("sprite") or "")
    return (sprites.get("official_artwork")
            or sprites.get("home")
            or sprites.get("default")
            or pokemon.get("sprite") or "")


# ── Display helpers (ported from Forge data.py / pokemon_data.py) ────────


def stat_abbr(stat: str) -> str:
    return STAT_MAP.get(stat, stat.upper())


def calculate_stat_range(base: int, stat: str) -> tuple[int, int]:
    """Min/max at level 50 (0 IV/0 EV neg nature vs 31 IV/252 EV pos nature)."""
    if stat == "hp":
        min_stat = math.floor((2 * base) * 50 / 100) + 50 + 10
        max_stat = math.floor((2 * base + 31 + 63) * 50 / 100) + 50 + 10
    else:
        min_stat = math.floor(((2 * base + 0 + 0) * 50 / 100 + 5) * 0.9)
        max_stat = math.floor(((2 * base + 31 + 63) * 50 / 100 + 5) * 1.1)
    return min_stat, max_stat


def best_natures(base_stats: dict) -> list[str]:
    nature_map = {
        "hp": ["Hardy", "Docile", "Serious", "Bashful"],
        "attack": ["Adamant", "Lonely", "Naughty", "Brave"],
        "defense": ["Bold", "Impish", "Relaxed", "Lax"],
        "sp_atk": ["Modest", "Mild", "Rash", "Quiet"],
        "sp_def": ["Calm", "Gentle", "Careful", "Sassy"],
        "speed": ["Timid", "Jolly", "Hasty", "Naive"],
    }
    top = max(STAT_ORDER, key=lambda s: (base_stats or {}).get(s, 0))
    return nature_map.get(top, nature_map["hp"])


def ev_yield_display(ev_yields: dict) -> str:
    if not ev_yields:
        return "None"
    parts = []
    for stat in STAT_ORDER:
        val = ev_yields.get(stat, 0)
        if val and val > 0:
            parts.append(f"{val} {stat_abbr(stat)}")
    return ", ".join(parts) if parts else "None"


def gender_display(gender_rate) -> str:
    try:
        rate = int(gender_rate)
    except (TypeError, ValueError):
        return "Unknown"
    if rate == -1:
        return "Genderless"
    male = (8 - rate) / 8 * 100
    female = rate / 8 * 100
    return f"{male:.0f}% male / {female:.0f}% female"


def growth_display(rate: str) -> str:
    return (rate or "unknown").replace("-", " ").title()


def moves_for(pokemon: dict, category: str) -> list[dict]:
    """category: levelup | tm | tutor | egg."""
    if category == "levelup":
        return pokemon.get("moves") or []
    if category == "tm":
        return pokemon.get("tm_moves") or []
    if category == "tutor":
        return pokemon.get("tutor_moves") or []
    if category == "egg":
        return pokemon.get("egg_moves") or []
    return []


CATEGORY_TITLES = {
    "levelup": "Level-up moves",
    "tm": "TM moves",
    "tutor": "Tutor moves",
    "egg": "Egg moves",
}

#: Flat move rows for /mv: (name, type, power, accuracy, source_label).
#: source_label is "Lv.X", "TM", "Tutor" or "Egg".
def all_move_rows(pokemon: dict) -> list[dict]:
    """Every learnable move, grouped level-up → TM → tutor → egg."""
    rows: list[dict] = []
    seen: set[str] = set()

    def _push(move: dict, source: str) -> None:
        name = move.get("name") or ""
        if not name:
            return
        key = f"{name}|{source}"
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "name": name,
            "type": move.get("type") or "Normal",
            "power": move.get("power"),
            "accuracy": move.get("accuracy"),
            "category": move.get("category") or "Status",
            "source": source,
        })

    for m in moves_for(pokemon, "levelup"):
        level = m.get("level")
        # level 0 = "no fixed level" (evolved/initial) — label as Lv.1.
        label = f"Lv.{level}" if level else "Lv.1"
        _push(m, label)
    for m in moves_for(pokemon, "tm"):
        _push(m, "TM")
    for m in moves_for(pokemon, "tutor"):
        _push(m, "Tutor")
    for m in moves_for(pokemon, "egg"):
        _push(m, "Egg")
    return rows


def dex_number(pokemon_id) -> str:
    try:
        return f"#{int(pokemon_id):04d}"
    except (TypeError, ValueError):
        return str(pokemon_id)
