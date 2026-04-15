"""Telegram bot API sender with auto-splitting for long messages."""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

from .config import Config


TG_MAX_CHARS = 4096
# Leave headroom; we'll split at paragraph boundaries at this size.
SAFE_CHARS = 3800


def split_message(text: str, limit: int = SAFE_CHARS) -> list[str]:
    """Split text into TG-safe chunks on paragraph (then line) boundaries."""
    if len(text) <= limit:
        return [text]
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


def send_message(cfg: Config, text: str, parse_mode: str = "HTML") -> bool:
    data = urllib.parse.urlencode(
        {
            "chat_id": cfg.telegram_chat_id,
            "text": text[:TG_MAX_CHARS],
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return bool(json.loads(resp.read().decode()).get("ok"))
    except Exception as e:
        print(f"[telegram] send failed: {e}", file=sys.stderr)
        return False


def send_long(cfg: Config, text: str, parse_mode: str = "HTML") -> tuple[int, int]:
    """Split and send. Returns (sent_count, total_count)."""
    parts = split_message(text)
    sent = 0
    for p in parts:
        if send_message(cfg, p, parse_mode=parse_mode):
            sent += 1
        else:
            break
    return sent, len(parts)
