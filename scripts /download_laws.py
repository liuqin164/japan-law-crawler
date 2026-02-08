#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

def fetch_json(url, timeout=30):
    """带超时保护的请求函数"""
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (OpenClaw-Crawler)'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--category-cd", default="013")
    parser.add_argument("--limit", type=int, default=None, help="最多下载多少部法令后停止")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    offset = 1
    limit_per_page = 100
    active_count = 0
    target_cat = args.category_cd.zfill(3)

    print(f"🚀 启动流式下载任务。目标分类: {target_cat}", flush=True)

    while True:
        # 阶段 1: 获取一页索引 (100条)
        list_url = f"https://laws.e-gov.go.jp/api/2/laws?response_format=json&offset={offset}&limit={limit_per_page}"
        try:
            print(f"📡 正在扫描索引偏移量: {offset}...", flush=True)
            data = fetch_json(list_url)
            laws = data.get("laws_response", {}).get("law_info_list", [])
            
            if not laws:
                print("🏁 已到达索引末尾。")
                break

            # 阶段 2: 立即处理这一页中的每一条法律 (流式处理)
            for law in laws:
                # 检查是否达到用户设定的 limit
                if args.limit and active_count >= args.limit:
                    print(f"🛑 已达到设定的下载上限 ({args.limit})，停止任务。")
                    return

                law_id = law.get("law_id")
                law_name = law.get("law_name")

                try:
                    # 下载详情进行精准过滤
                    detail_url = f"https://laws.e-gov.go.jp/api/2/law_data/{law_id}?response_format=json&law_full_text_format=json&extraction_target=all"
                    detail_payload = fetch_json(detail_url)
                    
                    data_root = detail_payload.get("law_data_response", {})
                    revision_info = data_root.get("revision_info", {})
                    
                    # 校验分类: 必须是 013 (国税)
                    current_cat = str(revision_info.get("category_cd", "")).zfill(3)
                    if current_cat != target_cat:
                        continue

                    # 校验状态: 必须是现行 (非废止)
                    repeal = revision_info.get("repeal_status")
                    if repeal in ["Repeal", "Expire", "LossOfEffectiveness"]:
                        continue

                    # 执行保存 (即时落盘)
                    safe_name = re.sub(r"[^\w\-]", "_", law_name)
                    file_path = output_dir / f"{law_id}_{safe_name[:50]}.json"
                    file_path.write_text(json.dumps(detail_payload, ensure_ascii=False, indent=2))
                    
                    active_count += 1
                    print(f"   ✅ [{active_count}] 已保存: {law_name}", flush=True)
                    
                    # 详情下载间隔，保护API
                    time.sleep(0.3)

                except Exception as e:
                    # 详情下载失败只跳过当前条目，不中断全量任务
                    continue

            # 翻页逻辑
            if len(laws) < limit_per_page:
                break
            offset += limit_per_page
            
        except Exception as e:
            print(f"❌ 索引获取异常 (Offset {offset}): {e}")
            # 如果索引获取失败，尝试跳过这页继续
            offset += limit_per_page
            time.sleep(2)

    print(f"\n🚀 任务完成! 共保存 {active_count} 部有效国税法令。")

if __name__ == "__main__":
    main()
