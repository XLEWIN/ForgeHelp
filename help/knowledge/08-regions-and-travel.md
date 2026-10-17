# Regions, travel and EV training

## The nine regions

Your current region decides which species and which level range appear in
your hunts.

| Region | Gen | Pokédex range | Wild levels |
| --- | --- | --- | --- |
| Kanto | 1 | #1–151 | 1–30 |
| Johto | 2 | #152–251 | 15–45 |
| Hoenn | 3 | #252–386 | 25–55 |
| Sinnoh | 4 | #387–493 | 35–65 |
| Unova | 5 | #494–649 | 45–75 |
| Kalos | 6 | #650–721 | 55–85 |
| Alola | 7 | #722–809 | 65–90 |
| Galar | 8 | #810–905 | 75–95 |
| Paldea | 9 | #906–1025 | 85–100 |

**Travel is completely open:** no unlock level, no cooldown — you can move
between any two regions as often as you like. (The in-bot help menu still
mentions a "level = gen number" unlock rule; travel is not actually gated.)

## Commands

- `/travel` — opens the inline travel grid menu (current region plus every region).
- `/travel <region>` — go directly, e.g. `/travel johto`
  - Accepts the name, a **number** (`/travel 7` = Alola), or a fragment
    (`/travel kal`).
  - If you are already there, it just says so.
  - An unknown name prints the region list.
- `/hunt` — encounter a wild Pokémon from your **current** region (DM only).

## EV training — /evtrain

`/evtrain <pokemon> <stat>` puts hunting into training mode for that stat:

- Costs **500 Forge Coins per hunt** — charged only when a spawn actually
  lands (item/empty spawns are free).
- The spawn is a training dummy: **you cannot catch it** (no Throw Ball
  button, no Flee button).
- Winning the battle gives **1–5 EVs** in the chosen stat.
- `/evtrain stop` turns training off (you can also do it from the EV menu
  if you cannot afford the fee).

## Notes for hunters

- Starting a new `/hunt` makes the previous encounter flee.
- You cannot hunt while a battle is active.
- Encounters expire after **4 minutes** of user inactivity.
