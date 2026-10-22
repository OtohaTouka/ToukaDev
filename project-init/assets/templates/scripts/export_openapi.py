#!/usr/bin/env python3
"""
export_openapi.py｜匯出 FastAPI OpenAPI 規格
執行方式：uv run python scripts/export_openapi.py
輸出：根目錄下的 openapi.json
"""

import json
import sys
from pathlib import Path

# Windows cp950 終端機無法輸出 emoji，會 UnicodeEncodeError；強制改用 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "openapi.json"


def main() -> int:
    try:
        # ⚠️ 將 "src.main" 和 "app" 替換為你的 FastAPI 應用程式實際路徑
        from src.main import app  # type: ignore
    except ImportError as e:
        print(f"❌ 無法匯入 FastAPI app：{e}")
        print("請確認 src/main.py 存在且 FastAPI app 物件名稱為 'app'")
        return 1

    spec = app.openapi()
    OUTPUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ openapi.json 已匯出至：{OUTPUT}")

    paths = list(spec.get("paths", {}).keys())
    print(f"   共 {len(paths)} 個端點：")
    for p in paths:
        print(f"   - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
