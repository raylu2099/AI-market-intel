"""
Main entry point. Dispatches to a slot by name.

Usage:
    python -m intel.run <slot_name>

Env:
    MARKET_INTEL_DRY=1    Print messages to stdout instead of sending to Telegram
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime

from .config import load_config
from .cost_tracker import save_daily_costs
from .slots import china_open, market_brief, market_close, stock_brief
from .slots import weekly_review, watchdog
from .storage import save_push
from .telegram import send_message
from .urgency import get_vix, urgency_banner


def _make_runners(cfg):
    return {
        "premarket": lambda: market_brief.run_market_brief(cfg, market_brief.PREMARKET_SPEC),
        "open": lambda: market_brief.run_market_brief(cfg, market_brief.OPEN_SPEC),
        "midday": lambda: market_brief.run_market_brief(cfg, market_brief.MIDDAY_SPEC),
        "stocks_pre": lambda: stock_brief.run_stocks_pre(cfg),
        "stocks_post": lambda: stock_brief.run_stocks_post(cfg),
        "china_open": lambda: china_open.run(cfg),
        "close": lambda: market_close.run(cfg),
        "weekly_review": lambda: weekly_review.run(cfg),
        "watchdog": lambda: watchdog.run(cfg),
    }


def _log(msg: str) -> None:
    sys.stderr.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    sys.stderr.flush()


def main() -> int:
    # Support --config <name> for multi-config (#14)
    args = sys.argv[1:]
    config_name = None
    if "--config" in args:
        idx = args.index("--config")
        if idx + 1 < len(args):
            config_name = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    cfg = load_config(config_name=config_name)
    runners = _make_runners(cfg)

    if len(args) != 1 or args[0] not in runners:
        sys.stderr.write(
            f"Usage: {sys.argv[0]} [--config <name>] <slot>\n"
            f"Slots: {', '.join(runners)}\n"
            f"Env: MARKET_INTEL_DRY=1 to skip Telegram send.\n"
        )
        return 1

    slot_name = args[0]
    dry = os.environ.get("MARKET_INTEL_DRY") == "1"

    try:
        t0 = time.time()
        result = runners[slot_name]()
        elapsed = time.time() - t0
        _log(
            f"slot={slot_name} articles={len(result.articles)} "
            f"analysis_chars={len(result.analysis_md or '')} "
            f"messages={len(result.messages)} elapsed={elapsed:.1f}s"
        )
    except Exception as e:
        _log(f"slot={slot_name} FAILED: {e}")
        traceback.print_exc(file=sys.stderr)
        # P1: notify user of failure via Telegram
        try:
            err_msg = (
                f"⚠️ <b>market-intel 异常</b>\n\n"
                f"slot: <b>{slot_name}</b>\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"错误: {str(e)[:200]}\n"
                f"操作: 请检查 logs/slot.log"
            )
            send_message(cfg, err_msg)
        except Exception:
            pass
        return 2

    # Save push record and cost data
    save_push(cfg, result.date_str, slot_name, result.messages)
    save_daily_costs(cfg, slot_name)

    # Skip empty results silently (e.g. watchdog with no alert)
    if not result.messages:
        return 0

    # P2: VIX-driven urgency banner
    vix = get_vix()
    banner = urgency_banner(vix)
    if banner and result.messages:
        result.messages[0] = banner + result.messages[0]

    # P10: Cold start guidance — first 7 days
    _add_cold_start_marker(cfg, result)

    if dry:
        for i, m in enumerate(result.messages, 1):
            if i > 1:
                print("\n---[SPLIT]---\n")
            print(m)
        return 0

    total = len(result.messages)
    for i, m in enumerate(result.messages, 1):
        # P5: Add message count marker to last message
        if i == total and total > 1:
            m = m.rstrip() + f"\n\n<i>[{i}/{total}]</i>"
        elif total > 1:
            m = m.rstrip() + f"\n\n<i>[{i}/{total}]</i>"

        if send_message(cfg, m):
            _log(f"slot={slot_name} part {i}/{total} sent ({len(m)} chars)")
        else:
            _log(f"slot={slot_name} part {i}/{total} TG send FAILED")
            return 3

    return 0


def _add_cold_start_marker(cfg, result):
    """P10: Add day-N marker during first 7 days of operation."""
    analyses_dir = cfg.analyses_dir("china")
    if not analyses_dir.exists():
        day_count = 1
    else:
        day_count = len(list(analyses_dir.glob("*.md")))
    if day_count <= 7 and result.messages:
        marker = f"📌 <i>系统第 {day_count} 天运行。历史对比功能将在第 30 天后完全生效。</i>\n\n"
        result.messages[0] = marker + result.messages[0]


if __name__ == "__main__":
    sys.exit(main())
