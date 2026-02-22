#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status != 200:
            raise RuntimeError(f"telegram send failed with status {resp.status}")


def build_message(summary: dict) -> str:
    target = summary.get("target_year")
    hits = summary.get("target_year_hits", [])
    errors = summary.get("fetch_errors", [])

    lines: list[str] = []
    if hits:
        lines.append(f"[OU IST] Detected {target}年度 募集要項")
        for item in hits:
            text = item.get("text", "")
            url = item.get("url", "")
            lines.append(f"- {text}: {url}")
    elif errors:
        lines.append("[OU IST] Check failed (fetch error)")
        for err in errors:
            lines.append(f"- {err}")
    else:
        lines.append(f"[OU IST] No update for {target}年度")

    return "\n".join(lines)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-file", required=True, help="Path to checker JSON summary")
    args = parser.parse_args()

    summary = json.loads(open(args.summary_file, "r", encoding="utf-8").read())
    detected = bool(summary.get("detected", False))
    errors = summary.get("fetch_errors", [])
    heartbeat = env_flag("HEARTBEAT_NOTIFY", default=True)
    should_notify = detected or bool(errors) or heartbeat
    if not should_notify:
        print("No notification needed.")
        return 0

    message = build_message(summary)
    if heartbeat and not detected and not errors:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        message = f"{message}\n- heartbeat: workflow is running ({ts})"

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return 1

    send_telegram(bot_token, chat_id, message)
    print("Sent Telegram notification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
