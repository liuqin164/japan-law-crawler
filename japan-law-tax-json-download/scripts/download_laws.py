#!/usr/bin/env python3
"""Download national tax laws (category_cd=13) from e-Gov API v2 and save JSON."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


def build_url(base_url: str, path: str, params: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}?{query}"


def fetch_json(url: str, timeout: int = 60) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def sanitize_filename(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^0-9A-Za-z_\-()\[\]【】]+", "_", value)
    value = value.strip("_")
    return value or "unknown"


def extract_law_info(law_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    law_id = law_info.get("law_id") or law_info.get("lawId")
    law_num = law_info.get("law_num") or law_info.get("lawNum")
    law_name = law_info.get("law_name") or law_info.get("lawName")
    return law_id, law_num, law_name


def iter_laws(law_info_list: Iterable[Dict[str, Any]], limit: Optional[int]) -> Iterable[Dict[str, Any]]:
    count = 0
    for item in law_info_list:
        yield item
        count += 1
        if limit is not None and count >= limit:
            break


def fetch_law_data(
    base_url: str,
    law_id: str,
    law_num: Optional[str],
    timeout: int,
) -> Dict[str, Any]:
    params = {
        "law_full_text_format": "json",
        "response_format": "json",
        "extraction_target": "all",
    }
    law_url = build_url(base_url, f"law_data/{law_id}", params)
    try:
        return fetch_json(law_url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code != 404 or not law_num:
            raise
        fallback_url = build_url(base_url, f"law_data/{law_num}", params)
        return fetch_json(fallback_url, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download national tax laws as JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory to save JSON files.")
    parser.add_argument("--base-url", default="https://laws.e-gov.go.jp/api/2")
    parser.add_argument("--category-cd", default="13")
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    list_params = {
        "category_cd": args.category_cd,
        "response_format": "json",
    }
    list_url = build_url(args.base_url, "laws", list_params)
    list_payload = fetch_json(list_url, timeout=args.timeout)
    law_info_list = list_payload.get("law_info_list", [])

    if not isinstance(law_info_list, list):
        raise RuntimeError("Unexpected response format: law_info_list is not a list.")

    for law_info in iter_laws(law_info_list, args.limit):
        law_id, law_num, law_name = extract_law_info(law_info)
        if not law_id:
            print("Skipping entry without law_id.")
            continue

        try:
            law_payload = fetch_law_data(args.base_url, law_id, law_num, args.timeout)
        except Exception as exc:  # pragma: no cover - log and continue
            print(f"Failed to fetch law data for {law_id}: {exc}")
            continue

        safe_num = sanitize_filename(law_num or law_id)
        safe_name = sanitize_filename(law_name or law_id)
        filename = output_dir / f"{safe_num}_{safe_name}.json"
        filename.write_text(json.dumps(law_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved {filename}")
        time.sleep(args.sleep_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
