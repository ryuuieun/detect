#!/usr/bin/env python3
"""
Detect whether Osaka University IST master's admission guidelines
for a new academic year have been published.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


DEFAULT_URLS = [
    "https://www.ist.osaka-u.ac.jp/japanese/examinees/admission/",
]

USER_AGENT = "Mozilla/5.0 (compatible; ou-ist-guidelines-checker/1.0)"


def _to_half_width_digits(text: str) -> str:
    table = str.maketrans("０１２３４５６７８９", "0123456789")
    return text.translate(table)


def _reiwa_to_year(reiwa: int) -> int:
    # Reiwa 1 = 2019
    return reiwa + 2018


def extract_years(text: str) -> list[int]:
    text = _to_half_width_digits(text)
    years: set[int] = set()

    for m in re.finditer(r"(20\d{2})\s*年度", text):
        years.add(int(m.group(1)))

    for m in re.finditer(r"令和\s*([0-9]{1,2})\s*年度?", text):
        years.add(_reiwa_to_year(int(m.group(1))))

    for m in re.finditer(r"\((20\d{2})\)", text):
        years.add(int(m.group(1)))

    return sorted(years)


def normalize_space(text: str) -> str:
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Candidate:
    url: str
    text: str
    years: tuple[int, ...]

    @property
    def key(self) -> str:
        return f"{self.url}::{self.text}"


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_anchor = False
        self._href = ""
        self._parts: list[str] = []
        self.anchors: list[tuple[str, str]] = []
        self.page_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href") or ""
        self._in_anchor = True
        self._href = href
        self._parts = []

    def handle_data(self, data: str) -> None:
        if data:
            self.page_text_parts.append(data)
        if self._in_anchor:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._in_anchor:
            return
        text = normalize_space("".join(self._parts))
        self.anchors.append((self._href, text))
        self._in_anchor = False
        self._href = ""
        self._parts = []


def fetch_html(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def is_relevant(text: str, url: str) -> bool:
    t = normalize_space(text)
    u = url.lower()

    has_guideline_term = any(k in t for k in ("募集要項", "募集要项"))
    has_year_hint = bool(extract_years(t)) or ("年度" in t)
    has_guideline_url = any(
        k in u for k in ("guideline", "admission", "examinees", "bosyu", "youkou")
    )

    return has_guideline_term and (has_year_hint or has_guideline_url)


def extract_candidates(base_url: str, html: str) -> list[Candidate]:
    parser = AnchorParser()
    parser.feed(html)

    candidates: list[Candidate] = []
    seen_keys: set[str] = set()

    for href, text in parser.anchors:
        full_url = urllib.parse.urljoin(base_url, href)
        merged = f"{text} {full_url}"
        if not is_relevant(merged, full_url):
            continue
        years = tuple(extract_years(merged))
        item = Candidate(url=full_url, text=normalize_space(text), years=years)
        if item.key in seen_keys:
            continue
        seen_keys.add(item.key)
        candidates.append(item)

    return candidates


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def flatten(items_by_url: dict[str, list[Candidate]]) -> list[Candidate]:
    out: list[Candidate] = []
    for items in items_by_url.values():
        out.extend(items)
    return out


def year_hit(items: Iterable[Candidate], target_year: int) -> list[Candidate]:
    return [x for x in items if target_year in x.years]


def current_default_target_year(now: datetime) -> int:
    # For Japanese admissions pages, "new year" usually means next fiscal year listing.
    return now.year + 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Check new OU IST master's guidelines postings.")
    p.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Page URL to scan (repeatable). Defaults to official admission pages.",
    )
    p.add_argument(
        "--state",
        default=".ou_ist_guidelines_state.json",
        help="State JSON path for baseline and change detection.",
    )
    p.add_argument(
        "--target-year",
        type=int,
        default=None,
        help="Target academic year to detect (e.g., 2027). Default: current year + 1.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    p.add_argument(
        "--alert-on-first-run",
        action="store_true",
        help="If state file does not exist, treat current findings as detected.",
    )
    p.add_argument(
        "--print-json",
        action="store_true",
        help="Print machine-readable JSON summary.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    urls = args.urls or DEFAULT_URLS
    state_path = Path(args.state)
    now = datetime.now()
    target_year = args.target_year or current_default_target_year(now)

    all_items: dict[str, list[Candidate]] = {}
    fetch_errors: list[str] = []

    for url in urls:
        try:
            html = fetch_html(url, timeout=args.timeout)
            all_items[url] = extract_candidates(url, html)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            fetch_errors.append(f"{url}: {exc}")
            all_items[url] = []

    current_items = flatten(all_items)
    current_keys = {x.key for x in current_items}
    target_hits = year_hit(current_items, target_year)

    state = load_state(state_path)
    previous_keys = set(state.get("seen_keys", []))
    first_run = not bool(state)
    new_items = [x for x in current_items if x.key not in previous_keys]

    detected = bool(target_hits or (new_items and (args.alert_on_first_run or not first_run)))
    if first_run and not args.alert_on_first_run:
        detected = bool(target_hits)

    new_state = {
        "updated_at": now.isoformat(timespec="seconds"),
        "urls": urls,
        "target_year": target_year,
        "seen_keys": sorted(current_keys),
        "items": [asdict(x) for x in current_items],
    }
    save_state(state_path, new_state)

    summary = {
        "detected": detected,
        "first_run": first_run,
        "target_year": target_year,
        "target_year_hits": [asdict(x) for x in target_hits],
        "new_items": [asdict(x) for x in new_items],
        "fetch_errors": fetch_errors,
    }

    if args.print_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        if fetch_errors:
            print("WARN: Some pages could not be fetched:")
            for err in fetch_errors:
                print(f"- {err}")
        if detected:
            print(f"DETECTED: possible new guidelines found (target year: {target_year}).")
        else:
            print(f"NO_UPDATE: no new target-year posting found (target year: {target_year}).")
        print(f"Scanned {len(urls)} page(s), found {len(current_items)} candidate item(s).")
        if first_run:
            print(f"Initialized state at: {state_path}")

    if fetch_errors and not current_items:
        return 1
    return 2 if detected else 0


if __name__ == "__main__":
    sys.exit(main())
