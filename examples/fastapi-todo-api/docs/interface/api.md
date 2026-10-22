# API 介面文件

> 本文件是 API 的 SSOT，所有端點的詳細規格集中於此。
> FastAPI 也會在 `/docs` 自動產生互動式文件，兩者應保持一致。

## 基底 URL
- 開發環境：`http://localhost:8000`

---

## POST /todos — 建立 Todo

**請求：**
```json
{
  "title": "買牛奶",          // 必填，1~200 字
  "description": "低脂的"    // 選填
}
```

**回應 201 Created：**
```json
{
  "id": 1,
  "title": "買牛奶",
  "description": "低脂的",
  "completed": false,
  "created_at": "2026-05-17T10:00:00+00:00"
}
```

**錯誤：**
- `422 Unprocessable Entity`：title 缺失或超過 200 字

---

## GET /todos — 列出 Todo

**查詢參數：**
- `completed=true`：只回傳已完成的 Todo
- `completed=false`：只回傳未完成的 Todo
- 不傳：回傳所有 Todo

**回應 200 OK：**
```json
[
  {
    "id": 2,
    "title": "買牛奶",
    "description": null,
    "completed": false,
    "created_at": "2026-05-17T10:00:00+00:00"
  }
]
```

結果依 `created_at` 倒序排列（最新的在最前面）。

---

## PATCH /todos/{id}/complete — 標記為完成

**路徑參數：** `id`（整數）

**回應 200 OK：**
```json
{
  "id": 1,
  "title": "買牛奶",
  "description": null,
  "completed": true,
  "created_at": "2026-05-17T10:00:00+00:00"
}
```

**錯誤：**
- `404 Not Found`：id 不存在

---

## DELETE /todos/{id} — 刪除 Todo

**路徑參數：** `id`（整數）

**回應 204 No Content：** 無回應內容

**錯誤：**
- `404 Not Found`：id 不存在

---

## GET /health — 健康檢查

**回應 200 OK：**
```json
{ "status": "ok" }
```
