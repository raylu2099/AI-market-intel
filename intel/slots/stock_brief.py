"""
Per-stock news slots: stocks_pre and stocks_post.

Same two-step approach: search_articles() for real URLs, then translate
headlines per-ticker. One Telegram message per ticker.
"""
from __future__ import annotations

from ..config import Config
from ..prices import Quote, fetch_quotes
from ..search import SearchQuery
from ..storage import dedupe_articles
from ..summary import search_and_translate
from ..telegram import split_message
from ..timeutil import now_pt, today_str
from .base import SlotResult, archive_articles


CATEGORY = "stocks"
STOCK_DOMAINS = [
    "cnbc.com", "investing.com", "marketwatch.com", "finance.yahoo.com",
    "barrons.com", "seekingalpha.com", "thestreet.com",
    "businessinsider.com", "benzinga.com", "investors.com",
    "reuters.com", "bloomberg.com", "wsj.com",
]


def _queries(ticker: str, name: str) -> list[SearchQuery]:
    return [
        SearchQuery(
            prompt=(
                f"Find the most important recent news about {name} ({ticker}) "
                f"stock: earnings results, analyst rating changes and price "
                f"targets, product launches, regulatory developments, "
                f"executive moves, partnerships, and market-moving events."
            ),
            domain_filter=STOCK_DOMAINS,
            recency="day",
            max_tokens=80,
            search_context="high",
        ),
    ]


def _format_price_line(q: Quote, label: str) -> str:
    if not q.ok:
        return f"价格: — · {label}"
    assert q.last is not None and q.pct is not None
    arrow = "🟢" if q.pct >= 0 else "🔴"
    return f"{arrow} ${q.last:.2f} ({q.pct:+.2f}%) · {label}"


def _run_stock_slot(
    cfg: Config,
    slot_name: str,
    header_label: str,
    price_label: str,
) -> SlotResult:
    date_str = today_str(cfg.market_tz)
    pt = now_pt()
    quotes = {q.ticker: q for q in fetch_quotes(cfg.watchlist)}

    all_articles = []
    messages = []
    for ticker, name in cfg.watchlist:
        chinese_text, articles = search_and_translate(
            cfg, _queries(ticker, name), context=f"{name} ({ticker})"
        )
        articles = dedupe_articles(articles)
        archive_articles(
            cfg, CATEGORY, date_str, articles,
            slot_sub=f"{ticker}_{slot_name}",
        )
        all_articles.extend(articles)

        q = quotes.get(ticker, Quote(ticker, name))
        price_line = _format_price_line(q, price_label)
        header = (
            f"📈 <b>{name} · {ticker}</b> — {header_label} "
            f"({pt:%a %m/%d})"
        )
        body = f"{header}\n{price_line}\n\n📰 <b>要闻 ({len(articles)} 篇)</b>\n{chinese_text}"
        messages.extend(split_message(body))

    return SlotResult(
        slot=slot_name,
        category=CATEGORY,
        date_str=date_str,
        articles=all_articles,
        messages=messages,
    )


def run_stocks_pre(cfg: Config) -> SlotResult:
    return _run_stock_slot(cfg, "stocks_pre", "盘前要闻", "昨收")


def run_stocks_post(cfg: Config) -> SlotResult:
    return _run_stock_slot(cfg, "stocks_post", "盘后要闻", "收盘")
