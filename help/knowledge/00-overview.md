# Forge — what this bot is

Forge (Telegram username **@PokeForgebot**) is a Pokémon catching, collecting
and battling Telegram bot. Players register, hunt wild Pokémon, catch them
with balls, build teams, trade with friends, fight gym leaders and climb
leaderboards.

Everything in the bot is driven by slash commands with the `/` prefix.
Some commands work everywhere, some only in a group, some only in the bot's
private chat (DM).

## The five minute version

1. `/start` with the bot in **private chat** — register your trainer.
2. `/hunt` in **private chat** — a wild Pokémon appears.
3. Tap **Battle It**; use the **Ball** button in the battle screen to catch,
   or defeat it to earn EXP and coins.
4. `/mypokemons` — see what you own, `/myteam` — build a team of six.
5. `/daily`, `/quests`, `/achievements` — earn coins and rewards every day.
6. `/help` — the full in-bot command menu, `/leaderboard` — the rankings.

## Where things live

| What you want | Where |
| --- | --- |
| Play the game (hunt, catch, battle) | Private chat with the bot |
| Daily rewards, quests, games | Main group (see `/daily` notes) |
| Full command menu | `/help` |
| Bug reports and ideas | `/query <text>` |
| Human support | @ForgeSupport |
| News and updates | @ForgeUpdates |

## Command families

- **Getting started** — `/start` `/help` `/mystats` `/myinv` `/rename` `/query` `/clear`
- **Catching** — `/hunt` `/open` `/close` `/safari` `/enter` `/exit` `/evtrain`
- **Battles** — `/battle` `/challenge` `/gym` `/gymbattle` `/analyze` `/zmine`
- **Collection** — `/mypokemons` `/data` `/details` `/stats` `/pc` `/search` `/filter`
- **Teams** — `/myteam` `/teams` `/newteam` `/move` `/equip` `/chart` `/bestnat`
- **Breeding** — `/daycare` `/breed` `/eggs` `/hatch` `/walk` `/warm` `/care` `/breedhelp`
- **Economy** — `/shop` `/buy` `/sell` `/daily` `/weekly` `/rewards` `/redeem` `/referral`
- **Trading** — `/trade` `/canceltrade` `/tradehistory`
- **Social** — `/faction` `/quest` `/achievements` `/guess` `/leaderboard`
- **Regions** — `/travel`

The complete generated index of every registered command lives in
`knowledge/generated/commands.md`, and the bot's own `/help` menu is
mirrored in `knowledge/generated/help-menu.md`.

## What this helper will and will not do

It answers questions about **the Forge bot only** — commands, features,
mechanics, how to do things, and why something may not be working. It will
not talk about unrelated topics, and it never shares credentials, tokens,
database details or other internal configuration.
