# Collection, PC and team building

## Browsing what you own

| Command | Shows |
| --- | --- |
| `/mypokemons` | Paginated list of everything you caught |
| `/mypokemon` · `/mypoke` · `/collection` | Quick collection list |
| `/myinv` · `/myinventory` | Balls, stones, TMs and key items |
| `/myshinies` | Every shiny you own |
| `/myfav` | Your favourites |
| `/myforms` | Regional and alternate forms in your collection |
| `/nicknames` | Pokémon you have nicknamed |
| `/myanc` | Your **Ancients** — every Legendary and Mythical you own |

`/mypokemons` is the main browser: it pages through your list, and its
buttons control sorting and what each row shows.

## Sorting and display

- `/sort` — sort options: name, time, level, nature, types, total IVs,
  total EVs, Pokédex number, each individual IV and EV.
- `/display` — choose what list rows show: none, level, nature, types,
  total IVs, total EVs, type symbol, or any single IV/HP-Attack-Defense
  line.

## Searching and filtering — /search and /filter

`/search [filters]` opens results immediately. Accepted arguments:

- **Type:** `/search fire` (any Pokémon type)
- **Generation:** `/search 3` (generations 1–9, by National Dex range)
- **Shiny:** `/search shiny`
- **Legendary:** `/search legendary`
- **IV range:** `/search iv>150` or `/search iv:150-180`
- **Name:** anything else is treated as a name search, e.g. `/search eevee`

`/filter` opens the interactive filter menu instead: By Type, By Gen,
Shiny Only, Legendaries, IV Range, Name Search, Clear All.

## PC storage — /pc

`/pc` opens your storage box for Pokémon that are not in your active list.
It also has its own typing-based search prompt (send `/pc` again to
replace an outstanding name prompt).

## Looking at one Pokémon

| Command | Shows |
| --- | --- |
| `/data <name>` | Species data and spawn info, e.g. `/data gyarados` |
| `/details <name>` | Extended details, e.g. `/details Charmeleon` |
| `/stats <name>` | Full stat card, e.g. `/stats Charmeleon` |
| `/bestnat <name>` | Best natures for that species |
| `/checkevolve <name>` | What it can evolve into |
| `/lineage <name>` | Family tree of a bred Pokémon |

Names are matched fuzzily — close spellings still resolve.

## Managing them

- `/nickname` — nickname wizard: pick a Pokémon, then type the new name.
  `/cancel` exits any wizard or dialog.
- `/setfav <name>` — toggle favourite, e.g. `/setfav pikachu`
- `/release <name>` — release a Pokémon, e.g. `/release charmander`
- `/forms <name>` — view and change forms, e.g. `/forms pikachu`
- `/evolve` — pick a Pokémon and confirm an evolution
- `/move <move>` — change moves, e.g. `/move flamethrower`
- `/chart` — IV/EV calculator

## Teams

- `/myteam` — team card image and the six Pokémon on your team
- `/teams` — list every saved team
- `/newteam <name>` — create one, e.g. `/newteam rain`
- `/delteam <name>` — delete one, e.g. `/delteam rain`
- `/team`, `/setteam`, `/remteam` are legacy redirects to the new system
  and show help for it.
