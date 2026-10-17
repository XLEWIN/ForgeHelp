# Getting started with Forge

## Register with /start

Open the bot in **private chat** and send `/start`. If you send `/start`
inside a group, it replies that registration needs your private chat and
offers an **Open DM** button.

The registration conversation runs in this order:

1. **Welcome** — tap **Move Forward**.
2. **Choose your gender** — male or female.
3. **Choose your region** — your starting region.
4. **Choose your starter** — the Pokémon your journey begins with.
5. **Trainer name** — type a name (2–20 characters). You can change it later
   with `/rename <name>`.

If you are already registered, `/start` says so and points you at your
commands instead of starting over.

Your progress, coins and Pokémon are stored on the bot's database and are
the same in every chat.

## Everyday commands

| Command | What it does |
| --- | --- |
| `/help` | Full command menu with tappable module pages |
| `/mystats` | Name, coins, catches and PvP at a glance |
| `/myinv` · `/myinventory` | Balls, stones, TMs and key items |
| `/mypokemons` | Paginated list of everything you caught |
| `/myteam` | Team card image and roster |
| `/rename <name>` | Change your trainer name (2–20 characters) |
| `/query <text>` | Report a bug or suggest a feature — sent to the owners |
| `/clear` | Unstick a frozen battle or trade |

## Where commands work

- **Private chat (DM):** `/hunt`, the rest of the encounter flow,
  `/start` registration, `/open` and `/close` for your hunt panel.
- **Group chats:** `/battle`, `/guess`, `/quest`, trading, factions and most
  social/economy commands. Trying `/hunt` in a group shows
  *"This command only works in DM"* with an Open DM button.
- **Main group only:** `/daily` and `/weekly` are documented as main-group
  only rewards; `/candy` is documented as groups only.
- Restricted commands (marked owner/sudo in the command index) do nothing
  for regular players.

## Anti-bot verification

Hunting may show a **captcha** instead of a spawn — a distorted text or a
four-button "pick the matching image" puzzle. Solve it and hunt again.
A check you never answer never costs anything: it simply reappears on
your next hunt, and a pending check must be cleared before hunting
continues. Only an answer that is **wrong** or **faster than 30
seconds** costs a strike (5m → 15m → 24h locks for 1, 2 and 3
consecutive fails).

## Stuck?

- A frozen battle or trade: `/clear`
- Leave a stuck wizard: `/cancel`
- Bot not responding to a command: check `/help` for the exact syntax,
  then ask in @ForgeSupport
