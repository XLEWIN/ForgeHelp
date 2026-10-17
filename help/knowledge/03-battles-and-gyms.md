# Battles, gyms and Z-Moves

## Trainer battles — /battle

Send `/battle` **while replying to another trainer's message** to fight
them. `/challenge` opens the challenge menu (same system, extra options).

Battle settings:

- **Mode:** singles (1v1), 6v6, or open team size (1–6).
- **Weather** starts about 30% of battles (rain, sun, sandstorm, hail) and
  lasts up to 8 turns.
- Both players act under a turn lock — one move each, then it resolves.

In-battle actions include: **Move**, **Switch**, **Use** (battle items such
as X Attack / X Defense / Dire Hit), **Team** (view rosters), **Mega**
evolution, **Dynamax**, **Form change**, **Arceus plate**, **Z-Move** menu,
**Throw ball** (catch attempts inside battle), **Run**, and ending the match.

Notes from the in-bot help menu:

- Catching a Pokémon during a battle keeps it.
- Winning battles pays roughly **10–20 coins**.

A battle locks your account for hunting: you cannot `/hunt` while a battle
is active. Battles expire after **4 minutes without an accepted action**
from either side. `/clear` unsticks a frozen battle.

## Gym league — /gym and /gymbattle

- `/gym` — the gym league screen with all leaders.
- `/gymbattle <leader>` — fight a leader, e.g. `/gymbattle Brock`.

Gym leaders currently in the bot:

| Leader | Gym | City |
| --- | --- | --- |
| Brock | Pewter Gym | Pewter City |
| Misty | Cerulean Gym | Cerulean City |
| Erika | Celadon Gym | Celadon City |
| Koga | Fuchsia Gym | Fuchsia City |
| Sabrina | Saffron Gym | Saffron City |
| Clair | Blackthorn Gym | Blackthorn City |
| Juan | Sootopolis Gym | Sootopolis City |
| Volkner | Sunyshore Gym | Sunyshore City |
| Drayden | Opelucid Gym | Opelucid City |
| Oleana | Rose Tower | Wyndon City |

Gym battles run on the same real battle engine as PvP, so the same
switching, items, mega and Z-Move tactics apply.

## AI battle analysis — /analyze

`/analyze` (alias `/battleanalyze`) asks the bot's AI to break down your
last battle: strengths, weaknesses, improvement tips and a quality verdict.
It needs the OpenRouter API key to be configured on the deployment; if it
is missing you get a setup message instead of an analysis.

## Z-Moves — /zmine

1. Buy a **Z-Crystal** in `/shop` → Z-Crystals (they also drop from hunts).
2. `/zmine` to equip the crystal.
3. In battle, open the Z-move menu and power up a same-type move —
   **once per battle**.

The crystal catalogue lives in `/shop`; `/zmine` only handles equipping.

## Team building that matters in battle

- `/myteam` — team card image and roster; `/teams`, `/newteam <name>`,
  `/delteam <name>` manage multiple saved teams.
- `/move <move>` — change a Pokémon's moves.
- `/equip <item>` / `/unequip <item>` — held items (Choice Band, Life Orb,
  Focus Sash, Assault Vest, Eviolite …).
- `/bestnat <name>` — best natures for a species.
- `/chart` — IV/EV calculator.
- `/evolve` and `/checkevolve <name>` — evolution paths and confirmation.
