# Troubleshooting

## "It doesn't do anything when I send a command"

1. Check the exact syntax with `/help` (the menu shows arguments and
   examples).
2. Check where you sent it — `/hunt`, `/start` registration are
   **DM-only**.
3. Make sure you are registered (`/start`) before any other command.
4. If the bot was restarted or is under maintenance, wait a moment and
   retry; `/botstats` shows uptime.

## Stuck states

| Symptom | Fix |
| --- | --- |
| Frozen battle | `/clear` |
| Frozen or stuck trade | `/canceltrade` (alias `/tradecancel`), then `/clear` |
| Stuck in a wizard/prompt | `/cancel` |
| Hunt says you are in a battle | Finish or flee the battle, then `/hunt` |
| Hunt panel you do not want | `/close` (reopen with `/open`) |
| In an old Safari session | `/exit` |
| Training mode you did not mean to enable | `/evtrain stop` |

## Captcha problems

- A captcha replaces the spawn when the anti-bot check triggers — solve it
  and hunt again.
- Ignoring a captcha never adds a strike — it just reappears on your next
  hunt. Only an answer that is wrong or faster than 30 seconds costs a
  strike (5m → 15m → 24h).
- Typed the word but not the code (or the code but not the word)? The bot
  replies with the exact format to use — that reply is a hint, not a
  strike.
- If it keeps triggering, slow down between hunts and answer promptly.

## Membership gate

`/daily`, `/weekly` and `/redeem` check that you joined the bot's required
channel and group. Use the **join** buttons in the gate message, then tap
**I Joined** — the bot re-checks and runs your command.

## Buttons say "message is not modified" / "query is too old"

Those are stale-button noise from Telegram: the message changed or the tap
arrived too late. Just send the command again. They are harmless and are
suppressed in logs.

## Missing coins or items after a purchase

Check `/myinv` (items) and `/mystats` (coins). Purchases are applied
atomically — if a tap did nothing, the balance check failed (usually not
enough coins). If it persists, `/query <what happened>`.

## The bot is slow or unresponsive

- `/botstats` for uptime and activity.
- Heavy moments are usually sprite/image generation; retry once.
- If it is down entirely, check @ForgeUpdates for maintenance notices.

## Wrong bot / second deployment

If you run your own copy of this repo, remember that **one bot token can
only poll from one process**. A second deployment on the same token
receives no updates (the log warns about webhook conflicts). Use a
separate token for test deployments.

## Still stuck?

Send `/query <clear description>` in the bot — it reaches the owners — or
ask in @ForgeSupport.
