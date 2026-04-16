"""
Perplexity as a search probe. We extract the real URL list from
`search_results`, not the synthesized answer, and return Article records.

Running multiple queries against different angles is what gives us source
diversity — a single query tends to cluster on one domain.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass

from .config import Config
from .storage import Article


PPLX_ENDPOINT = "https://api.perplexity.ai/chat/completions"


@dataclass
class SearchQuery:
    prompt: str
    domain_filter: list[str] | None = None
    recency: str = "day"
    max_tokens: int = 100
    search_context: str = "high"


def _call(cfg: Config, query: SearchQuery) -> dict:
    body: dict = {
        "model": cfg.pplx_model_search,
        "messages": [{"role": "user", "content": query.prompt}],
        "max_tokens": query.max_tokens,
        "temperature": 0.1,
        "web_search_options": {"search_context_size": query.search_context},
    }
    if query.recency:
        body["search_recency_filter"] = query.recency
    if query.domain_filter:
        body["search_domain_filter"] = query.domain_filter

    req = urllib.request.Request(
        PPLX_ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg.perplexity_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        cost = data.get("usage", {}).get("cost", {}).get("total_cost", 0)
        if cost:
            print(f"[cost] search: ${cost:.5f}", file=sys.stderr)
        return data
    except Exception as e:
        print(f"[search] perplexity call failed: {e}", file=sys.stderr)
        return {}


def _publisher_from_url(url: str) -> str:
    try:
        host = url.split("/")[2]
        if host.startswith("www."):
            host = host[4:]
        if host.startswith("amp."):
            host = host[4:]
        return host
    except Exception:
        return ""


def search_articles(cfg: Config, queries: list[SearchQuery]) -> list[Article]:
    """
    Run multiple queries, dedupe by URL, return Article records.
    Articles start in unfetched state (fetched=False, body=None).
    """
    by_id: dict[str, Article] = {}
    for q in queries:
        resp = _call(cfg, q)
        if not resp:
            continue
        results = resp.get("search_results") or []
        for r in results:
            url = (r.get("url") or "").strip()
            if not url:
                continue
            aid = Article.make_id(url)
            if aid in by_id:
                continue
            by_id[aid] = Article(
                id=aid,
                url=url,
                title=(r.get("title") or "").strip(),
                publisher=_publisher_from_url(url),
                date=(r.get("date") or "").strip(),
                snippet=(r.get("snippet") or "").strip(),
                source="perplexity",
            )
    return list(by_id.values())
