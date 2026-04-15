"""
market_close slot: deep Claude analysis of the US market close with watchlist
focus. Same pipeline shape as china_open but different search queries and
prompt.
"""
from __future__ import annotations

from ..claude_analyst import analyze, load_prompt
from ..config import Config
from ..fetch import enrich_with_bodies
from ..search import SearchQuery, search_articles
from ..storage import dedupe_articles, load_recent_analyses, save_analysis
from ..telegram import split_message
from ..timeutil import now_pt, today_str
from .base import (
    SlotResult,
    archive_articles,
    format_article_block,
    format_history_index,
    load_recent_articles,
)


CATEGORY = "market_close"
SLOT_NAME = "close"
CORE_DOMAINS = [
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
    "cnbc.com", "barrons.com", "marketwatch.com", "seekingalpha.com",
    "apnews.com",
]


def _queries(cfg: Config) -> list[SearchQuery]:
    watchlist_names = ", ".join(name for _, name in cfg.watchlist)
    watchlist_tickers = ", ".join(t for t, _ in cfg.watchlist)
    return [
        SearchQuery(
            prompt=(
                "Find the most important news about the US stock market close "
                "today: S&P 500, Nasdaq, Dow Jones performance, sector rotation, "
                "and major market-moving events from the last 24 hours."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                f"Find news from the last 24 hours about these specific stocks: "
                f"{watchlist_names} ({watchlist_tickers}). Focus on earnings, "
                f"analyst rating changes, product events, and regulatory news."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                "Find news about US macro conditions from the last 24 hours: "
                "Federal Reserve speeches, CPI/PCE/NFP data, Treasury yields, "
                "dollar, oil, and gold."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
    ]


def _build_user_prompt(
    cfg: Config,
    today_articles: list,
    history_articles: list,
    past_analyses: list[tuple[str, str]],
) -> str:
    watchlist_str = ", ".join(f"{t} ({n})" for t, n in cfg.watchlist)
    parts = [
        f"# Today's date (US Pacific): {now_pt().strftime('%Y-%m-%d %A')}",
        f"# Watchlist: {watchlist_str}",
        "",
        f"# Today's articles ({len(today_articles)} items)",
        "",
        format_article_block(today_articles, include_body=True),
        "",
        f"# Historical article index (last {cfg.history_window_days} days)",
        "",
        format_history_index(history_articles),
        "",
        f"# Your past analyses (last {cfg.history_window_days} days)",
        "",
    ]
    if past_analyses:
        for date_str, content in past_analyses[-15:]:
            parts.append(f"## Analysis from {date_str}")
            parts.append("")
            parts.append(content)
            parts.append("")
    else:
        parts.append("(no past analyses — day 1 of operation, continuity "
                     "section should note 'data accumulating')")
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(
        "Produce the close briefing now, following the system prompt format. "
        "Cite with [A1]..[A{}].".format(len(today_articles))
    )
    return "\n".join(parts)


def run(cfg: Config) -> SlotResult:
    date_str = today_str(cfg.market_tz)

    articles = search_articles(cfg, _queries(cfg))
    articles = dedupe_articles(articles)
    enrich_with_bodies(articles)
    archive_articles(cfg, CATEGORY, date_str, articles)

    history = load_recent_articles(cfg, CATEGORY, cfg.history_window_days)
    past_analyses = load_recent_analyses(cfg, CATEGORY, cfg.history_window_days)

    system_prompt = load_prompt(cfg, "market_close_analyst")
    user_prompt = _build_user_prompt(cfg, articles, history, past_analyses)
    analysis_md = analyze(cfg, system_prompt, user_prompt)
    save_analysis(cfg, CATEGORY, date_str, analysis_md)

    header = f"🏁 <b>US Close</b> — {now_pt():%a %m/%d} 16:00 ET"
    full = f"{header}\n\n{analysis_md}"
    messages = split_message(full)

    return SlotResult(
        slot=SLOT_NAME,
        category=CATEGORY,
        date_str=date_str,
        articles=articles,
        messages=messages,
        analysis_md=analysis_md,
    )
