# Restricted commands (owner / sudo / admin)

These commands exist in the bot but are **not for regular players** — they
check the caller's role and reply with an error (or nothing) for everyone
else. This helper will not help anyone bypass those checks.

## Moderator tools (sudo or owner)

| Command | Purpose |
| --- | --- |
| `/mt` | Maintenance control — list modules, toggle maintenance per module or command |
| `/mt status` | Same maintenance screen |
| `/gban [reply \| @user \| id] [reason]` | Restrict all bot commands for a user |
| `/mute [reply \| @user \| id] <period> [reason]` | Timed restriction |
| `/ungban [reply \| @user \| id]` | Lift a restriction |
| `/gbanlist` | Everyone currently restricted |
| `/addsudo [reply \| @user \| id]` | Grant sudo access (owner) |
| `/rmsudo [reply \| @user \| id]` | Revoke sudo access (owner) |
| `/sudos` (alias `/sudolist`) | List every sudo user and the owner |
| `/adminhelp` | The admin command surface, with pages |

## Owner tools

**Player and economy management**
`/add`, `/poke`, `/addcoins`, `/rmcoins`, `/setlevel`, `/addballs`,
`/rmballs`, `/additem`, `/rmitem`, `/addpoke`, `/rmpoke`, `/checkuser`,
`/padd`, `/premove`, `/padt`, `/pdel`

**Broadcasting and tooling**
`/broadcast` (alias `/bcast`), `/bstats`, `/emo`, `/novapin`,
`/testitems`, `/spawnmenu`, `/captcha_test`, `/gen` (redeem-code
generator)

**Dangerous resets**
`/reset [userid]` — reset one trainer's journey
`/wipe` — delete a user document entirely so `/start` runs brand new
`/resetdb` — wipe every collection (bot data and all users)

**Lifecycle shortcuts**
`/pvpseason` — preview and confirm the end of the current ranked season
`/instantbreed`, `/instahatch` — instantly breed / hatch for testing

## What players should use instead

| You want to | Use |
| --- | --- |
| See your own data | `/mystats`, `/myinv`, `/mypokemons` |
| Change something of yours | `/rename`, `/nickname`, `/setfav`, `/release` |
| Earn coins | `/daily`, `/weekly`, `/quest`, `/achievements` |
| Report a problem | `/query <text>` |
| Get help | `/help`, or ask @ForgeSupport |
