# 交班文件：既有 Ruff formatting debt

- 日期：2026-08-09
- 狀態：經人類明確核准後完成，尚未 stage／commit
- 上層任務：ToukaDev reviewer cost controls 第二批的 DBG-A 驗證

## 變更

- `scripts/guard_all.py`
- `scripts/guard_security.py`
- `tests/integration/test_todos_api.py`

以上僅套用專案 `.venv` 內 Ruff 0.15.13 的格式化；與 HEAD 的 Python AST 全部等價，沒有
功能、介面、依賴或資料行為變更。

## 驗證

- pytest：18 passed。
- Ruff check：通過。
- Ruff format check：16 files already formatted。
- `guard_all.py`：零 ERROR／WARNING／INFO。
- `guard_security.py`：零 ERROR／WARNING／INFO，零豁免。

本次未讀取或修改 `data/`，未執行 Docker，未 stage、未 commit。
