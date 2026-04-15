"""
china_open slot: deep Claude analysis of China politics/economy/military
news, archived daily, with rolling historical context.

Pipeline:
  1. Multi-query Perplexity search (politics / economy / military angles)
  2. Dedupe, attempt full-text fetch
  3. Archive to data/sources/china/<date>/articles.jsonl
  4. Load last 30 days of archived articles + past analyses as context
  5. Run Claude analyst with china_analyst.md system prompt
  6. Save analysis to data/analyses/china/<date>.md
  7. Format for Telegram, split, send
"""
from __future__ import annotations

from ..claude_analyst import analyze, load_prompt
from ..config import Config
from ..fetch import enrich_with_bodies
from ..search import SearchQuery, search_articles
from ..storage import dedupe_articles, load_recent_analyses, save_analysis
from ..telegram import split_message
from ..timeutil import BEIJING, now_bj, today_str
from .base import (
    SlotResult,
    archive_articles,
    format_article_block,
    format_history_index,
    load_recent_articles,
)


CATEGORY = "china"
SLOT_NAME = "china_open"
CORE_DOMAINS = [
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
    "scmp.com", "nikkei.com", "apnews.com", "economist.com",
]


def _queries() -> list[SearchQuery]:
    return [
        SearchQuery(
            prompt=(
                "Find the most important news about China's domestic politics, "
                "leadership, Party affairs, and government policy from the last "
                "24 hours."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                "Find the most important news about China's economy: GDP, "
                "fiscal/monetary policy, real estate, trade, consumption, "
                "industrial output, capital markets, and key company news "
                "from the last 24 hours."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                "Find the most important news about China's military, defense, "
                "PLA activities, Taiwan Strait, South China Sea, and strategic "
                "developments from the last 24 hours."
            ),
            domain_filter=CORE_DOMAINS,
            recency="day",
            max_tokens=100,
            search_context="high",
        ),
        SearchQuery(
            prompt=(
                "Find the most important news about China's foreign relations: "
                "US-China, Russia-China, EU, ASEAN, Middle East ties, and major "
                "diplomatic events from the last 24 hours."
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
    parts = [
        f"# Today's date (Beijing): {now_bj().strftime('%Y-%m-%d %A')}",
        "",
        f"# Today's articles ({len(today_articles)} items)",
        "",
        format_article_block(today_articles, include_body=True),
        "",
        f"# Historical article index (last {cfg.history_window_days} days, titles only)",
        "",
        format_history_index(history_articles),
        "",
        f"# Your past analyses (last {cfg.history_window_days} days)",
        "",
    ]
    if past_analyses:
        for date_str, content in past_analyses[-15:]:  # cap to 15 most recent
            parts.append(f"## Analysis from {date_str}")
            parts.append("")
            parts.append(content)
            parts.append("")
    else:
        parts.append("(no past analyses — this is day 1 of the system, "
                     "historical comparison must note 'data accumulating')")
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(
        "Produce the briefing now, following the system prompt's format "
        "exactly. Use article IDs [A1]..[A{}] for citations.".format(len(today_articles))
    )
    return "\n".join(parts)


def run(cfg: Config) -> SlotResult:
    date_str = today_str(BEIJING)

    # 1. Search
    articles = search_articles(cfg, _queries())
    articles = dedupe_articles(articles)

    # 2. Fetch bodies
    enrich_with_bodies(articles)

    # 3. Archive
    archive_articles(cfg, CATEGORY, date_str, articles)

    # 4. Load context: articles from last N days + past analyses
    history = load_recent_articles(cfg, CATEGORY, cfg.history_window_days)
    past_analyses = load_recent_analyses(cfg, CATEGORY, cfg.history_window_days)

    # 5. Claude analysis
    system_prompt = load_prompt(cfg, "china_analyst")
    user_prompt = _build_user_prompt(cfg, articles, history, past_analyses)
    analysis_md = analyze(cfg, system_prompt, user_prompt)

    # 6. Save analysis
    save_analysis(cfg, CATEGORY, date_str, analysis_md)

    # 7. Format for Telegram
    header = f"🇨🇳 <b>中国简报</b> — {now_bj():%a %m/%d} (Beijing)"
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
