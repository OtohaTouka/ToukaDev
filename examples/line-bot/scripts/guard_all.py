#!/usr/bin/env python3
"""
guard_all.py - SSOT 靜態檢查聚合器
執行方式：uv run python scripts/guard_all.py

嚴重性等級：
  [ERROR]   - 必須修復，阻擋 commit（exit code 1）
  [WARNING] - 建議修復，不阻擋 commit（exit code 0）
  [INFO]    - 優化建議，可忽略（exit code 0）
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"

error_findings: list[str] = []
warning_findings: list[str] = []
info_findings: list[str] = []


# ==============================================================================
# 基礎版檢查（必跑）
# ==============================================================================


def check_hardcoded_paths() -> None:
    """[ERROR] 檢查硬編碼的絕對路徑和磁碟代號。"""
    patterns = [
        r"[A-Za-z]:[/\\][^/]",  # Windows 磁碟代號（排除 URL scheme 如 sqlite://）
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
                error_findings.append(f"硬編碼路徑 | {f.relative_to(ROOT)} | 符合模式：{pattern}")


def check_local_imports() -> None:
    """[WARNING] 禁止在函式或方法內部使用局部 import（影響測試 mock 精準度）。"""
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
                            f"局部匯入 | {f.relative_to(ROOT)} | "
                            f"函式 {node.name}() 第 {child.lineno} 行"
                        )


def check_env_direct_access() -> None:
    """[ERROR] 環境變數必須透過 config.py 取得，禁止直接使用 os.environ 或 os.getenv。"""
    patterns = [r"os\.environ\[", r"os\.getenv\(", r"os\.environ\.get\("]
    allowed_files = {"config.py", "settings.py"}
    py_files = list(SRC.rglob("*.py")) if SRC.exists() else []
    for f in py_files:
        if f.name in allowed_files:
            continue
        content = f.read_text(encoding="utf-8")
        for pattern in patterns:
            if re.search(pattern, content):
                error_findings.append(
                    f"直接存取環境變數 | {f.relative_to(ROOT)} | "
                    f"請透過 src/config.py 的 settings 物件取得"
                )


# ==============================================================================
# 執行器
# ==============================================================================


def main() -> int:
    print("執行 SSOT 靜態檢查...")

    check_hardcoded_paths()
    check_local_imports()
    check_env_direct_access()

    if error_findings:
        print(f"\n[ERROR] 必須修復，阻擋 commit：共 {len(error_findings)} 個")
        for i, e in enumerate(error_findings, 1):
            print(f"  {i}. {e}")

    if warning_findings:
        print(f"\n[WARNING] 建議修復，不阻擋 commit：共 {len(warning_findings)} 個")
        for i, e in enumerate(warning_findings, 1):
            print(f"  {i}. {e}")

    if info_findings:
        print(f"\n[INFO] 優化建議：共 {len(info_findings)} 個")
        for i, e in enumerate(info_findings, 1):
            print(f"  {i}. {e}")

    print("\n--- 檢查結果 ---")
    print(f"[ERROR]  : {len(error_findings)} 個")
    print(f"[WARNING]: {len(warning_findings)} 個")
    print(f"[INFO]   : {len(info_findings)} 個")

    if error_findings:
        print("\nX 有 ERROR，請修復後再 commit。")
        return 1

    print("\nOK 無 ERROR，可以繼續。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
