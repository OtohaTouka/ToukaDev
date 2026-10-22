# Webhook 介面文件

## POST /webhook — LINE Webhook 接收端點

LINE 平台在使用者與 Bot 互動時，會呼叫此端點。

**Headers（必須）：**
- `X-Line-Signature`：LINE 計算的 HMAC-SHA256 簽名，用於驗證請求來源

**請求內容：** LINE webhook event JSON（由 LINE 平台自動產生）

**回應：** `200 OK` 純文字 "OK"（其他 status code 會讓 LINE 重試）

**錯誤：**
- `400 Bad Request`：`X-Line-Signature` 缺失或不正確

---

## 支援的 LINE 事件

### MessageEvent（文字訊息）

使用者傳送文字訊息時觸發。

| 輸入 | 回覆 |
|------|------|
| 「幫助」（前後空白忽略）| HELP_TEXT（可用指令說明） |
| 其他文字 | 原文回傳（Echo 模式） |

### FollowEvent（加入好友）

使用者將 Bot 加為好友時觸發，自動發送 WELCOME_MESSAGE。

---

## GET /health — 健康檢查

**回應 200 OK：**
```json
{ "status": "ok" }
```

---

## 本機測試 webhook（使用 ngrok）

```bash
# 1. 啟動 Bot
uv run uvicorn src.main:app --reload --port 8000

# 2. 啟動 ngrok（另開終端）
ngrok http 8000

# 3. 把 ngrok 給的 https URL 設定到 LINE Developers Console
# Webhook URL: https://xxxx.ngrok-free.app/webhook
```
