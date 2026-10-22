#!/usr/bin/env python3
"""
guard_all.py｜SSOT 靜態檢查聚合器
執行方式：uv run python scripts/guard_all.py
所有檢查通過才輸出 SUCCESS，任一失敗立即輸出錯誤並回傳非零退出碼。

brownfield（既有專案導入）：uv run python scripts/guard_all.py --write-baseline
把當前所有 ERROR 快照為既有債務基線（scripts/guard_baseline.json，納入版控）；
之後基線內的違規顯示為 🟠 既有債務、不阻擋 commit，只擋新增的違規。
綠地專案永遠不需要基線。
"""

import ast
import json
import re
import sys
from pathlib import Path

# ── Windows 主控台編碼修正 ──────────────────────────────────────
# cp950 終端機無法輸出 emoji，會 UnicodeEncodeError；強制 stdout/stderr 改用 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ── 專案路徑設定（由 project-init 自動填入）──────────────────────────
ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"  # 後端主要程式碼目錄
FRONTEND_SRC = ROOT / "frontend/src"  # 前端主要程式碼目錄（若無前端則設為 None）
OPENAPI_PATH = ROOT / "openapi.json"  # FastAPI 自動生成的 OpenAPI 規格
ENV_EXAMPLE = ROOT / ".env.example"  # 環境變數範本
DOCKER_COMPOSE = ROOT / "docker-compose.yml"  # Docker Compose 設定（若無則設為 None）

# ── 既有債務基線（僅 brownfield 導入的專案會有這個檔案）──────────────
BASELINE_PATH = ROOT / "scripts" / "guard_baseline.json"

# ── 嚴重性等級定義 ──────────────────────────────────────────────
# ERROR    🔴 必須修復，阻擋 commit（exit code 1）
# 既有債務 🟠 基線內的舊 ERROR（brownfield），不阻擋，建議逐步清償
# WARNING  🟡 建議修復，不阻擋 commit（exit code 0）
# INFO     ℹ️  優化建議，可忽略（exit code 0）
error_findings: list[str] = []
warning_findings: list[str] = []
info_findings: list[str] = []

# ═══════════════════════════════════════════════════════════════
# 【基礎版】開箱即用的檢查項目
# ═══════════════════════════════════════════════════════════════


def check_hardcoded_paths() -> None:
    """檢查硬編碼的絕對路徑和磁碟代號。"""
    patterns = [
        r"(?<![A-Za-z])[A-Za-z]:[/\\\\]",  # Windows 磁碟代號 C:/ D:/（負向後查避免誤判 sqlite:// 等 URL scheme）
        r'"/app/',  # 容器絕對路徑
        r"'/app/",
        r'"/home/\w+/',  # Unix 家目錄
        r"'/home/\w+/",
    ]
    py_files = list(SRC.rglob("*.py")) if SRC.exists() else []
    for f in py_files:
        content = f.read_text(encoding="utf-8")
        for pattern in patterns:
            if re.search(pattern, content):
                error_findings.append(
                    f"硬編碼路徑｜{f.relative_to(ROOT)}｜符合模式：{pattern}"
                )


def check_local_imports() -> None:
    """禁止在函式或方法內部使用局部 import（影響測試 mock 精準度）。"""
    py_files = list(SRC.rglob("*.py")) if SRC.exists() else []
    for f in py_files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        warning_findings.append(
                            f"局部匯入｜{f.relative_to(ROOT)}｜"
                            f"函式 {node.name}() 第 {child.lineno} 行"
                        )


def check_env_direct_access() -> None:
    """環境變數必須透過設定層取得，禁止直接 os.environ[] 或 os.getenv()。
    例外：設定模組本身（config.py、settings.py）允許直接存取。"""
    patterns = [r"os\.environ\[", r"os\.getenv\(", r"os\.environ\.get\("]
    allowed_files = {"config.py", "settings.py", "configuration.py"}
    py_files = list(SRC.rglob("*.py")) if SRC.exists() else []
    for f in py_files:
        if f.name in allowed_files:
            continue
        content = f.read_text(encoding="utf-8")
        for pattern in patterns:
            if re.search(pattern, content):
                error_findings.append(
                    f"直接存取環境變數｜{f.relative_to(ROOT)}｜"
                    f"請透過設定層（config/settings）取得"
                )


def check_openapi_frontend_sync() -> None:
    """檢查前端呼叫的 API 端點是否存在於 FastAPI 生成的 openapi.json。
    前提：需先執行 FastAPI 服務並匯出 openapi.json。"""
    if not OPENAPI_PATH.exists():
        warning_findings.append(
            "OpenAPI 同步｜openapi.json 不存在｜"
            "請先執行：uv run python scripts/export_openapi.py"
        )
        return
    if not FRONTEND_SRC or not FRONTEND_SRC.exists():
        return  # 無前端則跳過

    try:
        spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warning_findings.append("OpenAPI 同步｜openapi.json 格式錯誤")
        return

    backend_paths = set(spec.get("paths", {}).keys())

    # 掃描前端程式碼中的 API 呼叫（fetch/axios/apiClient 模式）
    api_call_patterns = [
        r'(?:fetch|axios\.(?:get|post|put|delete|patch))\s*\(\s*[\'"`]([/][^\'"`\s]+)',
        r'api(?:Client|client|Service)\s*\.\s*(?:get|post|put|delete|patch)\s*\(\s*[\'"`]([/][^\'"`\s]+)',
    ]
    frontend_files = (
        list(FRONTEND_SRC.rglob("*.ts"))
        + list(FRONTEND_SRC.rglob("*.tsx"))
        + list(FRONTEND_SRC.rglob("*.js"))
        + list(FRONTEND_SRC.rglob("*.jsx"))
    )
    for f in frontend_files:
        content = f.read_text(encoding="utf-8")
        for pattern in api_call_patterns:
            for match in re.finditer(pattern, content):
                endpoint = match.group(1).rstrip("'\"` ")
                # 轉換路徑參數格式：/users/{id} vs /users/123
                normalized = re.sub(r"/\d+", "/{id}", endpoint)
                if not any(
                    re.fullmatch(
                        re.sub(r"\{[^}]+\}", r"[^/]+", p.lstrip("/")),
                        normalized.lstrip("/"),
                    )
                    for p in backend_paths
                ):
                    warning_findings.append(
                        f"API 不同步｜{f.relative_to(ROOT)}｜"
                        f"端點 {endpoint} 不存在於 openapi.json"
                    )


# ═══════════════════════════════════════════════════════════════
# 【進階版】依專案需求逐步啟用
# 遇到相關問題時，告知 AI「請啟用 guard_all.py 的 [項目名稱] 檢查」
# ═══════════════════════════════════════════════════════════════


def check_hardcoded_error_messages() -> None:
    """檢查硬編碼的錯誤訊息字串（應集中在 SSOT 錯誤訊息模組）。
    啟用條件：專案建立了統一的錯誤訊息 SSOT 後才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


def check_hardcoded_colors_and_styles() -> None:
    """檢查前端硬編碼的顏色、字體大小、CSS 數值（應使用設計系統變數）。
    啟用條件：專案建立了 design token 或 CSS 變數系統後才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


def check_time_calculation_consistency() -> None:
    """檢查時間計算方式的一致性（內部統一使用 UNIX EPOCH，外部才轉換時區）。
    啟用條件：專案有明確的時間處理 SSOT 定義後才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


def check_data_exchange_format() -> None:
    """檢查跨模組的資料交換格式是否符合 SSOT 定義（如統一用 ISO 8601、snake_case）。
    啟用條件：專案建立了資料交換格式 SSOT 文件後才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


def check_permission_access() -> None:
    """檢查權限取得是否統一透過權限層，禁止直接讀取 role/permission 欄位。
    啟用條件：專案建立了統一的權限抽象層後才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


def check_config_access() -> None:
    """檢查設定取得是否統一透過設定層（已由 check_env_direct_access 部分涵蓋）。
    啟用條件：需要更細緻的設定層檢查時才啟用。"""
    pass  # TODO: 告知 AI 啟用此項目


# ═══════════════════════════════════════════════════════════════
# 執行器
# ═══════════════════════════════════════════════════════════════


def main() -> int:
    write_baseline = "--write-baseline" in sys.argv
    print("🔍 執行 SSOT 靜態檢查...")

    # 基礎版（必跑）
    check_hardcoded_paths()  # → ERROR
    check_local_imports()  # → WARNING
    check_env_direct_access()  # → ERROR
    check_openapi_frontend_sync()  # → WARNING

    # 進階版（預設關閉，由 TODO 標記，告知 AI 逐步啟用）

    # ── 既有債務基線（brownfield 導入用）─────────────────────────
    if write_baseline:
        BASELINE_PATH.write_text(
            json.dumps(sorted(error_findings), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"\n📸 已寫入基線：{len(error_findings)} 筆既有 ERROR → {BASELINE_PATH.relative_to(ROOT)}"
        )
        print(
            "   請將清單整理進 docs/ssot/debt.md（人類可讀版），基線檔一併納入 git 版控。"
        )
        return 0

    baseline: set[str] = set()
    if BASELINE_PATH.exists():
        try:
            baseline = set(json.loads(BASELINE_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            warning_findings.append(
                "基線｜guard_baseline.json 讀取失敗，本次視為無基線（全部 ERROR 照常阻擋）"
            )

    debt_findings = [e for e in error_findings if e in baseline]
    blocking_errors = [e for e in error_findings if e not in baseline]
    for cleared in sorted(baseline - set(error_findings)):
        info_findings.append(f"債務已清償｜{cleared}｜可重跑 --write-baseline 縮小基線")

    # ── 分層輸出報告 ──────────────────────────────────────────────
    if blocking_errors:
        print(f"\n🔴 ERROR（必須修復，阻擋 commit）：共 {len(blocking_errors)} 個")
        for i, e in enumerate(blocking_errors, 1):
            print(f"  {i}. {e}")

    if debt_findings:
        print(
            f"\n🟠 既有債務（基線內，不阻擋；建議逐步清償）：共 {len(debt_findings)} 個"
        )
        for i, e in enumerate(debt_findings, 1):
            print(f"  {i}. {e}")

    if warning_findings:
        print(f"\n🟡 WARNING（建議修復，不阻擋 commit）：共 {len(warning_findings)} 個")
        for i, e in enumerate(warning_findings, 1):
            print(f"  {i}. {e}")

    if info_findings:
        print(f"\nℹ️  INFO（優化建議）：共 {len(info_findings)} 個")
        for i, e in enumerate(info_findings, 1):
            print(f"  {i}. {e}")

    # ── 摘要與退出碼 ─────────────────────────────────────────────
    print("\n--- 檢查結果 ---")
    print(f"🔴 ERROR  ：{len(blocking_errors)} 個")
    if baseline or debt_findings:
        print(f"🟠 既有債務：{len(debt_findings)} 個")
    print(f"🟡 WARNING：{len(warning_findings)} 個")
    print(f"ℹ️  INFO   ：{len(info_findings)} 個")

    if blocking_errors:
        print("\n❌ 有 ERROR，請修復後再 commit。")
        return 1

    print("\n✅ 無 ERROR，可以繼續。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
