#!/usr/bin/env python3
"""
Download ONLY active national tax laws (category_cd=13) from e-Gov API v2.
Strategy: Uses /laws to get the full master list, then filters locally for category 013.
This avoids the '400 Bad Request' from the /keyword endpoint.
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

def extract_law_info(law_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    law_id = law_info.get("law_id") or law_info.get("lawId")
    law_num = law_info.get("law_num") or law_info.get("lawNum")
    law_name = law_info.get("law_name") or law_info.get("lawName")
    # 提取分类代码用于本地过滤
    category = law_info.get("category_cd") or law_info.get("categoryCd")
    return law_id, law_num, law_name, category

def fetch_law_data(base_url: str, law_id: str, law_num: Optional[str], timeout: int) -> Dict[str, Any]:
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
    parser = argparse.ArgumentParser(description="Download active national tax laws (Category 013).")
    parser.add_argument("--output-dir", required=True, help="Directory to save JSON files.")
    parser.add_argument("--base-url", default="https://laws.e-gov.go.jp/api/2")
    parser.add_argument("--category-cd", default="013") # 国税代码
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取全量清单
    list_params = {"response_format": "json"}
    list_url = build_url(args.base_url, "laws", list_params)
    
    print(f"正在从 {list_url} 获取全量法令清单...")
    try:
        list_payload = fetch_json(list_url, timeout=args.timeout)
    except Exception as e:
        print(f"获取清单失败: {e}")
        return 1

    target_data = list_payload.get("laws_response", list_payload)
    full_info_list = target_data.get("law_info_list", [])

    if not full_info_list:
        print("未获取到任何法令信息。")
        return 0

    # 2. 本地过滤出分类为 013 (国税) 的法令
    # zfill(3) 确保格式对齐 (如 '13' 变为 '013')
    target_category = args.category_cd.zfill(3)
    tax_laws = [
        item for item in full_info_list 
        if str(item.get("category_cd", "")).zfill(3) == target_category
    ]

    print(f"全量法令共 {len(full_info_list)} 条，筛选出国税法令 {len(tax_laws)} 条。")

    active_count = 0
    processed_count = 0
    
    for law_info in tax_laws:
        if args.limit is not None and processed_count >= args.limit:
            break
        
        law_id, law_num, law_name, _ = extract_law_info(law_info)
        if not law_id:
            continue

        try:
            # 下载法令详情
            law_payload = fetch_law_data(args.base_url, law_id, law_num, args.timeout)
            
            # 解析版本信息进行有效性检查 (方案 B)
            data_root = law_payload.get("law_data_response", law_payload)
            revision_info = data_root.get("revision_info", {})
            
            repeal_status = revision_info.get("repeal_status", "")
            amendment_type = str(revision_info.get("amendment_type", ""))

            # 过滤掉已废止、失效或属于废止件的法令
            if repeal_status in ["Repeal", "Expire", "LossOfEffectiveness"] or amendment_type == "8":
                print(f"跳过非现行法令: {law_name} ({repeal_status or '废止件'})")
                continue

            # 保存为 JSON 文件
            safe_num = sanitize_filename(law_num or law_id)
            safe_name = sanitize_filename(law_name or law_id)
            filename = output_dir / f"{safe_num}_{safe_name}.json"
            
            filename.write_text(json.dumps(law_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"成功保存现行法令: {filename}")
            
            active_count += 1
            processed_count += 1
            
        except Exception as exc:
            print(f"下载法令数据失败 {law_id}: {exc}")
            continue

        # 稍微暂停，避免请求过快
        time.sleep(args.sleep_seconds)

    print(f"\n任务完成！共保存 {active_count} 部现行有效国税法令。")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n用户中止了任务。")
        raise SystemExit(1)
