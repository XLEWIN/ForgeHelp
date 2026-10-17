# Frequently asked questions

## Starting out

**How do I begin?**
Open the bot in private chat and send `/start`. Follow the prompts:
Move Forward → gender → region → starter → trainer name.

**Do I need a group?**
You need the bot somewhere — hunting happens in DM, most social and
economy commands work in groups, and `/daily` / `/weekly` are documented
as main-group rewards.

**What is the prefix?**
`/` — every command starts with a slash, e.g. `/help`, `/hunt`, `/myteam`.

## Catching

**Where do I find wild Pokémon?**
`/hunt` in private chat. The pool comes from your current region.

**Why does /hunt say "This command only works in DM"?**
Because it is DM-only. Tap the Open DM button and try again there.

**How do I catch one?**
Tap **Battle It**, then **Ball**, on the full battle screen. Failed throws
burn turns — you get 1–10 throws before it flees, and the encounter expires
after 4 minutes of user inactivity.

**Where do I get balls?**
`/buy <ball> [qty]`, free ones from `/daily` and `/weekly`, and drops.
`/pballs` lists every ball with its catch rate and price.

**What are the shiny odds?**
Shiny 1 in 2,000, ultra shiny 1 in 20,000, god shiny 1 in 200,000, plus a
hidden shiny roll that brings effective odds to roughly 1 in 640.

**What is an Ancient?**
Your Legendaries and Mythicals — `/myanc`.

## Progress and money

**How do I get coins?**
Battle wins (about 10–20), `/daily`, `/weekly`, quests, achievements,
selling items, and referrals. `/mystats` shows your balance.

**Why can't I claim /daily?**
Check, in order: already claimed today (resets midnight IST), not in the
main group, membership gate (join the required channel/group and tap
**I Joined**), or your streak simply resets on a missed day.

**How do I level up my Pokémon?**
`/candy <name>` (+1 level, groups only), battles, and EXP from wins.
`/nullcandy` resets one to level 1 if you want a do-over.

**How do I evolve?**
`/checkevolve <name>` shows the paths, `/evolve` opens the confirm screen.
Stones are bought in `/shop`.

## Social

**How do I trade?**
Reply to the other trainer and send `/trade`. Both sides pick, preview and
confirm. `/canceltrade` cancels, `/tradehistory` shows past trades.

**How do I join a faction?**
You need an invite link — factions are private. `/factionjoin <link>`.
`/factioncreate <name> | <desc>` makes your own.

**How do I get a team?**
`/myteam` shows your team of six; `/newteam <name>` saves a named team,
`/teams` lists them.

## Technical

**Did the bot restart and lose my encounter?**
Encounters are held in memory, so a restart clears them — just `/hunt`
again. Everything else (coins, Pokémon, teams, factions) is in the
database.

**Why did /analyze not answer?**
It needs an AI provider key configured on the deployment; without it you
get a setup message instead of an analysis.

**Are there trivia / duel / slot commands?**
No. They appear in older help text but are not registered in this build.
`/guess` is the registered mini-game.

**How do I report a bug or suggest a feature?**
`/query <text>` — it goes straight to the owners. Support chat:
@ForgeSupport. News: @ForgeUpdates.
