# line-bot｜ToukaDev 範例專案

目前狀態見 [HANDOVER.md](HANDOVER.md)；接續實作才恢復狀態。已知介面直接讀，未知才查 [SSOT 導航](docs/ssot/README.md)。


這是一個用 [ToukaDev](../../README.md) 框架建構的 LINE Bot，
展示 **project-init → dev-workflow** 串接流程在 webhook + LINE Messaging API 專案的應用
（本範例以小型專案初始化建立，未含 CI/CD 與 MkDocs 設定）。

## 這個範例示範了什麼

| ToukaDev 元件 | 在哪裡 |
|--------------|--------|
| 專案規則與共同工程基線 | `AGENTS.md` |
| 規格文件（project-init 產出） | `docs/spec.md` |
| SSOT 常數管理 | `src/constants.py` ↔ `docs/ssot/constants.md` |
| 架構決策記錄（ADR） | `docs/adr/ADR-001-技術棧選擇.md` |
| Webhook 介面文件 | `docs/interface/webhook.md` |
| 交班文件（dev-workflow 產出） | `docs/handover/` |
| 業務邏輯與 SDK 呼叫分離（DIP） | `src/handlers/` vs `src/line_client.py` |
| 無 LINE 帳號的測試方法 | `tests/unit/` + `tests/integration/`（mock） |

## 快速開始

### 環境需求
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### 安裝

```bash
cd examples/line-bot
uv sync
cp .env.example .env
# 填入 LINE 憑證（見下方說明）
```

### 如何取得 LINE 憑證

1. 前往 [LINE Developers Console](https://developers.line.biz/)
2. 建立 Provider → 建立 Messaging API Channel
3. 在 Channel 設定頁面取得：
   - **Channel secret** → 填入 `.env` 的 `LINE_CHANNEL_SECRET`
   - **Channel access token** → 點「Issue」→ 填入 `LINE_CHANNEL_ACCESS_TOKEN`

### 本機執行

```bash
# 啟動 Bot
uv run uvicorn src.main:app --reload

# 另開終端，使用 ngrok 公開 webhook
ngrok http 8000
# 把 ngrok 給的 https URL 貼到 LINE Developers Console 的 Webhook URL
# 格式：https://xxxx.ngrok-free.app/webhook
```

### 執行測試（不需要 LINE 帳號）

```bash
uv run pytest -v
```

### 執行靜態檢查

```bash
uv run python scripts/guard_all.py
uv run ruff check .
```

## 目錄結構

```
line-bot/
├── AGENTS.md            ← 專案規則與 ToukaDev 共同工程基線
├── HANDOVER.md         ← 目前狀態與精確入口
├── src/
│   ├── main.py           ← FastAPI app + LINE webhook 路由
│   ├── config.py         ← 環境設定（唯一允許讀環境變數的地方）
│   ├── constants.py      ← SSOT：關鍵字與訊息模板
│   ├── line_client.py    ← LINE API 呼叫層（測試時 mock 此處）
│   └── handlers/
│       ├── message.py    ← 文字訊息業務邏輯（純函式，不依賴 SDK）
│       └── follow.py     ← 加入好友業務邏輯（純函式，不依賴 SDK）
├── tests/
│   ├── conftest.py       ← 測試 fixtures（env var 注入 + 簽名計算）
│   ├── unit/             ← handler 函式的單元測試
│   └── integration/      ← webhook 端點的整合測試（mock LINE API）
├── scripts/
│   └── guard_all.py      ← SSOT 靜態檢查
└── docs/
    ├── spec.md           ← 專案規格（project-init 產出）
    ├── ssot/             ← SSOT 定義文件
    ├── adr/              ← 架構決策記錄
    ├── interface/        ← Webhook 介面文件
    └── handover/         ← 保留的 legacy 歷史（按需讀取）
```

## 相關連結
- [ToukaDev 框架](../../README.md)
- [術語表](docs/glossary.md)
