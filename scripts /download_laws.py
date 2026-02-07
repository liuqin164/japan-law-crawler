#!/usr/bin/env python3
"""
Download ONLY active national tax laws (category_cd=13) from e-Gov API v2.
Filters out repealed, expired, or loss-of-effectiveness laws for knowledge base use.
"""

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
    parser = argparse.ArgumentParser(description="Download active national tax laws as JSON.")
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
    
    print(f"Fetching law list from {list_url}...")
    list_payload = fetch_json(list_url, timeout=args.timeout)
    
    # 适配 API 可能存在的 laws_response 包裹层
    target_data = list_payload.get("laws_response", list_payload)
    law_info_list = target_data.get("law_info_list", [])

    if not isinstance(law_info_list, list):
        raise RuntimeError("Unexpected response format: law_info_list is not a list.")

    print(f"Found {len(law_info_list)} total entries. Starting filtered download...")

    active_count = 0
    for law_info in iter_laws(law_info_list, args.limit):
        law_id, law_num, law_name = extract_law_info(law_info)
        if not law_id:
            continue

        try:
            law_payload = fetch_law_data(args.base_url, law_id, law_num, args.timeout)
            
            # --- 方案 B: 有效性过滤逻辑 ---
            # 兼容 API 嵌套结构获取 revision_info
            data_root = law_payload.get("law_data_response", law_payload)
            revision_info = data_root.get("revision_info", {})
            
            repeal_status = revision_info.get("repeal_status", "")
            amendment_type = str(revision_info.get("amendment_type", ""))

            # 过滤规则：
            # 1. repeal_status 为 Repeal(废止), Expire(失效), LossOfEffectiveness(丧失实效) 时跳过
            # 2. amendment_type 为 8 (代表废止法令本身) 时跳过
            if repeal_status in ["Repeal", "Expire", "LossOfEffectiveness"] or amendment_type == "8":
                print(f"Skipping inactive law: {law_name} (Status: {repeal_status or 'AmendmentType 8'})")
                continue

            # 保存有效法令
            safe_num = sanitize_filename(law_num or law_id)
            safe_name = sanitize_filename(law_name or law_id)
            filename = output_dir / f"{safe_num}_{safe_name}.json"
            
            filename.write_text(json.dumps(law_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved Active Law: {filename}")
            active_count += 1
            
        except Exception as exc:
            print(f"Error processing {law_id}: {exc}")
            continue

        time.sleep(args.sleep_seconds)

    print(f"\nTask Complete. Total active laws saved: {active_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        raise SystemExit(1)
