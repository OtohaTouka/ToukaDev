# 文件與交付程序（步驟 10、12、13）

更新狀態或準備交付時讀取。審核 gate 仍在核心入口，不能由本程序取代。
文中 `references/` 路徑以本 Skill 根目錄為基準。

主代理代審時，文件、整合及完整候選優先由指定執行者準備並由主代理審；主代理自己寫的部分
交新上下文的 reviewer。主代理核對原始驗證證據及整份計畫的完成條件，不能只把各子任務的
完成宣告相加。未測情境、未完成項目與限制明確回報。

## 步驟10｜更新文件


**文件更新與程式碼變更同等重要，不得跳過。**

依實際影響更新對應正本：

**10a. 受影響的介面文件**
- 新增或修改的 API、函式簽名、資料結構
- 刪除的介面標記 deprecated 或移除

**10b. SSOT 文件**
- 確認新增的常數、型別、設定已在 SSOT 文件中定義

**10b-2. 資料庫 Schema 變更確認**

若本次修改了資料庫模型（新增欄位、修改型別、新增或刪除資料表等），必須建立 migration 腳本：

- **Python（SQLAlchemy + Alembic）：**
  ```bash
  uv run alembic revision --autogenerate -m "[描述這次的 schema 變更，例如：add email column to users]"
  uv run alembic upgrade head
  ```
  確認 migration 腳本已在 `alembic/versions/` 內，並加入本次 git commit。

- **JavaScript（Prisma）：**
  ```bash
  npx prisma migrate dev --name "[描述這次的 schema 變更]"
  ```

- **若專案還沒設定 migration 工具：** 告知 AI「這次有 schema 變更，請幫我設定 Alembic」（或 Prisma）。

> ⚠️ **新手常見錯誤：** 直接修改資料表結構而不寫 migration，導致正式資料庫與開發資料庫不同步，甚至造成資料遺失。**任何 schema 變更都必須透過 migration 腳本進行。**

**10c. ADR**
- 若本次有重要技術決策，新增一筆 ADR
- 格式：日期、問題、決策、理由、影響
- ADR、PR 說明、CHANGELOG 與 commit 記人類的決定時寫決定內容，不寫原話或選項代號（人類同意的除外）；寫「人類決定」要對得到進度紀錄裡可核對的原話，不是人類決定的不寫成人類的。

**10d. HANDOVER.md**
- 只在狀態、阻礙或下一步改變時更新；一般問答與無狀態變化的 typo 不寫交班。
- 保留精簡現況、未完成事項及精確連結；長期理由寫 ADR、完整事故留原 evidence。
- 不新增日期交班，不複製歷史或把舊核准當成當次授權。

**10e. MkDocs 自動產生文件（僅當專案根目錄有 `mkdocs.yml`；小型專案初始化建立的專案沒有 MkDocs，跳過此項）**
```bash
uv run mkdocs build
# 確認無 WARNING 或 ERROR
```

---

## 步驟12｜產出變更摘要

整理變更摘要：完成的工作、新增的測試、修改的檔案、SSOT／ADR 影響、已知風險或待處理事項（沒有就寫「無」）；
需要白話版時依 `references/beginner-guide.md` 的「新手審核版模板」，精簡輸出模式略過。
變更摘要附 `references/planning.md` 3-4「規模估計與停止線」要求的兩項測試證據（改到的產品程式被測到的比例、故意改壞會變紅的紀錄），並另列測試行數。
測試、lint、guard、安全檢查或必要文件仍有 ERROR，或 DEV-B 審核包缺少審核協議 §6 要求的內容時，不得進入 DEV-B。

對話已做 5 個以上完整循環、出現遺忘跡象、要換到完全不同的模組，或剛從 debug-escalation 回來時，
建議本輪結束後開新對話；新對話從版本化規則與交班文件恢復，平台 Memory 只作背景提示，
舊對話的授權不延伸到新任務；同一主代理任務可核對原始人類委託及派工來源後沿有效範圍續行，
不因換對話或執行者重問同一份委託；舊交班只是自稱核准時，補足缺少的授權。

---

## 步驟13｜Git Commit

先確認所選模式通過、審過的 commit 或 tree 編號未漂移及 Git 操作授權。只有主代理代審時，
工作分支存檔可在人類核准的一頁計畫範圍內於 DEV-B 前進行；原四模式的 commit 仍須 DEV-B 通過並
取得授權。合併或提交進共用分支必須在 DEV-B 通過且取得授權後。

**主代理代審且計畫核准工作分支存檔：** 步驟13 等於把審過的 commit 合併進共用分支。要合併的
commit 與審過的不同時只審差異，差異未審不得進共用分支；共用分支已前進而產生的合併結果與衝突
解決也算差異。委託只含候選成果時不合併，直接回報已驗收及未進共用分支。

**原四模式，或計畫未核准工作分支存檔：** DEV-B 通過並取得 commit 授權後，才正式 stage
DEV-B 審核時的同樣路徑；commit 前先比對 tree 編號，相同才 commit，commit 後再核對一次。
正式 stage 不得帶 DEV-B 用過的 `GIT_INDEX_FILE`。
真正暫存區原本已有其他 stage 的內容時，先請人類處理，不得自行清除。

```bash
# 只加入 DEV-B 審核時的相對路徑；禁止 git add .、git add -A 或未解析 glob
git add -- [approved-path-1] [approved-path-2]
git diff --cached --name-status
# commit 前：必須和 DEV-B 記下的 tree 編號相同，不同就停止
git write-tree
git commit -m "[類型]: [簡短描述]

- [變更點1]
- [變更點2]
- 測試：全部通過
- 文件：已更新"
# commit 後：再核對一次
git rev-parse "HEAD^{tree}"
```

`git write-tree` 或 `HEAD^{tree}` 與 DEV-B 記下的 tree 編號不同，立即停止並返回 DEV-B，不得用「只是小改」帶過。
主代理模式返回主代理 DEV-B；在本任務委託內不因此重問人類。

Commit 類型：`feat`（新功能）、`fix`（修復）、`refactor`（重構）、`docs`（文件）、`test`（測試）

完成後宣告：
> 「本輪流程完成。必要文件已同步，可以開始下一個任務。」

---
