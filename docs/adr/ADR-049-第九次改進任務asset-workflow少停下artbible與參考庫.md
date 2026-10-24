# ADR-049：第九次改進任務：asset-workflow 少停下、art bible 與參考庫

- 日期：2026-10-24
- 狀態：已接受（一頁計畫 v2.1 由人類逐條核准：第 1、3 條兩項放寬單獨接受，第 4 條選「下次 ART-0 起必備」，第 2、5～11 條
  照建議，完成後不跑改進；不做對抗式複審；主代理代審，單一寫入者；實作在本 PR）
- 修訂：ADR-045 D5（L8）改字；ADR-045 D2「基準存進 `<作品>/reference-set/`」與 D3「基準用 LFS」改成參考庫
- 影響範圍：`asset-workflow/` 的 SKILL、兩份程序、README、兩個範本（新增 `art-bible.md`）；守衛 `scripts/guard_framework.py`
  與 `tests/test_guard_document_structure.py` 的清單；README、術語表 4 份、SSOT 導航、ADR 索引、HANDOVER。
  dev-workflow 與四份共同區塊沒動

## 背景

這是依 ADR-036 進行的第九次改進任務，由人類啟動，對象只有 asset-workflow。人類的方向：流程太重、偏離美術；審查的技術判定
不必問人類，但中間試作品與成品一定要人類看；要不要先定 art bible 統一同一專案的風格；參考影片不要進 repo。

來源是另一個影片專案的 5 筆待處理紀錄（5 組根因，外加 ADR-045 留給下次的 L7／L8 已知限制）；同一專案 1 筆屬 dev-workflow
的紀錄、ToukaDev 11 筆、第三個專案 19 筆依人類範圍留給下一次。只讀各專案的 `.toukadev/lessons/`；紀錄是證據，不是授權。
分析與一頁計畫經非作者的 DEV-A 3 輪（第 1 輪 CHANGES_REQUIRED：3 個 HIGH、10 個 MEDIUM；第 2 輪 PASS_WITH_NOTES；LOW 修正確認），
審的人先盲標鬆緊再對照作者版。

## 教訓

| 紀錄的教訓（概括） | 類型與次數 | 處理 |
|---|---|---|
| 美術任務在 ART-0 前為技術問題停下問人類 6 次，人類每次都選建議；下載同意另外問 3 次 | 反覆困擾 1 | D1 |
| 為難量化的缺陷先做大套量測工具（約 1,900 行、約 11 小時），做完多數指標只能記錄、仍靠評分 | 白做工 1 | D2 |
| 選用外觀和原版共用同一支著色器時，保護區「逐位元組相同」做不到，標準比工具能保證的更嚴 | 白做工 1 | D2 |
| 照規則把第三方參考影片 commit 進 repo（LFS）並推上遠端，事後只能改寫歷史、重建遠端 repo | 重大錯誤 1 | D5 |
| 計畫要求看齊全部時段評分，實際每輪只看第一段，缺陷到交件審稿才被發現 | 問題由他人發現 1 | D6 |
| 每個任務各自挑參考條件，同一專案的風格沒有定錨（人類的問句） | 反覆困擾（同第一筆） | D4 |

## 決定

1. **D1 技術判斷不中途問人類**（第 1 條，放寬，人類單獨核准）：
   - 核心原則加一段：技術判斷由主代理依證據決定，不停下問人類；主代理自己寫的內容照 dev-workflow 交審的人；人類決定美感（三關）、
     需求取捨，以及一頁計畫列出的預算、範圍、授權與預設做法。
   - 步驟 5：量測寫法、遮罩、量測框、工具做法由主代理決定，記進「替你做的技術決定」交 ART-1；ART-0 之後改的量測規則同時照 L4
     標待確認。量測方面的審核意見，寫的人照一頁計畫核准的預設做法修（照審的人的要求改，做不到就把那項指標改成只記錄、回到並排
     與主觀評分），改完照常交審的人確認；一頁計畫沒核准這項、仍不收斂，以及程式缺陷的審核意見，照 dev-workflow。
   - 技術判斷只在下列情況停下問人類：預算或停止線超標；改作品預設外觀、其他已核可作品或範圍外的檔案；受保護規則；planning 3-4
     不能套預設的逐次同意。停止條件、重過 ART-0、需求取捨與缺少必要證據照常提出。會改變成功標準的事 ART-0 前併進 ART-0。
   - 一頁計畫加「要下載的檔案」「預算」「量測方面審核意見的預設做法」；不必先下載或做工具就能量基準時，一頁計畫和 ART-0 一起交。
   - 下載：預覽寫明「挑中即同意下載挑中的這幾個檔」；預覽以外的檔與參考庫遺失後重新取得的檔另外同意。
   - 源頭：「需要人類決定的事照常提出」ADR-045 D1；兩輪上限與交人類 ADR-031、ADR-032、ADR-034；寫審分離 ADR-034。
2. **D2 先試量，再做工具**（第 2 條）：
   - reference-review 新段：正式工具前用拋棄式腳本在作品現況、基準與雜訊底線上試量，分得出缺陷才做工具；分不出的那類在 ART-0
     改用並排與主觀評分；要做新工具時，素材任務的一頁計畫寫指標與預估花費，工具本身另走 dev-workflow；預估比美術修改本身還大時附
     「只用並排與主觀評分」的做法。SKILL 適用性原句保留，後面加試量。
   - 雜訊底線：選用外觀和原版共用同一支程式時，另拍「加了新程式但關閉選用」對舊版；保護區容許範圍的算法與上限寫進一頁計畫由人類
     核可，超過才停；大於同一份程式的雜訊底線時 ART-1 列出；差異集中在新邏輯附近時當成漏進保護區。asset-management 那句指向這裡。
3. **D3 L8 改字**（第 3 條，放寬，人類單獨核准）：L8 → L8'，明寫 L8 的情況不必照 dev-workflow 的 TDD（解掉 ADR-045 的已知
   限制），並擴大到「修改只影響 ART-0 核可只用並排與主觀評分的畫面類別」。下一段收窄：ART-0 後改成只記錄、人類還沒確認的指標
   不算已全數合格；預設外觀不變、參數接線這類寫得出測試的行為仍照 TDD。ART-0 交件寫明哪些類別只用並排與主觀評分。L7 不改。
   源頭：ADR-045 D4／D5（X1、X2），更早是共同基線 ADR-001。
4. **D4 art bible**（第 4 條，人類選 (a)）：範圍由專案宣告（整個專案或每個作品）；1～2 頁加 6～12 張定錨圖；人類核可、記版本、
   上鎖；各任務 ART-0 只確認基準符合；還沒有時，下一次外觀任務的 ART-0 一併提出草稿；外部定錨圖放參考庫，從已核可作品挑的記
   tag 與時間點。範本 `assets/templates/art-bible.md`。
5. **D5 參考庫**（第 5 條）：鎖定句 L9。參考素材本身不進 repo（含 LFS），放專案宣告的參考庫（AGENTS.md 或作品 README，不能在
   repo 裡）；`<參考庫>/<作品>/<參考集>/` 加 `SHA256SUMS`、核可後不改；任何清理不碰、不推送不上傳不發佈；備份責任；遺失時依下載
   同意重新取得並核對；既有 repo 裡的參考檔不再新增，搬移照該專案自己的計畫。五種狀態仍是五種，原始素材分「自己做的」與
   「外部取得的參考」兩種存法；目錄骨架、LFS 段、範本 `reference-set.json`（`store`、`bytes`、參考庫內路徑）同步。
6. **D6 評分看齊全部畫面**（第 6 條）：每一類寫明作品要看哪些畫面與時段；中間各輪可只看一部分但要寫明；交 ART-1 前最後一輪用
   全部重拍、重評，ART-1 的評分以這一輪為準；ART-1 交件寫每項評分看了哪些；範本加 `workWindows`。
7. **D7 減法**（第 7 條）：SKILL 步驟 5「連續 3 輪…就停」刪掉（reference-review 停止條件原本就有）；SKILL ART-1 交件清單改指向
   reference-review「ART-1 交件」；reference-review 兩處重述 L7／L8 的句子縮短。每個要求都還在。

## 決定落點表

行號是本 PR 的位置，只供核對時找，以檔案與段落為準。

| 項次 | 決定 | 檔案 | 段落（行號附近） |
|---|---|---|---|
| D1 | 技術判斷由主代理決定、人類決定什麼 | `asset-workflow/SKILL.md` | 核心原則末段（L39–40） |
| D1 | 一頁計畫的下載、預算、預設做法、和 ART-0 一起交 | `asset-workflow/SKILL.md` | 步驟 2（L60–66） |
| D1 | 技術判斷、預設做法、停下情況、成功標準 | `asset-workflow/SKILL.md` | 步驟 5 第 3～6 子項（L85–92） |
| D1 | ART-1 一定有替你做的技術決定；禁止清單 | `asset-workflow/SKILL.md` | ART-1（L99）；禁止清單（L128） |
| D1 | 下載同意寫法 | `asset-workflow/references/reference-review.md` | 「挑選基準」第 2 項（L21–23） |
| D1 | 替你做的技術決定的範圍 | `asset-workflow/references/reference-review.md` | 「ART-1 交件」（L119–120） |
| D1 | 中途找你的情況 | `asset-workflow/README.md` | 「你會看到的三個審核點」後段 |
| D2 | 試量、工具比例 | `asset-workflow/references/reference-review.md` | 「先試量，再做工具」（L54–60） |
| D2 | 共用程式的雜訊底線與保護區上限 | `asset-workflow/references/reference-review.md` | 「畫面分類與衡量方式」末項（L49–52） |
| D2 | 指向同一正本 | `asset-workflow/references/asset-management.md` | 「共用素材與範圍外的段落」第 2 項（L116–117） |
| D2 | 適用性加試量；保護區上限列進一頁計畫 | `asset-workflow/SKILL.md` | 「適用性」第 2 項（L47–48）；步驟 2（L63） |
| D3 | L8' 與收窄的下一段；ART-0 交件寫只用並排的類別 | `asset-workflow/SKILL.md` | L34、L36–37；ART-0（L72–74） |
| D4 | art bible 段 | `asset-workflow/references/reference-review.md` | 「art bible」（L6–15）；「挑選基準」第 1 項 |
| D4 | 恢復狀態、ART-0 對照 | `asset-workflow/SKILL.md` | 步驟 1（L59）；ART-0（L72） |
| D4 | 目錄骨架、第一次使用；範本 | `asset-workflow/references/asset-management.md`、`asset-workflow/assets/templates/art-bible.md` | L35、L145–146；全檔 |
| D5 | L9 與參考庫段 | `asset-workflow/references/asset-management.md` | 「參考庫」（L71–81） |
| D5 | 五種狀態、目錄骨架、LFS | `asset-workflow/references/asset-management.md` | L11、L37、L42、L97–98 |
| D5 | 存放與紀錄 | `asset-workflow/references/reference-review.md` | 「基準的存放與紀錄」（L29–37） |
| D5 | ART-0 寫入參考庫；禁止 commit 參考檔 | `asset-workflow/SKILL.md` | ART-0 第 2 段（L77–78）；禁止清單（L124–125） |
| D5 | 範本 | `asset-workflow/assets/templates/reference-set.json` | `store`、`bytes`、`file` |
| D6 | 要看的畫面、最後一輪全部重評、交件 | `asset-workflow/references/reference-review.md` | L42；「每一輪對照」第 3 項（L78–79）；「ART-1 交件」第 3 項 |
| D6 | ART-0 交件；範本 | `asset-workflow/SKILL.md`、`reference-set.json` | ART-0（L73）；`workWindows` |
| D7 | 減法 | `asset-workflow/SKILL.md`、`asset-workflow/references/reference-review.md` | 步驟 5、ART-1；「每一輪對照」第 1 項、「量化與主觀的取捨」第 3 項 |
| — | 守衛與測試清單 | `scripts/guard_framework.py`、`tests/test_guard_document_structure.py` | `REQUIRED_OBLIGATIONS`；`ASSET_OBLIGATIONS`、`ASSET_TEMPLATES` |
| — | 文件同步 | `README.md`、`glossary.md` 與 3 份複本、`docs/ssot/README.md` | asset-workflow 介紹、流程圖、目錄樹；「參考庫」「art bible」；精確導航兩列 |

## 規則鬆緊與受保護規則

作者與審的人（DEV-A）各自標記；審的人先盲標。

| 項次 | 改動 | 作者 | 審的人 | 核准方式 |
|---|---|---|---|---|
| D1 | 技術判斷不中途問人類、改在 ART-1 看 | 放寬 | 放寬 | 人類單獨核准 |
| D1 | 量測方面審核意見的預設做法 | 放寬（併在 D1） | 不變（每次由一頁計畫核准，和 dev-workflow 的不收斂規則不衝突） | 同上 |
| D1 | 下載同意併進挑候選 | 放寬（輕微，併在 D1） | 不變 | 同上 |
| D1 | 一頁計畫加下載、預算、預設做法；ART-1 一定列技術決定 | 加嚴 | 加嚴 | 照建議 |
| D2 | 試量、工具比例、集中度檢查 | 加嚴 | 加嚴 | 照建議 |
| D2 | 保護區容許範圍改由一頁計畫核可上限 | 加嚴 | 不變 | 照建議 |
| D3 | L8 → L8'（兩處） | 放寬 | 放寬 | 人類單獨核准 |
| D3 | 下一段收窄 | 加嚴 | 加嚴 | 同上 |
| D4～D6 | art bible、參考庫與 L9、評分涵蓋 | 加嚴 | 加嚴 | 照建議 |
| D7 | 減法 | 不變 | 不變 | 照建議 |

- 受保護規則：13 步驟與審核點、寫審分離、逐次同意與授權、安全刪法與清理、資料保護、改進迴圈的人類關卡都沒動。D3 碰到共同禁止行為
  「先寫實作再補測試」，照受保護規則單獨列給人類並附源頭。D1 不改寫審分離：寫的人照審的人的要求改或改成只記錄，再交審的人確認；
  dev-workflow 的兩輪上限、第二次 HIGH 交 debug-escalation 與審核協議 2.1 第 7 條都照舊。
- 鎖定句旁的寫法：asset-management L5 正下方第 2 項加了括號「選用外觀和原版共用同一支程式時，用一頁計畫核可的上限」。這是指向
  reference-review 的同一正本，上限由人類每次在一頁計畫核可、超過就停，DEV-A 判不放寬。L8' 下一段另起一段，內容是收窄與照常
  執行的檢查。計畫審核找過其他鎖定句旁，沒有另加例外。

## 鎖定句對照

| 編號 | 動作 | 核准 | 檔案 |
|---|---|---|---|
| L8' | 改字 | 一頁計畫第 3 條（單獨接受） | `asset-workflow/SKILL.md` |
| L9 | 新增 | 一頁計畫第 5 條 | `asset-workflow/references/asset-management.md` |

L1～L7 沒有改或刪；兩條程序觸發行與三個 ART 標題不變。

## 守衛與測試

- 守衛只換清單內容（L8 改字、加 L9），檢查邏輯不改。
- 測試先改、先紅：`ASSET_OBLIGATIONS` 改 L8、加 L9，`ASSET_TEMPLATES` 加 art-bible；套用前 13 個失敗、637 個通過（全是新期望），
  套用規則與守衛清單後全部通過。L9 的刪除、藏進註解、重複、加字、縮排、單字改動，經既有參數化測試自動涵蓋。

## 行數

與 `dev`（`5e37752`）比較（`git diff --numstat`，新增減刪除）。

| 項目 | 估計 | 實際 |
|---|---|---|
| 常駐載入的規則 | +13～+22 | +17（asset-workflow SKILL；四份共同區塊與其他 SKILL 0） |
| asset-workflow 兩份程序 | +38～+60 | +44 |
| 範本 | +30～+45 | +36 |
| asset-workflow README | +5～+12 | +7 |
| 守衛與測試 | +10～+25 | +11（守衛 +5、測試 +6） |
| README、術語表 4 份、SSOT、ADR 與索引、HANDOVER | +170～+270 | +214（ADR +173、術語表 +32、HANDOVER +5、README +3、索引 +1、SSOT 0） |
| 整個 repo 淨變化 | +270～+430（淨增超過約 +645 才停） | **+329** |

## 不採用與保留觀察

- 範圍外：同一專案「紀錄時間用估的」（dev-workflow 已有「一律取系統時間」，是執行問題）、ToukaDev 11 筆、第三個專案 19 筆，
  留給下一次。既有專案 repo 裡參考檔的搬移由各專案自己的計畫處理。
- 保留觀察：「技術判斷不中途問人類」靠 ART-1 的技術決定清單事後把關，推翻時要重做那段；art bible 只要求下一次 ART-0 起有，
  還沒有實際用過。

## 不變的部分

13 個步驟與全部審核點、5 種審核模式、寫的人和審的人分開、dev-workflow 的不收斂規則、逐次同意與授權、資料保護、安全刪法與
清理限制、改進任務的人類關卡、四份共同區塊、其他 Skill 的流程、ART-0／1／2 三關。

## 後果

- 美術任務中途找人類的情況只剩預算、範圍、受保護規則、逐次同意、停止條件與需求取捨；技術判斷改在 ART-1 一次看。
- 參考素材不再進 repo；參考庫通常只有一份，要靠人類備份，遺失時照清單重新取得。
- ADR-045 後果裡「L7 的『否則…照 TDD』字面上也涵蓋 L8 的情況」這項已知限制由 D3 解掉。
- 已知限制：
  - 守衛只證明文字存在，不證明 agent 會照做；保護區上限、預設做法是否每次寫進一頁計畫，靠計畫審核。
  - 試量「明顯大於」沒有固定數字，由主代理判斷並寫進 ART-0 交件。
  - 規則只經一個專案的兩次版本；art bible 與參考庫還沒有實際用過。
- 改動要重新安裝 asset-workflow Skill 才生效；人類已同意本次合併後重裝 Claude 的 Skill。
