# fastapi-todo-api 規格文件

> 由 project-init Skill 生成，開發過程中持續維護。

## 專案概述
- **問題描述：** 需要一個簡單的 Todo 管理後端 API，支援建立、列表、完成、刪除四個操作。
- **目標使用者：** 使用此 API 的前端應用程式或其他服務。
- **核心價值：** 展示 ToukaDev 框架在 FastAPI + SQLAlchemy 後端專案的完整應用流程。

## 功能需求

### 核心功能（MVP）
1. **建立 Todo**
   - 輸入：標題（必填）、描述（選填）
   - 驗收標準：回傳 201 與建立的 Todo 物件（含 id、created_at）

2. **列出所有 Todo**
   - 可篩選：completed=true / completed=false / 不傳（全部）
   - 驗收標準：回傳符合條件的 Todo 陣列，依建立時間倒序排列

3. **標記 Todo 為完成**
   - 輸入：Todo id
   - 驗收標準：回傳 200 與更新後的 Todo（completed=true）；id 不存在回傳 404

4. **刪除 Todo**
   - 輸入：Todo id
   - 驗收標準：回傳 204 無內容；id 不存在回傳 404

### 未來功能（非 MVP）
1. 編輯 Todo 標題與描述（PATCH /todos/{id}）
2. Todo 分類標籤
3. 截止日期與到期提醒

## 技術規格
- 語言／框架：Python 3.11 + FastAPI
- 資料庫：SQLite（開發）/ PostgreSQL（正式，透過 SQLAlchemy ORM）
- 外部整合：無
- 套件管理：uv

## 環境規劃
- 開發環境（本機）：✅ SQLite，不需安裝額外服務
- 暫存環境（staging）：不需要（此為範例專案）
- 正式環境（production）：視需求切換 DATABASE_URL 至 PostgreSQL

## 資料庫變更管理
- 目前：直接用 SQLAlchemy `create_all`（開發階段）
- 未來有 schema 變更時：改用 Alembic migration（告知 AI 設定）

## 介面規格（API 端點）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | /todos | 建立 Todo |
| GET | /todos | 列出 Todo（可篩選） |
| PATCH | /todos/{id}/complete | 標記完成 |
| DELETE | /todos/{id} | 刪除 Todo |
| GET | /health | 健康檢查 |

詳細說明見 `docs/interface/api.md`。

## 資料模型

```
Todo
├── id: int（主鍵，自動遞增）
├── title: str（最長 200 字，必填）
├── description: str | None（選填）
├── completed: bool（預設 False）
└── created_at: datetime（自動填入建立時間）
```

## 非功能需求
- **測試覆蓋：** 所有端點都有整合測試，模型有單元測試
- **錯誤處理：** 資源不存在回傳 404，驗證失敗回傳 422
- **文件：** FastAPI 自動生成 OpenAPI 文件（/docs）

## 限制與假設
- 此為範例專案，不實作驗證機制（無需登入）
- 使用 SQLite 以降低入門門檻；正式部署應換用 PostgreSQL

## 驗收標準
- `uv run pytest` 全部通過（0 failed）
- `uv run python scripts/guard_all.py` 無 ERROR
- `uv run ruff check .` 無錯誤
- 可以透過 `/docs` 的 Swagger UI 手動測試所有端點
