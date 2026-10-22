# ToukaDev 範例專案

這裡收錄用 ToukaDev 框架建構的完整範例，每個範例都包含：
- 完整的工作程式碼與測試
- project-init 產出的文件（spec.md、ADR、介面文件、交班文件）
- 可直接執行的靜態檢查腳本

## 範例清單

| 範例 | 類型 | 技術棧 | 適合對象 |
|------|------|--------|---------|
| [fastapi-todo-api](./fastapi-todo-api/) | Web API 後端 | FastAPI + SQLite + pytest | 想做後端 API 的人 |
| [line-bot](./line-bot/) | 聊天機器人 | FastAPI + LINE SDK + pytest | 想做 LINE Bot 的人 |

> 兩個範例皆相當於**小型專案初始化**的產出（未含 CI/CD 與 MkDocs 設定）；
> 完整專案初始化會另有 `mkdocs.yml`、`docs/index.md` 與 CI 設定檔。

## 如何使用範例

每個範例都可以獨立執行：

```bash
cd examples/fastapi-todo-api
uv sync
uv run pytest           # 跑測試
uv run uvicorn src.main:app --reload  # 啟動伺服器
```
