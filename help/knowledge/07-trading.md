# Trading and gifting

## Start a trade — /trade

**Reply to another trainer's message** in a group and send:

```
/trade
```

Requirements and limits:

- You must be registered (`/start`); the other trainer must be registered
  too, otherwise the bot says so.
- You cannot trade with yourself.
- Only **one active trade per person** — you or they must finish or cancel
  an existing trade first.
- The trade runs in the group chat where you started it.

### The flow

1. **Initiate** — you are auto-accepted (you are ready by default).
2. **Target accepts** — the other trainer taps Accept.
3. **Select your Pokémon** — numbered inline buttons with paging.
4. **Select their Pokémon** — same picker.
5. **Preview** — both sides see exactly what is on the table.
6. **Confirm** — each side confirms.
7. **Complete** — Pokémon swap, both collections updated.

Every step edits the same message, so a trade never spams the chat.

### Safety

- The preview shows **IVs** and other details of each side before anyone
  confirms, so you can see what you are actually getting.
- Each side must confirm independently — nobody can force a trade.
- Trades expire if abandoned.

## Cancelling

- `/canceltrade` or `/tradecancel` — cancel a pending trade.
- `/cancel` — generic "exit this wizard/dialog" also works in many places.

## History — /tradehistory

`/tradehistory` shows your past trades.

## Gifting

- `/give <coins>` — reply to someone and send `/give 100` to send coins.
- `/send_tm <TM>` — reply to someone and send `/send_tm 05` to send a TM.

Both trainers see the same flow, and each has to confirm. If a trade ever
looks stuck, `/clear` resets it for you.
