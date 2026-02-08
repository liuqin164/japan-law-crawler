#!/usr/bin/env python3
"""
Japanese Law Downloader - Optimized for National Tax Knowledge Base.
- Supports Pagination (fetches all 8000+ law entries)
- Filters by Category (013 for National Tax)
- Filters by Validity (Only Active)
- Includes 'limit' parameter for testing
"""

import argparse
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

def fetch_json(url, timeout=60):
    # 增加 User-Agent 模拟浏览器，防止被 e-Gov 拦截
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (OpenClaw-Crawler)'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory to save JSON files")
    parser.add_argument("--limit", type=int, default=None, help="Stop after downloading N laws (for testing)")
    parser.add_argument("--category-cd", default="013", help="Category code, 013 is National Tax")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 第一步：获取全日本所有法令的 LawID 清单
    law_id_list = []
    offset = 1
    limit_per_page = 100
    
    print("🔍 阶段 1: 正在扫描全量法令索引 (翻页中)...", flush=True)
    
    while True:
        list_url = f"https://laws.e-gov.go.jp/api/2/laws?response_format=json&offset={offset}&limit={limit_per_page}"
        try:
            data = fetch_json(list_url)
            laws = data.get("laws_response", {}).get("law_info_list", [])
            if not laws: break
            
            # 这里先不按分类过滤，因为清单接口的分类信息不准确
            law_id_list.extend(laws)
            print(f"   已发现 {len(law_id_list)} 个条目 (Offset: {offset})...", flush=True)
            
            if len(laws) < limit_per_page: break
            offset += limit_per_page
        except Exception as e:
            print(f"❌ 索引获取失败: {e}")
            break
        time.sleep(0.1)

    # 2. 第二步：遍历 LawID，下载详情并进行“双重清洗”
    print(f"\n📥 阶段 2: 开始下载详情并过滤国税现行法令 (目标分类: {args.category_cd})...", flush=True)
    
    active_count = 0
    for i, law_info in enumerate(law_id_list):
        if args.limit and active_count >= args.limit:
            break
            
        law_id = law_info.get("law_id")
        law_name = law_info.get("law_name")
        
        try:
            # 下载详情以获取准确的分类和状态
            detail_url = f"https://laws.e-gov.go.jp/api/2/law_data/{law_id}?response_format=json&law_full_text_format=json&extraction_target=all"
            detail_payload = fetch_json(detail_url)
            
            data_root = detail_payload.get("law_data_response", {})
            revision_info = data_root.get("revision_info", {})
            
            # 清洗 A: 检查分类 (必须符合 013)
            # 注意：详情里的 category_cd 可能在不同层级
            law_cat = str(revision_info.get("category_cd", "")).zfill(3)
            if law_cat != args.category_cd.zfill(3):
                continue
            
            # 清洗 B: 检查有效性 (排掉废止)
            repeal = revision_info.get("repeal_status")
            if repeal in ["Repeal", "Expire", "LossOfEffectiveness"]:
                continue
            
            # 存储
            safe_name = re.sub(r"[^\w\-]", "_", law_name)
            file_path = output_dir / f"{law_id}_{safe_name[:50]}.json"
            file_path.write_text(json.dumps(detail_payload, ensure_ascii=False, indent=2))
            
            active_count += 1
            print(f"✅ [{active_count}] 已保存: {law_name}", flush=True)
            
        except Exception as e:
            # 忽略下载错误，继续下一个
            continue
            
        # 频率控制，防止 API 封禁
        time.sleep(0.3)

    print(f"\n🚀 任务完成! 共有 {active_count} 部有效国税法令保存至 {args.output_dir}")

if __name__ == "__main__":
    main()
