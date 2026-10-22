# fastapi-todo-api｜ToukaDev 範例專案

目前狀態見 [HANDOVER.md](HANDOVER.md)；接續實作才恢復狀態。已知介面直接讀，未知才查 [SSOT 導航](docs/ssot/README.md)。


這是一個用 [ToukaDev](../../README.md) 框架建構的 FastAPI Todo API，
展示 **project-init → dev-workflow** 串接流程在 Python 後端專案的實際應用
（本範例以小型專案初始化建立，未含 CI/CD 與 MkDocs 設定）。

## 這個範例示範了什麼

| ToukaDev 元件 | 在哪裡 |
|--------------|--------|
| 專案規則與共同工程基線 | `AGENTS.md` |
| 規格文件（project-init 產出） | `docs/spec.md` |
| SSOT 常數管理 | `src/constants.py` ↔ `docs/ssot/constants.md` |
| 架構決策記錄（ADR） | `docs/adr/ADR-001-技術棧選擇.md` |
| API 介面文件 | `docs/interface/api.md` |
| 交班文件（dev-workflow 產出） | `docs/handover/` |
| 靜態檢查腳本 | `scripts/guard_all.py` |
| 設定層（禁止直接讀環境變數） | `src/config.py` |
| TDD 測試套件 | `tests/unit/` + `tests/integration/` |

## 快速開始

### 環境需求
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（`pip install uv` 或 `curl -LsSf https://astral.sh/uv/install.sh | sh`）

### 安裝

```bash
# 1. 進入此目錄
cd examples/fastapi-todo-api

# 2. 安裝依賴
uv sync

# 3. 複製環境變數範本
cp .env.example .env
```

### 執行 API 伺服器

```bash
uv run uvicorn src.main:app --reload
```

打開瀏覽器前往 http://localhost:8000/docs 可以看到互動式 API 文件。

### 執行測試

```bash
# 執行全部測試
uv run pytest

# 顯示詳細輸出
uv run pytest -v

# 顯示覆蓋率
uv run pytest --cov=src
```

### 執行靜態檢查

```bash
# SSOT 靜態檢查（guard_all.py）
uv run python scripts/guard_all.py

# 程式碼格式與語法檢查
uv run ruff check .
```

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | /todos | 建立 Todo |
| GET | /todos | 列出 Todo（可篩選 `?completed=true/false`） |
| PATCH | /todos/{id}/complete | 標記 Todo 為完成 |
| DELETE | /todos/{id} | 刪除 Todo |
| GET | /health | 健康檢查 |

## 目錄結構

```
fastapi-todo-api/
├── AGENTS.md           ← 專案規則與 ToukaDev 共同工程基線
├── HANDOVER.md         ← 目前狀態與精確入口
├── src/
│   ├── main.py          ← FastAPI app 進入點
│   ├── config.py        ← 環境設定（SSOT：唯一允許讀環境變數的地方）
│   ├── constants.py     ← 全域常數（SSOT）
│   ├── database.py      ← SQLAlchemy 連線設定
│   ├── models.py        ← 資料庫模型
│   ├── schemas.py       ← API 請求/回應格式（Pydantic）
│   └── routers/
│       └── todos.py     ← Todo 相關端點
├── tests/
│   ├── conftest.py      ← 測試 fixtures（in-memory SQLite）
│   ├── unit/            ← 模型單元測試
│   └── integration/     ← API 整合測試
├── scripts/
│   └── guard_all.py     ← SSOT 靜態檢查
└── docs/
    ├── spec.md          ← 專案規格（project-init 產出）
    ├── ssot/            ← SSOT 定義文件
    ├── adr/             ← 架構決策記錄
    ├── interface/       ← API 介面文件
    └── handover/        ← 保留的 legacy 歷史（按需讀取）
```

## 相關連結
- [ToukaDev 框架](../../README.md)
- [術語表](docs/glossary.md)（看到不懂的詞可以在這裡查）
