# Catching Pokémon in Forge

Hunting is the core loop: find a wild Pokémon, then either beat it or
throw a ball at it.

## Start an encounter — /hunt

Send `/hunt` in **private chat with the bot** (in a group it replies
*"This command only works in DM"* with an Open DM button).

- You must be registered (`/start`) first.
- You cannot hunt while you are in a battle — finish or flee it first.
- The pool is drawn from your **current region**: the region sets which
  species and which level range can appear.
- Starting a new hunt makes the previous encounter flee.
- A captcha may appear instead of a spawn — solve it and hunt again.

`/open` and `/close` show or hide the hunt panel in your DM.

## The encounter screen

You get a photo of the wild Pokémon (on a type background) with buttons:

| Button | Effect |
| --- | --- |
| **Battle It** | Fight the wild Pokémon in the battle scene |
| **EV Yield** | Preview what EVs beating it would train |

Tap **Battle It**, then the **Ball** button in the full battle screen,
to catch without typing a command.

## Timers and limits

- **4 minutes** of user inactivity and the encounter auto-flees.
- Every failed throw burns one turn; the encounter is given **1–10 turns**
  total, then the Pokémon flees regardless.
- There is no flee button — leaving an encounter is the 4-minute timeout
  or starting a new `/hunt`.
- Encounters live in memory: a bot restart clears them (start a new hunt).

## Balls

Balls are items. Buy them with `/buy`, check what you own with `/myinv`,
and see every ball with its catch chance and price with `/pballs`.
Higher-tier balls have a much better catch multiplier than the regular
ball, so save the strong balls for legendaries and shinies.
`/sell <ball> <qty>` converts unused balls back to coins.

`/shop` also opens the market with categories including Poké Balls,
medicine, vitamins, evolution items, held items and berries.

## Rarity — how rare is what I just found?

Spawn rarity (share of the non-legendary pool):

| Tier | Chance |
| --- | --- |
| Common | 58.50% |
| Uncommon | 25.00% |
| Rare | 9.50% |
| Very rare | 4.00% |
| Ultra rare | 2.00% |
| Pseudo-legendary | 0.60% |
| Legendary | 0.32% |
| Mythical | 0.08% |

## Shiny odds

Shiny is rolled separately from rarity:

- **Shiny** — 1 in 2,000 (0.05%)
- **Ultra shiny** — 1 in 20,000
- **God shiny** — 1 in 200,000
- A hidden bonus shiny roll adds about 0.10%, so effective shiny odds are
  roughly **1 in 640** overall.

Shiny, ultra-shiny and god-shiny spawns are prefixed on the encounter
screen so you know before you throw.

## Forms

Alternate and regional forms roll on top of the species roll: 96% normal,
2% regional, 1% alternate, 0.8% rare form, 0.2% ultra-rare form.
`/forms <name>` and `/myforms` show which forms exist and which you own.

## IVs

Every stat rolls independently 0–31 at spawn — a perfect 186/186 spread
is about 1 in 1.07 billion. Use `/chart` to see IV/EV maths and
`/boost <name>` to raise a stat once.

## Weather

About 1 in 5 encounters starts with weather (rain, sun, sandstorm or hail)
shown on the encounter screen.

## EV training mode

`/evtrain <pokemon> <stat>` switches hunting into training mode:

- Costs **500 Forge Coins per hunt** (charged only when a spawn lands).
- The spawn becomes a training dummy — **no catching** and no ball button.
- Winning the battle awards **1–5 EVs** in the chosen stat.
- `/evtrain stop` turns it off.

## Safari Zone

- `/safari` — Safari Zone info.
- `/enter <zone>` — join the Safari of **your current region** (the zone
  follows wherever you travel), e.g. `/enter Primal Ocean`.
- `/exit` — leave the Safari Zone.
- Entry costs **100 Forge Coins** and gives **30 Safari balls** and
  **100 hunts**.
- **25% of every Safari hunt is a Legendary** from that region, and 12%
  of that Legendary roll is a Mythical — the Safari is where you hunt them.
- The **Omni Ring** upgrade (`/use omni-ring`) adds a 5% chance for any
  normal hunt in your region to be overridden by a regional Legendary or
  Mythical.
