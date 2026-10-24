# ToukaDev 框架 SSOT

## 精確導航

已知正本直接讀；位置未知才查下表，不必先載入本檔後續全部契約。

| 問題／程式路徑 | 正本 |
|---|---|
| 根 Python／uv／測試環境 | [根目錄 uv 開發環境](#根目錄-uv-開發環境) |
| 文件快速路徑 L3 命令 | [最近作用域 AGENTS 的「Quick validation profile」段](../../AGENTS.md) |
| DEV-A／DEV-B 模式、完整候選與授權 | [審核協議](../../dev-workflow/references/review-protocol.md) |
| 主代理代審（預設）／同任務委託／DEV-A、DEV-B、DBG-A 調度／本機進度紀錄 | [主代理程序](../../dev-workflow/references/supervisor-delegation.md) |
| 進度紀錄格式／跨任務總覽板／進度網頁產生方式／暫存登記與清理 | [進度紀錄程序](../../dev-workflow/references/progress-record.md) |
| 多個執行者與多段計畫／角色／各工具名詞對照／派工對照表 | [多個執行者程序](../../dev-workflow/references/team-roles.md) |
| 流程問題紀錄（改進紀錄）的觸發、位置與格式 | [記錄程序](../../improvement-loop/references/recording.md) |
| 人類啟動的改進任務／受保護的規則／一頁計畫 | [改進任務程序](../../improvement-loop/references/improvement-run.md) |
| 美術素材的 art bible／參考基準／試量／量測規則修正／每輪對照／ART-1 交件 | [基準與對照程序](../../asset-workflow/references/reference-review.md) |
| 素材的五種狀態／命名與版本／鎖定／成品庫與參考庫／交付順序與發佈 | [素材管理程序](../../asset-workflow/references/asset-management.md) |
| INIT-B 後 greenfield 骨架協作／初始化 Debug／完整骨架驗收（選用時才讀） | [初始化協作程序](../../project-init/references/supervised-initialization.md) |
| 共通品質／Python、React 條件義務／品質分層 | [共同基線](../../AGENTS.md#程式碼品質) |

各列直達下方同名段落；不把全篇當作所有任務的前置讀取。


## AGENTS.md 命名

- 正式檔名：`AGENTS.md`
- 禁止使用任何非全大寫的大小寫變體作為正式規則檔
- 框架層與專案層由檔案所在位置區分，不由大小寫區分

## 共同工程規則

共同工程規則的正本位於根目錄 `AGENTS.md`：

```text
<!-- toukadev:shared-rules:begin -->
...
<!-- toukadev:shared-rules:end -->
```

下列檔案必須包含完全相同的共同區塊：

1. `AGENTS.md`
2. `project-init/assets/templates/AGENTS.md`
3. `examples/fastapi-todo-api/AGENTS.md`
4. `examples/line-bot/AGENTS.md`

`scripts/guard_framework.py` 負責驗證磁碟與 Git 索引中的檔名，以及共同區塊同步。

品質分為共通原則、語言／框架適用規則與專案實際驗證。Python 的型別與頂層匯入、React 的
元件及 Custom Hooks 義務保留適用範圍；SOLID 依範式逐項提供證據或合理不適用理由。
專案 spec 保存 INIT-B 核准的品質及骨架驗收條件，AGENTS 的「技術棧與執行命令」是實際命令
正本並引用既有工具配置；quick 宣告只寫在 AGENTS 的「Quick validation profile」段，不由品質表另設一份。
四份共同區塊的一致性與固定必要品質條款是有限文件契約，不代表任意程式已符合 SOLID。

初始化協作僅在兩個人類 gate 通過及明確委託後選用；共用委託及候選邊界仍由主代理程序管理。
初始化專用正本、Debug 返回點及品質分層的理由見
[ADR-032](../adr/ADR-032-初始化主代理協作與品質適用性分層.md)。

## 根目錄 uv 開發環境

ToukaDev framework root 是 non-package uv project：

- `.python-version`：Python minor version 正本；
- `pyproject.toml`：Python 相容範圍、uv required version、dev dependencies、pytest 與 Ruff 設定正本；
- `uv.lock`：解析後依賴版本與雜湊正本；
- `.venv/`：uv 建立的本機虛擬環境，不納入 Git；
- `.uv-cache/`：uv 與 pytest 的本機 cache，不納入 Git。

所有框架測試、lint 與 guard 一律由 `uv run --locked` 進入根環境。不得依賴全域 pytest／Ruff、
WindowsApps `python` shim 或任一 example 子專案的 `.venv`。CI 先執行 `uv sync --locked`，且 setup
action 與 uv required version 必須固定；lock 漂移時 fail closed，不得在驗證階段隱式重解。

此決策與回復邊界見 [ADR-015](../adr/ADR-015-ToukaDev根目錄uv工具鏈與可重現驗證環境.md)。

## 文件快速路徑的命令宣告

文件快速路徑 L3 要跑的命令，以最近作用域 `AGENTS.md` 的「Quick validation profile」段為正本，父子不合併：
ToukaDev 根執行 `uv run --locked python scripts/guard_framework.py`；project-init 範本與兩個 examples 執行
`guard_all.py`、`guard_security.py`，有 `mkdocs.yml` 時加跑 MkDocs。F17 整行鎖定這四份的命令行；原本的 JSON
schema 正本與 F10 已依 [ADR-039](../adr/ADR-039-13步驟程序精簡與審核小清尾.md) 退役。

## 按需程序

各 Skill 的詳細程序依 SKILL.md 的程序觸發行按階段讀取；所有適用父子規則仍有效。
`scripts/guard_framework.py` 的 F17 檢查步驟標題、審核點標題（整行、恰好一次、依序）、程序觸發行、
必要義務句（整行比對、恰好一次；少數 AGENTS、SKILL 片段用包含比對）、四份 HANDOVER 的固定標題與
「不是當次授權」聲明、程序文件不得再產生舊式 `docs/handover/` 日期交班檔，以及交班文件（四份 HANDOVER
全文）與導航段的相對連結（目標檔案須存在，不檢查 anchor）；F2 檢查程序引用。決策見
[ADR-034](../adr/ADR-034-主代理代審為預設與審核儀式精簡.md)。

## 進度紀錄與暫存清理

進度紀錄格式、進度網頁產生方式與暫存登記、清理規則的唯一正本為：

`dev-workflow/references/progress-record.md`

`dev-workflow/assets/progress/render_progress.py` 依這份格式產生網頁，不另定格式；網頁只是同一份紀錄的
另一種呈現，不是第二份正本。程式依紀錄的表頭顯示，不另存表頭；`tests/test_render_progress.py` 驗證正本與
`dev-workflow/assets/progress/example.md` 用的是同一組表頭，程式認得的必要區段與狀態值也和正本相同。
supervisor-delegation 只保留必要句並指向正本；四份 `AGENTS.md` 共同區塊只保留一行登記與清理規則。
AI 可自動清理的項目與刪法只以正本列出的為準。暫存資料夾只用 `dev-workflow/assets/progress/delete_tmp.py` 刪除：
刪之前在同一個程序裡重跑 `check_cleanup.py` 的 tmp 檢查，不另寫一份；每個條件由 `tests/test_tmp_delete.py` 鎖住。
決策見 [ADR-035](../adr/ADR-035-本機進度網頁與暫存清理.md)、
[ADR-037](../adr/ADR-037-第一次改進任務暫存範圍唯讀刪法與進度網頁.md)、
[ADR-038](../adr/ADR-038-第二次改進任務減法與獨立刪除腳本.md)。

## 改進紀錄與改進任務

流程問題紀錄（什麼要記、誰記、位置與檔名、格式、找重複、狀態權限、隱私、何時提醒）的唯一正本為：

`improvement-loop/references/recording.md`

改進任務（人類啟動、來源、分析、受保護的規則、一頁計畫、結案）的唯一正本為：

`improvement-loop/references/improvement-run.md`

紀錄範本 `improvement-loop/assets/templates/lesson.md` 依記錄程序的格式，不另定格式。紀錄放在各專案本機的
`.toukadev/lessons/`，不進版控；它是證據，不是授權，也不是 current。四份 `AGENTS.md` 共同區塊只保留一行
記錄規則；supervisor-delegation 的派工範本「回報」欄只加「流程或規則造成的困難」一項，一頁計畫段只加
「完成後要不要跑改進」一項並指向 improvement-run.md「啟動」。決策見
[ADR-036](../adr/ADR-036-改進迴圈Skill與流程問題紀錄.md)、[ADR-041](../adr/ADR-041-第四次改進任務團隊分工改進迴圈與建置產物宣告.md)。

## DEV-A／DEV-B 審核協議

DEV-A 與 DEV-B 的審核模式、變更風險、reviewer 路由、明確同意、審核包與結論狀態，唯一正本為：

`dev-workflow/references/review-protocol.md`

其他 Skills、README 與 `AGENTS.md` 只保留入口或不可違反的摘要，不得各自定義另一套完整流程。
正本中的 `review-policy:critical-rules` 區塊保存不可弱化語義。
`scripts/guard_framework.py` 的 F8 負責驗證必要標記、完整關鍵規則、有效使用端指令，
以及四份 `AGENTS.md` 共同區塊的必要審核規則。

### 審核 UX 與使用者可見名詞

審核輸出的 progressive disclosure 正本仍是
`dev-workflow/references/review-protocol.md`。每個 DEV-A／DEV-B 先顯示目前決定、風險、
傳輸內容、費用不確定性、推薦選項與一行核准方式；`HIGH`、`BLOCKING`、重大安全或不可逆風險
必須留在使用者可見摘要，`HUMAN_ONLY` 必須明說只有人類審核且未完成獨立 AI 技術驗證。

使用者可見名稱的正本是根目錄 `glossary.md`：

- 「精簡輸出模式」只縮短說明，machine token 仍是 `模式：精簡`；
- 「文件快速路徑」只處理純文件／typo，舊稱「`/quick`」仍可辨識；
- 「小型專案初始化」是 project-init 的小型設定。

`project-init/assets/templates/glossary.md` 必須與根正本完全一致；兩個 examples 的 glossary 也同步
相同相容映射。`scripts/guard_framework.py` 的 F11 驗證呈現規則、摘要必要欄位與順序、
四份 glossary 及 Skills、README、templates、examples 的 canonical 名稱。F11 不取代
F8 的 reviewer 資格／通過條件，也不建立任何傳輸、reviewer、commit 或不可逆操作授權。

完整決策與回復邊界見
[ADR-019](../adr/ADR-019-新手審核漸進揭露與使用者可見名詞契約.md)。

### Codex

嚴格單一 Codex reviewer runner、對抗式多代理測試腳本、Codex 原生 profiles 與 reviewer 專案部署生命週期
已依 ADR-033 退役，相關程式、Schema 與守衛已刪除；原生 reviewer 支援與 reviewer 設定檔也已移除。

### 跨 session 背景與授權

版本化 `AGENTS.md`、平台使用說明、交班文件與平台 Memory 可以保存長期規則、偏好、歷史
決策與已知能力限制。它們不得保存或推定當次 DEV-A／DEV-B 模式、外部資料傳輸同意、
多代理同意、開始實作、不可逆行動或 commit 授權；上述決定必須依當次對話重新取得。

## 舊名稱遷移

- 只有舊 `Agents.md`：先以兩段式改名遷移到 `AGENTS.md`，再補齊共同基線。 <!-- guard: F7-legacy-agents-ok -->
- 兩種名稱同時存在：停止流程，由人類確認保留內容；禁止自動覆蓋或合併。 <!-- guard: F7-legacy-agents-ok -->
