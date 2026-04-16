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
from .slots import china_open, market_brief, market_close, stock_brief
from .slots import weekly_review, watchdog
from .storage import save_push
from .telegram import send_message


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
        return 2

    # Save push record regardless of dry mode
    save_push(cfg, result.date_str, slot_name, result.messages)

    if dry:
        for i, m in enumerate(result.messages, 1):
            if i > 1:
                print("\n---[SPLIT]---\n")
            print(m)
        return 0

    for i, m in enumerate(result.messages, 1):
        if send_message(cfg, m):
            _log(f"slot={slot_name} part {i}/{len(result.messages)} sent ({len(m)} chars)")
        else:
            _log(f"slot={slot_name} part {i}/{len(result.messages)} TG send FAILED")
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
