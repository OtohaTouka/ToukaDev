# line-bot 規格文件

## 專案概述
- **問題描述：** 建立一個 LINE 聊天機器人，支援 Echo、幫助指令、加入好友歡迎訊息。
- **目標使用者：** LINE 平台使用者，透過加入 Bot 好友後互動。
- **核心價值：** 展示 ToukaDev 框架在 webhook 架構與 LINE Bot 專案的應用流程。

## 功能需求

### 核心功能（MVP）
1. **Echo 功能**
   - 使用者說什麼，Bot 就回覆什麼（原文回傳）
   - 驗收標準：任何非關鍵字訊息都原文回覆

2. **幫助指令**
   - 使用者傳「幫助」，Bot 回覆可用指令說明
   - 驗收標準：輸入「幫助」（前後空白自動忽略）回傳 HELP_TEXT

3. **加入好友歡迎訊息**
   - 使用者加入 Bot 好友時，自動發送歡迎訊息
   - 驗收標準：收到 follow 事件時回覆 WELCOME_MESSAGE

### 未來功能（非 MVP）
1. 記憶功能（儲存使用者偏好）
2. 更多指令（天氣、翻譯等）
3. Rich menu 設定

## 技術規格
- 語言／框架：Python 3.11 + FastAPI
- 外部整合：LINE Messaging API（line-bot-sdk v3）
- 部署方式：任何支援 HTTPS webhook 的平台（Render、Railway、ngrok 測試）

## 環境規劃
- 開發環境：ngrok 或 LINE 的 Webhook URL 設定
- 正式環境：部署到 Render / Railway，設定 HTTPS webhook URL

## 介面規格（API 端點）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | /webhook | LINE webhook 接收端點 |
| GET | /health | 健康檢查 |

詳細說明見 `docs/interface/webhook.md`。

## SSOT 訊息模板
所有關鍵字和訊息模板定義在 `src/constants.py`（對應文件：`docs/ssot/constants.md`）。

## 驗收標準
- `uv run pytest` 全部通過（0 failed）
- `uv run python scripts/guard_all.py` 無 ERROR
- `uv run ruff check .` 無錯誤
- 部署後可在 LINE 測試 Bot 基本功能
