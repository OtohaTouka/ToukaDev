# guard_all.py 擴充指南

## 如何看懂輸出結果

| 符號 | 等級 | 代表什麼 | 你需要做什麼 |
|------|------|---------|------------|
| 🔴 ERROR | 必須修 | 會導致部署失敗或安全問題 | 修完再繼續，阻擋 commit |
| 🟡 WARNING | 建議修 | 影響維護性或可能有 bug | 記錄，本輪或下輪修，不阻擋 commit |
| ℹ️ INFO | 可選修 | 程式碼品質優化建議 | 可忽略 |

## 目前啟用的檢查

| 項目 | 嚴重性 | 說明 |
|------|--------|------|
| 硬編碼路徑 | 🔴 ERROR | 硬碼磁碟路徑（C:/、/app/）會讓程式無法跨環境部署 |
| 環境變數直接存取 | 🔴 ERROR | 必須透過設定層，否則測試無法模擬不同設定 |
| 禁止局部 import | 🟡 WARNING | 函式內的 import 會讓測試 mock 失效 |
| 前後端 API 端點同步 | 🟡 WARNING | 前端呼叫的端點若後端不存在，功能會壞掉 |

## 可按需啟用的進階檢查

遇到以下問題時，告訴 AI「請啟用 guard_all.py 的 [項目名稱] 檢查」：

| 項目名稱 | 嚴重性 | 啟用時機 |
|---------|--------|---------|
| 硬編碼錯誤訊息 | ℹ️ INFO | 建立了統一錯誤訊息 SSOT 模組後 |
| 硬編碼顏色與樣式 | ℹ️ INFO | 建立了 design token 或 CSS 變數系統後 |
| 時間計算一致性 | 🟡 WARNING | 專案有明確時間處理 SSOT 定義後 |
| 資料交換格式 | 🟡 WARNING | 建立了資料交換格式 SSOT 文件後 |
| 權限取得方式 | 🔴 ERROR | 建立了統一權限抽象層後 |

## 如何啟用
1. 告知 AI：「請啟用 guard_all.py 的 [項目名稱] 檢查」
2. AI 會將對應的 `pass` 函式替換為實際檢查邏輯
3. 執行 guard_all.py 確認新檢查運作正常
4. 更新此文件的「目前啟用」清單

---

## 安全守衛 guard_security.py（S1–S9）

`guard_security.py` 是**獨立於 guard_all.py** 的安全性靜態檢查，**預設全部啟用**（安全不該 opt-in）。它管「程式碼層」的常見資安錯誤，與規劃階段的 `dev-workflow/references/security-checklist.md`（人工 gate）互補。

| 代號 | 檢查 | 嚴重性 |
|------|------|--------|
| S1 secret | 金鑰/密碼進 code 或 git；.env 衛生（.gitignore 含 .env、.env 未被追蹤） | 🔴 |
| S2 envsync | .env.example 與設定層同步；範本值非真金鑰 | 🔴 |
| S3 sql | execute() 以 f-string／＋／%／.format 拼接 SQL | 🔴 |
| S4 localstorage | 敏感 key 寫入 localStorage（前端） | 🔴 |
| S5 endpoint | 寫入端點缺認證且不在 `PUBLIC_ROUTES` | 🔴 |
| S6 errleak | `debug=True`、錯誤回應夾帶 `str(e)` | 🔴 |
| S7 hash | 密碼語境用 md5/sha1 | 🔴（非密碼語境 🟡）|
| S8 rng | 敏感語境用 `random` 生 token/secret | 🔴 |
| S9 rawbody | route 直接 `request.json()` 原始 dict | 🔴 |

### 控制誤報（不是關掉檢查）
- **白名單**：腳本頂部 `PUBLIC_ROUTES`（公開的寫入端點，如 `/webhook`）、`FRONTEND_SRC`（無前端設 `None`）。
- **行尾豁免**：在該行尾加 `# guard: <代號>-ok`（前端 `// guard: <代號>-ok`），略過該行且計入「🙈 已豁免」（可稽核、不靜默）。例：`hashlib.md5(data)  # guard: hash-ok`（非密碼用途的校驗碼）。

### 為何預設全開
安全風險不分專案大小都可能致命（尤其金鑰外洩**不可逆**）。因此安全守衛不採 guard_all 的「進階選配」模式，而是**一律啟用、用白名單收斂誤報**。
