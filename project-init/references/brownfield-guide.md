# 既有專案導入指南（Brownfield Guide）

> 由 project-init 的「步驟前檢查｜檢查2」分流至此。
> 適用：已有程式碼、但還沒用 ToukaDev 管理的專案。
> 完成後交棒 dev-workflow，與全新專案殊途同歸。

本流程不套用 INIT-B 後的 greenfield 主代理執行迴圈；B2 即使已確認反向規格，也不產生
初始化自主修改委託。保留只補缺件、沿用既有程式與債務政策；後續 dev 仍依當次範圍授權。

## 核心原則

- **不動現有程式碼**：導入階段只讀、只補文件與腳本，不重構、不搬目錄、不改任何 `src/` 內容。
- **只補缺的**：現有的 README、docs、測試一律沿用，缺什麼補什麼。
- **先盤點再動手**：所有補建都以 B1 的現況報告為依據，不憑空假設。
- **守衛用基線**：老專案第一次跑 guard 幾乎必然一堆違規——把它們記成「既有債務」逐步清償，而不是一次全擋（否則導入第一天就寸步難行）。

---

## B1｜盤點現況

AI 依序讀取（存在才讀）：專案 README、依賴檔（`pyproject.toml` / `package.json` / `requirements.txt`）、目錄結構、測試目錄、CI 設定檔、`.env.example` 或 `.env`（**只看鍵名，不讀值**）。

產出「現況報告」給使用者確認：

```markdown
## 導入盤點報告

- 技術棧：[語言、框架、資料庫、套件管理工具]
- 目錄慣例：[主要程式碼在哪、測試在哪、文件在哪]
- 測試現況：[有/無；框架；大約幾個測試]
- 靜態檢查現況：[有/無 ruff、ESLint 等設定]
- CI/CD 現況：[有/無；平台]
- Docker：[有/無]
- 觀察到的風險：[例如 .env 被版控、無任何測試、金鑰疑似寫死]
```

⚠️ 盤點發現 `.env` 被 git 追蹤或疑似金鑰寫死 → **立即告知使用者**，這是導入前就該處理的安全問題。

---

## B2｜反向規格（對應 INIT-B）

AI 從現有程式碼**反推** `docs/spec.md` 草稿：這個專案解決什麼問題、給誰用、核心功能有哪些（依範本 `assets/templates/spec.md` 的結構填寫，推不出來的欄位標註「[待使用者補充]」）。

呈現給使用者：
> 「這是我從程式碼反推的專案規格，請修正我理解錯的地方，並補上標註待補充的欄位。」

**⏸ 使用者確認後才繼續 B3**（等同 INIT-B 審核點）。
此對應只表示人類確認規格，不啟用 `references/supervised-initialization.md` 的步驟 6–12。

---

## B3｜補文件骨架（只補缺的）

比照標準流程步驟7，但**已存在的一律跳過**：

- `AGENTS.md`（範本 `assets/templates/AGENTS.md`，技術棧填 B1 盤點結果）
- `docs/ssot/README.md`、`docs/adr/README.md`、`docs/api/`、`docs/interface/` 的 README
- 根 `HANDOVER.md`（使用 `assets/templates/HANDOVER.md`；保留既有 legacy，不建立新日期交班）
- `docs/interface/README.md`（使用 `assets/templates/docs-interface-README.md`，只填真實正本連結）
- `docs/glossary.md`
- 沿用既有目錄慣例：若專案文件本來就放 `documentation/`，在該目錄下補，**不強制搬到 `docs/`**——但要在 `AGENTS.md` 記錄實際路徑，讓 dev-workflow 找得到。

---

## B4｜ADR-001：記錄既有技術棧

與全新專案不同，這裡**不是選擇而是記錄現狀**：

- 決策內容：既有技術棧清單（來自 B1）
- 理由：寫「導入前已採用」；若使用者知道當初原因就補上，不知道就標註「原始決策理由不可考」
- 這讓未來的 AI 知道「這些選擇不是 ToukaDev 流程做的，改動前先問使用者」

---

## B5｜守衛腳本與基線（本流程的關鍵步驟）

1. 比照標準流程步驟10 生成 `scripts/guard_all.py`、`scripts/guard_security.py`（依 B1 的實際目錄替換檔頭佔位變數）。
2. 先各執行一次，把違規現況呈現給使用者。
3. **guard_all.py 建立基線**：

   ```bash
   uv run python scripts/guard_all.py --write-baseline
   ```

   - 產生 `scripts/guard_baseline.json`（納入 git 版控）
   - 基線內的既有 ERROR 之後會顯示為 🟠 **既有債務**——不阻擋 commit，只擋**新增**的違規
   - 同時把清單整理成人類可讀的 `docs/ssot/debt.md`（每筆一行：違規內容、所在檔案、建議清償方式）

4. **guard_security.py 不建基線**——安全違規不能「先欠著」：
   - 能立即修的（如金鑰寫死）→ 當場修
   - 經使用者確認確實無風險的 → 在該行加 `# guard: <規則>-ok` 豁免並留下可稽核痕跡
   - 一時修不完的 → 列入 `docs/ssot/debt.md` 的「安全債務（最高優先）」區，**導入後第一個 dev-workflow 循環優先處理**

---

## B6｜測試現況處理

- **已有測試** → 沿用既有框架與目錄，只在 `AGENTS.md` 記錄執行方式
- **沒有測試** → 只建目錄骨架（`tests/unit`、`tests/integration`、`tests/smoke`、`conftest.py`），**不強制補寫舊功能的測試**——留給之後的 dev-workflow 循環：每次動到某模組時，順手為該模組補測試（TDD 對「新變更」立即生效，對「舊程式」漸進覆蓋）

---

## B7｜交班與交棒

建立或更新根 `HANDOVER.md`，只記錄有變化的 current 與精確連結；不建空 HISTORY／roadmap／evidence。內容包含：

- 導入完成狀態（B1–B6 各做了什麼、跳過了什麼）
- 債務清單位置（`docs/ssot/debt.md`）與當前筆數（安全債務單獨標明）
- 下一步建議（通常是：先清安全債務 → 再開始第一個功能循環）

宣告：
> 「既有專案導入完成。文件骨架與守衛已就位，既有違規已記入債務基線（[N] 筆，其中安全債務 [M] 筆）。之後開發使用 dev-workflow；建議每輪順手清償 1–2 筆債務，清完後重跑 `--write-baseline` 縮小基線。」

---

## 導入後的日常

- dev-workflow 照常運作；步驟9 的靜態檢查會顯示 🟠 既有債務（不阻擋）
- 債務清償節奏：每個開發循環順手清 1–2 筆；債務歸零後刪除 `guard_baseline.json` 與 `docs/ssot/debt.md`，從此與全新專案完全相同
- ⚠️ **禁止**把新產生的違規塞進基線來逃避修復——基線只在導入時建立、只能縮小不能擴大（清償後重跑 `--write-baseline` 即是縮小）
