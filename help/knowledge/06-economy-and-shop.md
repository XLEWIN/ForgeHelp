# Economy — Forge Coins, rewards and the shop

The currency is **Forge Coins** (shown as F.C.). Your balance is on
`/mystats` and in every shop screen.

## Earning

- **Winning battles** pays about 10–20 coins.
- **`/daily`** — 90–100 coins, plus **+5 per consecutive day** (streak cap
  50), plus 2–5 balls. Resets at **midnight IST**. Main-group reward.
- **`/weekly`** — 450–500 coins, plus **+20 per consecutive week**
  (streak cap 100), plus 10–15 balls and 2–4 Great Balls. Resets
  **Monday 00:00 IST**. Main-group reward.
- **`/rewards`** — shows both statuses and your streaks.
- **`/quest`** and **`/achievements`** pay out on claim.
- **`/referral`** — your invite link and milestone rewards.
- **`/sell <item> [qty]`** — sell items back, e.g. `/sell candy 3`.

### Membership gate

`/daily`, `/weekly` and `/redeem` require you to be a member of the bot's
required channel and group. If you are not, the bot shows a gate with
**join** buttons and an **I Joined** button that re-checks and then runs
the command you asked for.

## Daily and weekly details

| | Daily | Weekly |
| --- | --- | --- |
| Coins | 90–100 | 450–500 |
| Streak bonus | +5/day, cap 50 | +20/week, cap 100 |
| Items | 2–5 balls | 10–15 balls + 2–4 Great Balls |
| Resets | midnight IST | Monday 00:00 IST |

## The shop

- `/shop` — browse the market (balance shown at the top).
- `/pballs` — every Poké Ball with catch rate, price and how many you own.
- `/buy <item> [qty]` — e.g. `/buy Ultra 2`
- `/sell <item> [qty]` — e.g. `/sell candy 3`
- `/myinv` · `/myinventory` — what you already own.
- `/use <item>` — use an item from inventory.

Shop sections include Poké Balls, medicine (Potion, Super Potion, Hyper
Potion, Max Potion, Full Restore, Revive, antidotes …), vitamins
(HP Up, Protein, Iron, Calcium, Zinc, Carbos, PP Up, PP Max), evolution
items (Fire/Water/Thunder/Leaf/Moon/Sun Stones and many more), held items
(Choice Band, Choice Specs, Choice Scarf, Life Orb, Focus Sash, Rocky
Helmet, Assault Vest, Eviolite …), berries, Z-Crystals and Forge
exclusives (Nova Incense, Catch Charm, Shiny Lure, Exp. Share, Rare
Candy, Nature Mint, IV Booster).

## Training items

| Command | Effect |
| --- | --- |
| `/candy <name>` | Rare Candy — +1 level (documented as groups only) |
| `/boost <name>` | +1 IV, once per stat |
| `/vitamin <name>` | Boost EVs |
| `/berry <name>` | Reduce EVs by 10 |
| `/nullcandy` | Reset a Pokémon to level 1 |
| `/equip <item>` · `/unequip <item>` | Give or remove a held item |

## Giving and gifting

- `/give <coins>` — give coins (reply to the recipient), e.g. `/give 100`
- `/send_tm <TM>` — send a TM (reply), e.g. `/send_tm 05`
- `/redeem <code>` — redeem a gift code, e.g. `/redeem FORGE100`

Codes are made by the bot owner (`/gen` is owner-only) and distributed in
@ForgeUpdates.

## Permanent account upgrades

Some items are consumed once and give a permanent account effect. They
appear in the **Secret Stash** section of `/myinv` and are activated with
`/use <item>`:

| Item | Effect |
| --- | --- |
| **Omni Ring** | Every hunt gains a 5% chance to spawn a regional Legendary or Mythical instead of the normal spawn |
| **Egg Incubator** | All Eggs need **half the journey** to hatch (stacks with Flame Body) |

Using one twice just tells you the upgrade is already active — the item is
only consumed the first time.

## Referrals — /referral

`/referral` shows your link, how your trainees are doing, and the
one-time milestone ladder:

| Referrals | Reward |
| --- | --- |
| 1 | 500 Forge Coins |
| 3 | Random TM |
| 5 | Random TM + 1,000 coins + Shiny Rare Egg |
| 10 | Master Ball + random Mega Stone |

The tier-5 shiny egg draws from a rare pool (Dratini, Gible, Deino,
Bagon, Larvitar, Riolu, Eevee, Togepi).
