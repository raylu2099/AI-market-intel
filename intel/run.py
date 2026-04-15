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
from .slots import china_open, market_close
from .storage import save_push
from .telegram import send_message


SLOTS = {
    "china_open": china_open,
    "close": market_close,
    # Other slots will be added in Phase 3
}


def _log(msg: str) -> None:
    sys.stderr.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    sys.stderr.flush()


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in SLOTS:
        sys.stderr.write(
            f"Usage: {sys.argv[0]} {{{'|'.join(SLOTS)}}}\n"
            f"Env: MARKET_INTEL_DRY=1 to skip Telegram send.\n"
        )
        return 1

    slot_name = sys.argv[1]
    dry = os.environ.get("MARKET_INTEL_DRY") == "1"
    cfg = load_config()

    try:
        t0 = time.time()
        result = SLOTS[slot_name].run(cfg)
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
