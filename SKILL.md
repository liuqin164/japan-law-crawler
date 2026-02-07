---
name: japan-law-tax-json-download
description: "Download Japan e-Gov law data via API v2 for national tax (category_cd=13) and save each law as JSON locally. Use when Codex needs to build or run a workflow that lists laws from /laws and fetches full text from /law_data, including 404 fallback from law_id to law_num and 0.5s throttling."
---

# Japan National Tax Law JSON Downloader

## Use this skill when
- You need a repeatable workflow to download all national tax laws (category_cd=13) from the e-Gov API v2.
- You want JSON outputs saved locally, one file per law.

## Workflow
1. Run the downloader script to fetch the law list and full texts.
2. Inspect output files and rerun with different options if needed.

## Script
- **scripts/download_laws.py**: Downloads law list and full text JSON files.

### Usage
```bash
python scripts/download_laws.py --output-dir data/national-tax
```

### Key options
- `--base-url`: Override API base URL (default `https://laws.e-gov.go.jp/api/2`).
- `--category-cd`: Category code (default `13`).
- `--sleep-seconds`: Delay between law_data calls (default `0.5`).
- `--limit`: Limit number of laws for testing.

### Output
Files are saved as `{law_num}_{law_name}.json` (sanitized). If `law_num` or `law_name` is missing, the script falls back to `law_id`.

## Notes
- The script retries `law_data` by `law_num` when a `law_id` request returns HTTP 404.
- If you need XML bulk download instead, implement a separate workflow (not included here).
