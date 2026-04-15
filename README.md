# market-intel

A personal, self-hosted market intelligence system. Runs on cron, archives daily
news sources to a local corpus, and uses Claude (via `claude -p` or the Anthropic
API) to produce trading-grade analysis with historical context.

Built to run on a Synology NAS, but portable to any Linux box with Python 3.10+.

## What it does

Every trading day the system pushes a set of scheduled briefings to Telegram:

| Slot | Time (PT) | Weekday | What |
|------|-----------|---------|------|
| `premarket`   | 06:00 | Mon–Fri | US pre-market summary, macro snapshot, today's econ calendar |
| `open`        | 06:30 | Mon–Fri | US market open headlines |
| `midday`      | 09:30 | Mon–Fri | Mid-session watchlist + flow |
| `stocks_pre`  | 05:30 | Mon–Fri | Per-stock pre-market news (one message per ticker) |
| `close`       | 13:00 | Mon–Fri | **Deep Claude analysis** of the US session close |
| `stocks_post` | 13:30 | Mon–Fri | Per-stock post-close news |
| `china_open`  | 18:30 | Daily   | **Deep Claude analysis** of China politics / economy / military, with 3-persona output and rolling historical comparison |

The two slots marked "deep Claude analysis" load the last 30 days of archived
articles plus the system's own prior analyses, and produce a structured brief
in three analyst voices (macro narrative / Bridgewater-style positions /
geopolitical intel). All other slots use Perplexity for a lightweight summary
but still archive their source articles for future cross-referencing.

The value of this system compounds with time. On day 1 all you have is today's
news. By month 6 you have a searchable corpus of ~5,000 source articles,
cross-referenced to your own past analyses, and Claude can make "this looks
like the pattern we saw in February" observations grounded in retrievable
evidence.

## Architecture

```
┌──────────┐   ┌──────────┐   ┌─────────────┐   ┌──────────┐   ┌──────────┐
│  cron    │ → │ search   │ → │ fetch       │ → │ analyze  │ → │ push     │
│          │   │ (pplx)   │   │ (trafilat.) │   │ (claude) │   │ (telegr) │
└──────────┘   └────┬─────┘   └──────┬──────┘   └────┬─────┘   └──────────┘
                    ↓                ↓               ↓
              URL list         article JSONL    analysis MD
                                                      ↓
                                        data/analyses/... (becomes context
                                        for future analyses)
```

- **Perplexity** is used only as a search probe. We take its `search_results`
  field — real URLs with title, publisher, date, and snippet — and ignore its
  synthesized answer text.
- **trafilatura** fetches full article bodies where possible. Bot-blocked or
  paywalled sources (Reuters, FT, WSJ) fall back to the Perplexity snippet, and
  the record is tagged `paywalled: true`. The analyst prompt explicitly
  distinguishes first-hand articles from third-party snippets.
- **Claude** (via `claude -p` on a Max/Pro subscription by default, or via the
  Anthropic API if you prefer) reads today's articles plus the last 30 days of
  archive + past analyses, and emits a structured three-persona brief.
- **Telegram** is the delivery surface. Long briefs are auto-split at paragraph
  boundaries to stay under the 4096-char limit.

## Storage layout

Everything under `data/` is plain JSONL and Markdown — no database, easy to
back up, easy to grep.

```
data/
├── sources/
│   ├── china/YYYY-MM-DD/articles.jsonl
│   ├── market/YYYY-MM-DD_<slot>/articles.jsonl
│   └── stocks/<TICKER>/YYYY-MM-DD_<pre|post>/articles.jsonl
├── analyses/
│   ├── china/YYYY-MM-DD.md
│   └── market_close/YYYY-MM-DD.md
└── pushes/YYYY-MM-DD/<slot>.txt
```

Each article record looks like:

```json
{
  "id": "sha1-of-url",
  "url": "https://www.scmp.com/...",
  "title": "...",
  "publisher": "South China Morning Post",
  "date": "2026-04-15",
  "snippet": "...",
  "body": "full article text or null",
  "fetched": true,
  "paywalled": false,
  "fetched_at": "2026-04-15T18:30:07Z"
}
```

## Setup

```bash
# 1. Clone
git clone https://github.com/<you>/AI-market-intel.git
cd AI-market-intel

# 2. One-shot setup: creates venv, installs deps, copies .env.example
./setup.sh

# 3. Edit secrets
$EDITOR .env

# 4. Smoke-test one slot without sending Telegram
MARKET_INTEL_DRY=1 ./bin/run-slot.sh china_open

# 5. Live-send one slot
./bin/run-slot.sh china_open

# 6. Install cron entries (idempotent, works on Synology or standard Linux)
./bin/install-cron.sh
```

## Requirements

- Python 3.10+
- `claude` CLI (for Claude analyst, default runner) OR an Anthropic API key
- A Perplexity API key
- A Telegram bot token and your chat ID

## Cost profile

For the default configuration:

- **Perplexity**: ~200 `sonar` calls/month at ~$0.01 each → **~$2–3/month**
- **Claude Max subscription**: 2 deep analysis runs/day (china_open + close)
  × ~20k tokens input / 3k tokens output each → modest load on your Max quota,
  typically <20% of daily limit
- **Telegram**: free

Total incremental cost: **~$2–3/month** plus whatever Claude Max subscription
you already pay for.

If you'd rather not touch your Max quota, set `CLAUDE_RUNNER=api` in `.env`
and provide `ANTHROPIC_API_KEY`. Expect ~$5–10/month for Sonnet-4.6 analysis
calls.

## Not included / known limitations

- Reuters / FT / WSJ articles are archived as **snippets only** (~200 chars),
  not full text. Their bot protection blocks automated fetching. If this is a
  problem for your use case, a paid news API like NewsAPI.ai or EventRegistry
  can provide licensed full-text access for ~$200+/month.
- First 7 days of running, the "historical comparison" sections will show
  "data accumulating" placeholders. Meaningful comparison kicks in around day
  30.
- The analyst is opinionated and will make specific trading calls. Treat its
  output as one input among many, not a trade signal.

## License

MIT. See [LICENSE](LICENSE).

## Acknowledgements

Uses [Claude Code](https://claude.com/claude-code) as the analyst runtime,
[Perplexity](https://perplexity.ai) for web search, and
[trafilatura](https://trafilatura.readthedocs.io/) for article extraction.
