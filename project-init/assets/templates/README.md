# [專案名稱]

[一句話描述專案]

## 快速開始

### 環境需求
- [語言版本]
- [其他必要工具]

### 安裝

```bash
# 複製環境變數範本（Windows PowerShell 改用：Copy-Item .env.example .env）
cp .env.example .env
# 編輯 .env 填入實際值

# Python（一律透過 uv 管理，不使用 pip / venv）
uv sync

# 或 JavaScript/TypeScript
npm install
```

### 執行測試

```bash
# Python
uv run pytest tests/ -v

# JavaScript/TypeScript
npx jest --verbose
```

### 靜態檢查

```bash
uv run ruff check .             # Python
npx eslint .                    # JS/TS
uv run python scripts/guard_all.py         # SSOT 驗證
uv run python scripts/guard_security.py    # 安全性檢查（S1–S9）
```

### 產生文件（只有專案包含 mkdocs.yml 時）

```bash
uv run mkdocs serve    # 本地預覽
uv run mkdocs build    # 建置靜態文件
```

## 專案結構

[複製步驟6的目錄結構]

## 開發流程

本專案使用標準 13 步驟人機協作流程，詳見 `AGENTS.md`。
`AGENTS.md` 內的「Quick validation profile」命令清單是文件快速路徑 L3 命令 SSOT；
缺少清單或其中的檔案不存在時，必須停止並改走完整流程。

## 文件

- [規格文件](docs/spec.md)
- [架構決策記錄](docs/adr/)
- [API 文件](docs/api/)
- [目前狀態](HANDOVER.md)
- [SSOT 導航](docs/ssot/README.md)
- [介面導航](docs/interface/README.md)
