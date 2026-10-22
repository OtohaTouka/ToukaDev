# ADR-045：第七次改進任務：加入 asset-workflow（美術素材流程）

- 日期：2026-10-20
- 狀態：已接受（一頁計畫 v3.2 由人類核准：G1～G5、整合 1～3、Git 範圍與合併後重裝 Claude 的 Skills 照建議；X1、X2 兩項
  放寬由人類單獨核准；不做對抗式複審、完成後不跑改進；主代理代審，單一寫入者；實作在本 PR）
- 修訂：無。新增第五個 Skill；dev-workflow 只多一行分流，13 步驟與審核點不變
- 影響範圍：新增 `asset-workflow/`；`dev-workflow/SKILL.md` 一行；improvement-loop 的 SKILL 與 README 各一處流程列舉；
  守衛 `scripts/guard_framework.py` 與 `tests/test_guard_document_structure.py`；README、術語表 4 份、SSOT 導航、框架
  `AGENTS.md`（共同區塊外）、ADR 索引、HANDOVER。四份共同區塊沒動

## 背景

這是依 ADR-036 進行的第七次改進任務，由人類啟動，要加入 asset-workflow。人類先前已決定美術版
放在 ToukaDev 底下、做成和 dev-workflow 並列的獨立 Skill，美感審核改成先定基準、主代理自己逼近，人類只審基準、試作品與
成品，練習得到的經驗之後用在其他專案。

本任務的人類決定：範圍只做 asset-workflow；同意把另一個專案加進來源清單、把它的經驗整理成 `.toukadev/lessons`，並以它的
規則草稿、經驗清單與一次版本的迭代紀錄當新 Skill 的規格依據。來源是那個專案的 6 筆待處理紀錄（5 組根因）；ToukaDev 10 筆、
第三個專案 15 筆紀錄依人類範圍留給下一次。紀錄是證據，不是授權。技術計畫經非作者的 DEV-A 3 輪加 2 次差異確認後通過，
作者與審核者各自標記鬆緊，一致。

## 教訓

| 紀錄的教訓（概括） | 類型與次數 | 處理 |
|---|---|---|
| 美術工作沒有適用的流程，人類只好刻意不給 ToukaDev：美感不能先寫測試、標準要由人定、素材是二進位檔、成品要版本化歸檔 | 反覆困擾 1 | D1 |
| 共用素材改版，默默改掉已核可的作品；只改一段卻連帶改到範圍外的段落 | 重大錯誤 各 1 | D3（L5） |
| 交付過的版本沒有能重現的快照；tag 打在不能重現那一版的 commit | 重大錯誤 1 | D3（L6） |
| 無法重算的檔案放在看起來可以刪的輸出資料夾 | 重大錯誤 1 | D3（五種狀態） |
| 人類核可的量測規則，量基準本身時才發現不公平 | 白做工 1 | D2（L4） |

每組都只在一個專案發生 1 次；G1 由人類決定做成通用的美術版，其餘有明確解法。

## 決定

1. **D1 新增 asset-workflow，和 dev-workflow 並列**（G1）：
   - 適用「驗收標準是對照人類核可的參考基準」的作品外觀與素材（影片、插畫、遊戲美術、配樂與音效）；軟體介面、程式行為、
     工具與分不清的情況走 dev-workflow。需要已初始化的專案；缺量測工具時先照 dev-workflow 做工具。
   - 流程：恢復狀態 → 一頁計畫（含共用素材的其他使用者、Git 範圍的 tag、LFS 與成品庫寫入）→ 先量基準本身 → ART-0 基準 →
     迭代與逐段比對 → ART-1 試作品 → 成片與技術檢查 → ART-2 成品 → 交付。
   - 鎖定句 L1（美感標準在 ART-0 核可、人類只審三關）、L2（程式修改仍經 DEV-A、DEV-B、寫審分離與 commit 授權）、
     L3（量化通過不等於核可）。
   - 不做成 dev-workflow 的按需程序：核心循環衝突（先寫測試 vs 先定基準；主代理代審 vs 人類審美），且人類已決定並列。
2. **D2 基準與對照程序**（G5）：挑基準要授權、逐項同意下載、條件相近，刻意風格化的段落在 ART-0 標出不比；ART-0 前先量基準
   本身，只用暫存資料夾與可刪的輸出，不寫入 repo；每輪改一件事並記錄；先做對照實驗再下結論；量雜訊底線。鎖定句 L4：
   ART-0 之後修正的量測規則標成待確認，原規則與修正後的結果並列。
3. **D3 素材管理與交付程序**（G2、G3、G4）：檔案分五種狀態，能不能重算要實測；成品庫位置由專案宣告，任何清理都不碰；
   推送 LFS 先取得同意；重新上鎖放進 DEV-B 前的候選。鎖定句 L5（改共用素材或程式要和已核可的版本逐段比對，含範圍外的
   段落）、L6（ART-2、DEV-B、合併後才算交付；tag 只打在已合併且確認能重現的 commit；合併後改 repo 另過 DEV-B）。
   交付順序：合併 → 確認能重現 → 複製到成品庫 → 兩者都成功才打 tag；失敗不打 tag，修正另過 DEV-B。
4. **D4 用程式產生的外觀，以 ART-0 核可的量測作 Red／Green**（X1，放寬，人類單獨核准）：鎖定句 L7。
   每一次程式修改前，涵蓋它的量測項目都要先確認不合格；ART-0 改了量測方式就重量；否則或分不清時照 TDD。全體回歸、lint
   與守衛照常執行。源頭：TDD 與「先寫實作再補測試」禁令來自共同基線 ADR-001；ADR-001 只建立共同區塊，更早的源頭找不到記載。
5. **D5 量測全數合格後只依主觀評分的程式修改，逐項交人類決定**（X2，放寬，人類單獨核准）：鎖定句 L8，
   只在 X1 核准時生效。源頭同 D4。不核准時的替代（先補新的量測項目、重過 ART-0）一併列給人類，人類選擇核准。
6. **D6 分流與整合**：dev-workflow「適用性與按需程序」加一行分流（X1 核准的版本，不另加「與 TDD」）；improvement-loop 的流程
   列舉加上 asset-workflow；守衛登記 Skill、兩條程序觸發行、兩份程序、三個 ART 標題（存在、唯一、順序）與 L1～L8；README、
   術語表 4 份、SSOT 導航與框架 AGENTS 同步。
7. **D7 素材任務不是大任務**：素材任務不走 13 步驟，不是 improvement-run 定義的大任務，一頁計畫不附「完成後要不要跑改進」。

## 決定落點表

行號是本 PR 的位置，只供核對時找，以檔案與段落為準。

| 項次 | 決定 | 檔案 | 段落（行號附近） |
|---|---|---|---|
| D1 | 啟動時機、分流、三關與授權摘要 | `asset-workflow/SKILL.md` | frontmatter（L1–12） |
| D1 | L1、L3、L2 | `asset-workflow/SKILL.md` | 「核心原則」後的段落（L26、L28、L30） |
| D1 | 適用性、按需程序兩行、不附跑改進 | `asset-workflow/SKILL.md` | 「適用性與按需程序」（L40–50） |
| D1 | 步驟 1–10 與三個審核點 | `asset-workflow/SKILL.md` | 「規劃」到「交付」（L52–103） |
| D1 | 禁止行為 | `asset-workflow/SKILL.md` | 「AI 禁止行為清單」（L107–118） |
| D2 | 挑基準、存放、分類、先量基準、每輪、對照實驗 | `asset-workflow/references/reference-review.md` | L6–63 |
| D2 | L4 與修正規則的處理 | `asset-workflow/references/reference-review.md` | 「量測規則的修正」（L65–73） |
| D2 | 取捨、停止條件、ART-1 交件 | `asset-workflow/references/reference-review.md` | L75–94 |
| D2 | 基準清單範本 | `asset-workflow/assets/templates/reference-set.json` | 全檔 |
| D3 | 五種狀態、目錄、命名、成品庫、成品紀錄、LFS、鎖定 | `asset-workflow/references/asset-management.md` | L6–94 |
| D3 | L5 | `asset-workflow/references/asset-management.md` | 「共用素材與範圍外的段落」（L98） |
| D3 | L6 與交付順序 | `asset-workflow/references/asset-management.md` | 「交付」（L106–119） |
| D3 | 發佈、第一次使用 | `asset-workflow/references/asset-management.md` | L121–131 |
| D3 | 成品紀錄範本 | `asset-workflow/assets/templates/releases.json` | 全檔 |
| D4 | L7 與照常執行的檢查 | `asset-workflow/SKILL.md` | L32、L36；「迭代」第 1 子項（L73） |
| D5 | L8 | `asset-workflow/SKILL.md` | L34；ART-1 交件（L83–84） |
| D6 | 分流行 | `dev-workflow/SKILL.md` | 「適用性與按需程序」第 5 項（L46–47） |
| D6 | 流程列舉 | `improvement-loop/SKILL.md`、`improvement-loop/README.md` | L30；L74 |
| D6 | 守衛登記 | `scripts/guard_framework.py` | `SKILLS`、`PROCEDURE_ROUTES`、`REQUIRED_OBLIGATIONS`、`CHECKPOINT_HEADINGS`、`PROCEDURE_REFERENCE_PATHS` |
| D6 | 文件同步 | `README.md`、`glossary.md` 與 3 份複本、`docs/ssot/README.md`、`AGENTS.md` | 五個 Skill 的圖與介紹、審核點、安裝、使用流程、目錄樹；「美術素材流程」；精確導航兩列；「按需程序」 |
| D7 | 不附跑改進 | `asset-workflow/SKILL.md` | 「適用性與按需程序」第 4 項（L46） |

## 規則鬆緊與受保護規則

作者與審核者（DEV-A 3 輪）各自標記，結果一致。

| 項次 | 改動 | 作者 | 審核者 | 核准方式 |
|---|---|---|---|---|
| D1～D3 | 新 Skill 的非程式素材流程、L1、L3～L6、五種狀態 | 加嚴 | 加嚴 | 照建議 |
| D1 | L2（程式修改的 DEV-A、DEV-B） | 加嚴 | 加嚴（第 2 輪補「超出計畫回 DEV-A、影響基準重過 ART-0」） | 照建議 |
| D1 | ART-0／1／2 | 加嚴 | 加嚴（不取代 DEV-A、DEV-B） | 照建議 |
| D4 | X1／L7 | 放寬 | 放寬 | 人類單獨核准 |
| D5 | X2／L8 | 放寬 | 放寬 | 人類單獨核准 |
| D6 | 分流行 | 不變 | X1 核准下不變 | 照建議 |
| D6 | improvement-loop 列舉、框架 AGENTS 一行、文件 | 不變 | 不變 | 照建議 |
| D6 | 守衛與測試 | 加嚴 | 加嚴 | 照建議 |
| D7 | 素材任務不附跑改進（SKILL 也寫一句） | 不變 | 不變（DEV-B 標） | 照建議 |
| DEV-B 修正 | 清空輸出資料夾先問人類、改寫歷史要單獨核准、能逐位元組重現的要求雜湊相同 | 加嚴 | 加嚴（DEV-B 建議） | 照建議 |

DEV-B 審核者另外獨立標記：把「純素材改動以人類核可的 ART-0 代替 DEV-A（DEV-B 保留）」標成「不變」（比照文件快速路徑），
比作者的「加嚴」保守；其餘和上表一致，除 X1、X2 外沒有找到放寬。

受保護規則：13 步驟與審核點、寫審分離、逐次同意與授權、安全刪法都沒動。X1、X2 不改 TDD 原文，只以 L7、L8 限定適用範圍，
並單獨列給人類。計畫審核找過鎖定句旁另加的例外：步驟 5 的「人類要求看圖時才給中間版本」與 L1 一致（停止條件或人類要求
時除外），不是新的例外。

## 鎖定句對照

新增 8 句，逐句對到人類核准的編號；替代句 L7' 沒用，檔案裡沒有。

| 編號 | 核准 | 檔案 |
|---|---|---|
| L1、L2、L3 | 一頁計畫 G1 | `asset-workflow/SKILL.md` |
| L4 | G5 | `asset-workflow/references/reference-review.md` |
| L5 | G2 | `asset-workflow/references/asset-management.md` |
| L6 | G3 | `asset-workflow/references/asset-management.md` |
| L7 | X1 | `asset-workflow/SKILL.md` |
| L8 | X2 | `asset-workflow/SKILL.md` |

另由守衛逐字核對的：兩條程序觸發行與三個 ART 標題（整合第 2 項）。既有鎖定句沒有改或刪。

## 守衛與測試

- 守衛只擴充既有清單，不改檢查邏輯。
- 測試先改、先紅：獨立清單同步，新增 asset-workflow 契約涵蓋、ART 標題順序、單字改動、F2 缺檔與空檔（Skill、兩份程序、
  兩個範本）、F4 frontmatter，清單一致性測試另比對 `CHECKPOINT_HEADINGS`。登記前 71 個失敗、909 個通過（失敗全是
  asset-workflow 相關）；寫內容並登記後全部通過。
- 鎖定句的既有參數化測試（刪除、藏進註解、重複、加字、縮排）經清單一致性測試自動涵蓋 L1～L8。

## 行數

與 `dev`（`c9a7d24`）比較（`git diff --numstat`，新增減刪除）。

| 項目 | 估計 | 實際 |
|---|---|---|
| 常駐載入的規則 | +101～154 | +120（asset-workflow SKILL +118、dev-workflow SKILL +2、improvement-loop SKILL 0） |
| 新 Skill 的 README、兩份程序、兩個範本 | +360～525 | +380 |
| 守衛與測試 | +160～290 | +339（守衛 +60、測試 +279） |
| README、術語表 4 份、SSOT、框架 AGENTS（共同區塊外）、ADR 與索引、HANDOVER、improvement-loop README | +191～356 | +309 |
| 整個 repo 淨變化 | +815～1,332（淨增超過 +1,998 才停） | **+1,148** |

測試比估計多 59 行：asset-workflow 的 F2、F4 測試照 improvement-loop 的寫法各寫一份，沒有和既有測試合併參數化，
以免改動既有測試的名稱。兩份程序比估計少，交付與發佈的細節寫在 SKILL 的步驟裡。停止線沒觸發。

## 不採用與保留觀察

- 不做：project-init 的美術專案初始化、量測與渲染工具、遊戲專案的對照、特定平台的發佈規格。
- 範圍外：ToukaDev 10 筆、第三個專案 15 筆待處理紀錄，留給下一次改進任務。
- 保留觀察：主觀評分的門檻由主代理自評；之後可以考慮讓人類只看主代理挑出的爭議點。動態指標受鏡頭運動影響，目前只記錄。

## 不變的部分

13 個步驟與全部審核點、5 種審核模式、寫的人和審的人分開、逐次同意與授權、資料保護、安全刪法與清理限制、改進任務的
人類關卡、四份共同區塊、其他 Skill 的流程。

## 後果

- 美術與素材有固定流程：人類在 ART-0 定標準，中間版本不必看；程式修改仍有 DEV-A、DEV-B。
- 已知限制：
  - 規則只經一個專案、一次版本試點；試點專案還沒照 ToukaDev 初始化。
  - 守衛只證明文字存在；在鎖定句旁另加例外段落照樣通過，要靠計畫審核找。
  - Git LFS 的檔案鎖沒有驗證過。
  - L7 的「否則…照 TDD」字面上也涵蓋 L8 的情況（量測已全數合格時，涵蓋的項目不是不合格）；X2 的豁免靠 L8 與步驟 5
    的文字表達，和 L7 的優先順序沒寫明。照嚴格讀法會回到 TDD，是偏嚴；改 L7、L8 的字要人類核准，留給下次改進任務。
  - debug-escalation 的「回原流程」只寫 dev-workflow 與 project-init，素材任務靠交班範本的「其他明確任務」接回；
    交付步驟沒有另寫更新 HANDOVER，照共同區塊的文件協議做。
  - 這次只重裝 Claude 的 Skills：ToukaDev 的 Skills 已在 10/16 移出 Codex；要裝時另外處理。
- 新 Skill 要重新安裝 Skills 才會生效；人類已同意本次合併後重裝 Claude 的 Skills。
