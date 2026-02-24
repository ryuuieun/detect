#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import URLError


def send_telegram(
    bot_token: str,
    chat_id: str,
    text: str,
    timeout: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 2.0,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, data=payload, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"telegram send failed with status {resp.status}")
            return
        except (TimeoutError, URLError, RuntimeError) as exc:
            last_error = exc
            if attempt == retries:
                break
            wait_seconds = backoff_seconds * (2 ** (attempt - 1))
            print(
                f"Telegram notify attempt {attempt}/{retries} failed: {exc}. "
                f"Retrying in {wait_seconds:.1f}s..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(f"telegram send failed after {retries} attempts: {last_error}")


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
    parser.add_argument("--telegram-timeout", type=float, default=20.0)
    parser.add_argument("--telegram-retries", type=int, default=3)
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

    try:
        send_telegram(
            bot_token,
            chat_id,
            message,
            timeout=args.telegram_timeout,
            retries=args.telegram_retries,
        )
        print("Sent Telegram notification.")
        return 0
    except Exception as exc:
        print(f"Telegram notification failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
