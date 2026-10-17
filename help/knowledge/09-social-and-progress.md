# Factions, quests, achievements and ranked seasons

## Factions

Factions are **private guilds** — there is no public list and no joining
by name. The only way in is an **invite link** issued by the faction
owner. A faction with no members is dissolved, so a name is never locked
by an empty roster.

| Command | What it does |
| --- | --- |
| `/faction` | Faction hub |
| `/factioncreate <name> \| <desc>` | Create one, e.g. `/factioncreate Rocket \| Crime` |
| `/factionjoin <code\|link>` | Join with an invite code or link |
| `/factionleave` | Leave your faction |
| `/factionmembers` | Your faction roster |
| `/facinvite` | Show (leader only) or rotate the invite link |
| `/factionlist` | Retired — factions are private and cannot be browsed |
| `/factiondonate <coins>` | Donate coins, e.g. `/factiondonate 100` |
| `/factionchest` | The shared war chest |
| `/facwar` | Faction war hub |
| `/facwarreport <win\|loss> [pts]` | Report a war result (max 10 points), e.g. `/facwarreport win 3` |
| `/facedisband` | Owner only, always behind a confirmation tap |

Everything lives in the database: rosters, war chests, seasons and invite
links all survive bot restarts.

## Quests — /quest and /questclaim

`/quest` (alias `/quests`) shows your current **daily** and **weekly**
quests. Five daily quests are picked each day and three weekly quests
each week; `/questclaim` claims whatever you have finished.

Daily quests include:

| Quest | Goal | Reward |
| --- | --- | --- |
| Catcher | Catch 5 Pokémon | 150 coins, 50 XP, 3 balls |
| Battler | Win 3 battles | 200 coins, 80 XP |
| Tracker | Hunt 10 times | 100 coins, 40 XP |
| Warm-up Bout | Win 1 battle | 250 coins, 60 XP |
| Faithful | Claim your daily reward | 30 XP |

Weekly quests:

| Quest | Goal | Reward |
| --- | --- | --- |
| Warrior | Win 20 battles | 800 coins, 300 XP, 10 balls |
| Collector | Catch 30 Pokémon | 600 coins, 250 XP |
| Pathfinder | Hunt 15 times | 1000 coins, 400 XP |

## Achievements — /achievements and /achclaim

`/achievements` (alias `/ach`) lists achievements with their tiers;
`/achclaim` claims unlocked rewards.

| Achievement | Tracks | Tiers |
| --- | --- | --- |
| First Blood | Battles won | 1 / 10 / 50 / 200 |
| Ball Master | Pokémon caught | 10 / 50 / 200 / 1000 |
| Pokédex Pro | Unique species caught | 5 / 25 / 75 / 150 |
| Tycoon | Coins held at once | 1k / 10k / 50k / 200k |
| On Fire | Win streak | 3 / 7 / 15 / 30 |
| World Traveler | Regions visited | 2 / 4 / 6 / 9 |
| Faction Loyal | Faction contributions | 1 / 5 / 20 / 100 |
| Quest Hunter | Quests completed | 5 / 25 / 100 / 500 |
| Ranked Champion | Highest PvP season rank | 2 / 4 / 7 / 9 |

## Ranked seasons — /ranked

A **two-month** ranked season with a ten-tier ladder driven by rank points
(RP):

| Tier | RP |
| --- | --- |
| Iron | 0 |
| Steel | 600 |
| Copper | 1200 |
| Silver | 2000 |
| Gold | 3000 |
| Platinum | 4200 |
| Diamond | 5600 |
| Titanium | 7200 |
| Obsidian | 8600 |
| Mythic | 10000 |

- Winning PvP pays **+40 to +55 RP**; losing costs **30–40 RP** (RP floors
  at 0).
- Season-end rewards land at **Gold**, **Diamond** and **Mythic**.
- `/pvpleaderboard` shows the season standings.
- `/pvpclaim` is retired and just explains that claims now happen from the
  season screen.

Everything you need day to day is `/quest`, `/achievements` and `/ranked`.
