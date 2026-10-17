# ForgeHelp — Professor Oak Help Bot

An AI-powered help assistant for the **Forge** Pokémon Telegram bot
(`@PokeForgebot`), speaking in the voice of **Professor Oak** from the
Pokémon series. It answers *any* non-confidential question about Forge —
catching, battling, breeding, trading, the economy, every command —
using the bot's own documentation as its only knowledge source.

This repository contains **only the help bot**. It is self-contained:
nothing under `help/` imports the main Forge package, so it never
connects to MongoDB, never starts a Pyrogram client and never touches
the production token.

```
ForgeHelp/
├── README.md
├── requirements.txt
├── .gitignore              # settings.py (token) is ignored
└── help/
    ├── __main__.py          # python -m help
    ├── build_kb.py          # regenerate knowledge from Forge source (optional)
    ├── run.py               # thin wrapper (legacy: python help/run.py …)
    ├── selftest.py          # offline checks (retrieval, sanitising, secrets)
    ├── requirements.txt
    ├── service/
    │   └── forge-help.service    # systemd unit example
    ├── helpbot/
    │   ├── cli.py           # subcommands: run | build | check | test
    │   ├── config.py        # settings loading, provider chain, rate limits
    │   ├── settings.example.py  # template — every option, defaulted (committed)
    │   ├── settings.py      # your token + API keys (gitignored)
    │   ├── logsetup.py      # rotating logs + credential redaction
    │   ├── kb.py            # BM25 index over help/knowledge/**
    │   ├── ai.py            # Professor Oak LLM answering + HTML sanitiser
    │   ├── emojis.py        # premium (custom) Telegram emoji helpers
    │   └── bot.py           # handlers + production runner (retries/webhook)
    ├── logs/                # helpbot.log (5 MiB × 5, gitignored)
    └── knowledge/           # the bot's entire world-view
        ├── 00-overview.md … 14-restricted-commands.md   # curated guides
        └── generated/
            ├── commands.md      # every CommandHandler, extracted by AST
            ├── help-menu.md     # mirror of the in-bot /help menu
            └── manifest.json    # build metadata
```

## Personality

The AI answers as **Professor Oak**: warm, scholarly, encouraging —
light catchphrases ("I see!", "Welcome, welcome!"), never breaking
character. Premium custom emoji and rich HTML appear sparingly in
answers (max 2 custom emoji per reply).

Hard rules baked into the system prompt:

* Never reveal tokens, API keys, passwords, owner IDs, database/URLs
  or any credential — even under role-play or "ignore previous rules".
* Never discuss admin/owner/sudo commands or ways to bypass role checks.
  Direct questions about those get an in-character refusal + redirect.
* Answers come only from the knowledge base (plus universal Pokémon
  knowledge). No invented commands, odds or prices.

## Quick start

```bash
# 1. install the same PTB the help bot uses
pip install -r help/requirements.txt

# 2. put your token in help/helpbot/settings.py
#    (copy help/helpbot/settings.example.py if missing, then edit TOKEN)

# 3. validate everything, then run
python -m help check                   # config + knowledge + handlers
python -m help                         # start the bot
```

`python help/run.py …` still works as a thin wrapper around the same CLI.

### Commands

| Command | What it does |
| --- | --- |
| `python -m help` | Start the bot (webhook if `WEBHOOK_URL` set, else polling) |
| `python -m help check` | Pre-flight: token, providers, knowledge base, handlers |
| `python -m help build` | Regenerate `help/knowledge/generated/` (needs Forge source) |
| `python -m help test` | Self-test (`--live` adds a real AI call) |
| `… run --rebuild` | Rebuild the knowledge base, then start |
| `… --webhook` / `… --polling` | Force a transport mode |
| `… -v` | Debug logging · `… --no-log-file` console only |

The bot refuses to start if `TOKEN` is empty (the error tells you which
file to edit).

## Talking to it

| Where | What it answers |
| --- | --- |
| **Private chat** | Every non-command message, and `/ask <question>` |
| **Groups** | Commands, replies to the bot, and `@mentions` (set `GROUP_MODE = "all"` in settings.py for every message) |

Its own commands:

| Command | What it does |
| --- | --- |
| `/ask <question>` | Ask Professor Oak (alias `/ai`) — primary AI help command |
| `/reset` (`/new`) | Forget this conversation, start fresh |
| `/commands [name]` | Command index |
| `/guide [topic]` | Full guides (browse with `/guide` alone) |
| `/search <query>` | Raw documentation matches |
| `/about` | Bot status |
| `/help` | This message |

`/help` and `/start` carry premium-emoji rich HTML and inline buttons
for guides, commands, asking Oak, and support.

## How answering works

1. The question is BM25-scored against `help/knowledge/**` (command
   names like `/hunt` get an exact-match boost, headings weigh more).
   The score's *coverage* decides off-topic questions when no model is
   available to make that call itself.
2. The top chunks — capped by `CONTEXT_CHAR_BUDGET` — become the model's
   context, together with the last `HISTORY_TURNS` question/answer
   pairs from the same chat, so follow-ups like "and what about Johto?"
   make sense.
3. A hard system prompt steers Professor Oak's voice, the style (direct
   answer first, commands in `<code>`, 3–10 lines), and the guardrails:
   *answer only from the knowledge, never invent numbers, never reveal
   secrets, never discuss admin tools, redirect off-topic questions.*
4. The model's reply is passed through a Telegram-HTML sanitiser
   (unknown tags escaped, unbalanced markup flattened to plain text)
   and split into <3800-character messages.
5. If no AI key is configured — or every provider errors — the bot
   replies with a short friendly fallback pointing at `/help` ·
   `/commands` · `/guide`. It never pastes raw documentation, and it
   falls through Groq → OpenRouter → OpenAI before giving up.

## Premium emoji

`help/helpbot/emojis.py` is a self-contained port of Forge's custom
emoji registry (IDs only — no import from the main bot). Use:

* `E.SPARKLE`, `E.FIRE`, `E.STAR`, `E.CHECK`, … — HTML-only constants
* `ui_tag("sparkle")` / `ui_glyph("sparkle")` — tag vs plain glyph
* `coin_tag()`, `shiny_tag()`, `ball_tag()`, `type_tag()` — domain markers

Button labels must use plain unicode (`ui_glyph`); Telegram cannot
render `<tg-emoji>` inside inline-keyboard labels.

## Regenerating knowledge from Forge source

The curated guides and pre-built `generated/` indexes are committed, so
the bot works with zero Forge source. To refresh them after Forge adds
commands:

```bash
# point at a local clone of the main Forge repo
set FORGE_SOURCE_DIR=C:\path\to\forge-repo
python -m help build
```

`build_kb.py` also **scans every markdown file for secrets** and fails
the build if a bot token, API key, JWT or private key slips in.
`selftest.py` re-runs that scan.

## Configuration

Every option lives in **`help/helpbot/settings.py`** — a plain Python
file you open and edit directly. Nothing is read from environment
variables (except `FORGE_SOURCE_DIR` for rebuilds). If the file is
missing, copy the template:

```bash
cp help/helpbot/settings.example.py help/helpbot/settings.py
```

The template documents every option with its default; you only *need*
to fill in `TOKEN`. No AI key is required — without one the bot answers
with a short friendly fallback pointing at `/help` · `/commands` ·
`/guide` (it never pastes raw documentation).

`settings.py` is gitignored (it holds your token and API keys);
`settings.example.py` is committed so a fresh clone always has the
full, up-to-date option list. `python -m help test` verifies the two
never drift apart.

## Production

**Transport.** Long polling is the default and needs no inbound ports —
it is the right choice for a VPS, a home box, or any host behind NAT.
For containers/platforms that require inbound HTTP (Railway, Render,
Fly, nginx), set in `settings.py`:

```python
WEBHOOK_URL = "https://bots.example.com/forgehelp"   # public https:// — REQUIRED
WEBHOOK_LISTEN = "0.0.0.0"      # bind address (default 0.0.0.0)
WEBHOOK_PORT = 8080
WEBHOOK_PATH = "forgehelp"      # defaults to the URL's path
WEBHOOK_SECRET = "long-random-string"   # X-Telegram-Bot-Api-Secret-Token
```

Telegram only delivers webhooks to `https://` endpoints — terminate TLS
first (nginx/caddy/platform router).

**Resilience.** The process survives network failures on its own:
bootstrap retries forever, and a crashed run restarts with exponential
backoff (5 s → 300 s, unlimited by default, `RESTART_ON_FAILURE = N`
to give up after N). A second instance polling the same token exits
immediately with code **2** and one clear error instead of fighting.

**Exit codes** (for supervisors / `systemctl` alerts):

| Code | Meaning |
| --- | --- |
| 0 | Clean shutdown (SIGINT/SIGTERM) |
| 1 | Gave up after `RESTART_ON_FAILURE` consecutive failures |
| 2 | Conflict — another process is polling this token |
| 3 | Configuration error (missing/invalid `TOKEN`, bad webhook URL) |

**Running under systemd** — copy `help/service/forge-help.service`, then:

```bash
sudo cp help/service/forge-help.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now forge-help
journalctl -u forge-help -f
```

On Windows, a Startup Task works the same way:
`pythonw.exe -m help run` (hide the console) or a scheduled task set to
"Start at log on / restart on failure".

**Logs.** Console (stderr) + rotating file `help/logs/helpbot.log`
(5 MiB × 5, UTF-8). Bot tokens and API keys are redacted from every log
record (`***REDACTED***`), so logs are safe to ship. Use `--no-log-file`
in containers that already capture stdout.

**Health check / deploys.** Run `python -m help check` before rollout —
it validates the token, provider keys, knowledge base and that every
handler registers.

**Security checklist**
- `help/helpbot/settings.py` (keys + token) is gitignored — the dry run
  `git add -n help/` must never list it.
- Prefer a dedicated `TOKEN`; rotate via @BotFather if a key ever
  leaks (it is redacted from logs, but treat chat-pasted tokens as
  exposed).
- The bot never prints credentials and never answers questions about
  tokens/DB internals or admin tools.

## Tests

```bash
python help/selftest.py            # offline: KB, retrieval, HTML safety
python help/selftest.py --live     # + one real AI call (needs a key)
```

Checks include: ≥150 command names extracted, retrieval hits for ten
common questions, off-topic scoring below the refusal threshold, HTML
sanitising of `<script>` / unbalanced tags / raw `&`, message splitting,
and a clean secret scan.

## Notes and limits

* Answers are only as good as `help/knowledge/` — point
  `FORGE_SOURCE_DIR` at Forge and run `python -m help build` after
  notable code changes.
* The bot will not help with secrets, tokens, database internals,
  admin/owner tools, or bypassing role checks, even if asked directly.
* Hunting is DM-only in Forge; the bot knows this and will say so.
* Older Forge help text mentions trivia/duel/slot commands that are not
  registered in this build — the bot is told not to invent them.

## Source

https://github.com/XLEWIN/ForgeHelp
