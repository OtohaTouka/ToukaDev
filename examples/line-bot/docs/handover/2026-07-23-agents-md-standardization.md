# 交班文件：AGENTS.md 標準化

- **日期：** 2026-07-23
- **狀態：** 已完成
- **影響範圍：** 專案規則與文件，不影響 LINE webhook 行為

## 完成事項

- 將專案規則檔由舊式混合大小寫名稱遷移為正式 `AGENTS.md`。
- 套用 ToukaDev 根規則的共同工程基線。
- 保留 FastAPI、LINE Messaging API、pytest、ruff 與 uv 技術棧資訊。
- 保留 handler／LINE SDK 分層、環境變數與 webhook 文件同步規則。
- 更新 README 的 ToukaDev 元件清單與目錄樹。

## 未變更

- Webhook 端點與簽名驗證
- 訊息及 follow event 行為
- LINE API 呼叫層
- 應用程式碼、測試行為與 ADR-001

## 驗證

- pytest：15 passed。
- ruff check：通過。
- `scripts/guard_all.py`：零 ERROR、零 WARNING。
- `scripts/guard_security.py`：零 ERROR、零 WARNING。
- ruff format check 顯示 6 個未修改的既有檔案會被新版 formatter 重排；本次未做範圍外格式化。
