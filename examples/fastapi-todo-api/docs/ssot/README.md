# SSOT（單一事實來源）目錄

## 精確導航

| 任務／程式路徑 | 正本 |
|---|---|
| src/routers/todos.py 的 DELETE /todos/{id} | [刪除 Todo 契約](../interface/api.md#delete-todosid--刪除-todo) |
| src/routers/todos.py 的其他端點 | [API 介面](../interface/api.md) |
| src/constants.py | [常數文件](constants.md) |
| src/config.py | [設定實作](../../src/config.py) |

已知正本可直接讀完整必要章節；不要求先讀本 index。常數值由程式正本定義，本目錄記錄契約。


## 原則
每個常數、型別定義、設定值只在程式正本定義一次，其他地方 import 引用；此目錄記錄契約。
禁止在程式碼中重複定義，或直接寫死數值。

## 文件清單
- `constants.md`：全域常數定義（對應 `src/constants.py`）

## 違反 SSOT 的常見情況
- 在多個檔案重複定義相同常數（例如兩個地方都寫 `MAX_LENGTH = 200`）
- 硬編碼應該集中管理的數值（例如直接寫 `if len(title) > 200`）
- 直接讀取環境變數而不透過 `src/config.py`

## 自動驗證
執行 `uv run python scripts/guard_all.py` 會自動檢查常見的 SSOT 違反。
