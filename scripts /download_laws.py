#!/usr/bin/env python3
"""
Download ALL active national tax laws from e-Gov API v2.
Fixed: Implemented pagination to fetch the entire list beyond the first 100 entries.
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
from typing import Any, Dict, List, Optional, Tuple

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

def fetch_law_data(base_url: str, law_id: str, law_num: Optional[str], timeout: int) -> Dict[str, Any]:
    params = {"law_full_text_format": "json", "response_format": "json", "extraction_target": "all"}
    law_url = build_url(base_url, f"law_data/{law_id}", params)
    try:
        return fetch_json(law_url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code != 404 or not law_num: raise
        fallback_url = build_url(base_url, f"law_data/{law_num}", params)
        return fetch_json(fallback_url, timeout=timeout)

def main() -> int:
    parser = argparse.ArgumentParser(description="Download ALL active tax laws with pagination.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-url", default="https://laws.e-gov.go.jp/api/2")
    parser.add_argument("--category-cd", default="013")
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 翻页抓取全量清单 ---
    all_tax_laws: List[Dict[str, Any]] = []
    offset = 1
    limit_per_page = 100 # API 最大单次返回数
    
    print("正在分批获取法令清单（由于数量较多，可能需要翻页）...")
    
    while True:
        list_params = {
            "response_format": "json",
            "offset": offset,
            "limit": limit_per_page
        }
        list_url = build_url(args.base_url, "laws", list_params)
        
        try:
            payload = fetch_json(list_url, timeout=args.timeout)
            resp = payload.get("laws_response", payload)
            laws = resp.get("law_info_list", [])
            
            if not laws:
                break # 没有更多数据了
            
            # 本地过滤国税分类
            target_cat = args.category_cd.zfill(3)
            current_page_tax = [l for l in laws if str(l.get("category_cd", "")).zfill(3) == target_cat]
            all_tax_laws.extend(current_page_tax)
            
            print(f"已扫描偏移量 {offset}，在当前页发现 {len(current_page_tax)} 部国税法令...")
            
            # 判断是否需要继续翻页
            if len(laws) < limit_per_page:
                break
            offset += limit_per_page
            
        except Exception as e:
            print(f"获取清单失败: {e}")
            break

    print(f"\n✅ 清单获取完成！在总计约 {offset+len(laws)} 部法令中，筛选出国税法令 {len(all_tax_laws)} 部。")

    # --- 下载详情 ---
    active_count = 0
    for law_info in all_tax_laws:
        law_id = law_info.get("law_id")
        law_num = law_info.get("law_num")
        law_name = law_info.get("law_name")
        
        try:
            law_payload = fetch_law_data(args.base_url, law_id, law_num, args.timeout)
            data_root = law_payload.get("law_data_response", law_payload)
            revision = data_root.get("revision_info", {})
            
            # 清洗：有效性检查
            if revision.get("repeal_status") in ["Repeal", "Expire", "LossOfEffectiveness"] or str(revision.get("amendment_type")) == "8":
                continue

            # 保存
            safe_num = sanitize_filename(law_num or law_id)
            safe_name = sanitize_filename(law_name or law_id)
            filename = output_dir / f"{safe_num}_{safe_name}.json"
            
            filename.write_text(json.dumps(law_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已保存: {safe_name}")
            active_count += 1
            
        except Exception as exc:
            print(f"跳过错误条目 {law_id}: {exc}")
            continue

        time.sleep(args.sleep_seconds)

    print(f"\n🚀 任务结束！共下载 {active_count} 部现行有效国税法令。")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
