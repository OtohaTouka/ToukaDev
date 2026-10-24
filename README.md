# Human-AI Collaborative Development Skills

## English summary

ToukaDev is a set of five Skills (Markdown procedures plus small Python guard scripts) for building software with
AI coding agents, including when the human does not read code. Any tool that can read a `SKILL.md` can follow them;
Claude Code and Codex pick a Skill from its `SKILL.md` description, and with other tools you ask the agent to follow
a Skill.

- **project-init**: set up a new or existing project once (requirements interview, stack choice, docs skeleton,
  tests, lint, guards and CI).
- **dev-workflow**: the 13-step loop for every feature or fix, with TDD, a single source of truth (SSOT), ADRs and two
  mandatory review points (DEV-A for the plan, DEV-B for the finished change). By default the main agent reviews on
  the human's behalf once the human approves a one-page plain-language plan; the writer and the reviewer are never
  the same agent.
- **debug-escalation**: when an agent hits the same error three times, it stops, hands off, and a fresh context does
  the root-cause analysis before a reviewed fix.
- **improvement-loop**: problems with the process itself are recorded; the human starts an improvement run and
  approves each rule change.
- **asset-workflow**: for visual and audio assets that are judged against a human-approved reference instead of tests.

The documents are in Traditional Chinese. [Touka](https://github.com/OtohaTouka/Touka) is a project built with this
method. Installation is copying the Skill folders (see 安裝 below). See [CONTRIBUTING.md](CONTRIBUTING.md) to
contribute and [SECURITY.md](SECURITY.md) to report a security problem. License: MIT.

---

文件入口：[目前狀態](HANDOVER.md)、[介面導航](docs/interface/README.md)、[SSOT 導航](docs/ssot/README.md#精確導航)。
已知文件直接讀，未知才查導航；五個 Skills 的詳細程序按階段展開，HUMAN_ONLY 不載入 reviewer 操作手冊。


一套經過實戰驗證的 AI 輔助開發方法論，讓不懂程式的人也能交付複雜的軟體專案。

## 實戰成果

完成的**Touka**專案，GitHub 傳送門：[GitHub連結](https://github.com/OtohaTouka/Touka)

## 這套方法論解決什麼問題

用 AI 寫程式很容易，讓 AI 持續、穩定、不亂跑地寫出可維護的程式碼很難。

常見的失敗模式：
- AI 每次進來都要重新解釋一遍專案背景
- AI 在不同地方重複定義相同的東西，最後自相矛盾
- AI 陷入除錯迴圈，一直試一直失敗
- AI 寫完功能，文件沒更新，下一個 AI 不知道發生了什麼
- 人類不知道該在哪個時間點介入
- 流程或規則出錯、讓人困擾，下次還是照舊

這套 Skills 透過結構化流程、強制審核點、交班文件機制與改進迴圈，系統性地解決上述問題；
作品的外觀與素材另有「先定基準，再逼近基準」的美術素材流程。

---

## 五個 Skill，各司其職

```
project-init        dev-workflow          debug-escalation      improvement-loop
─────────────       ────────────          ────────────────      ────────────────
新專案用            每個功能/修復都用     AI 卡住時才用         流程或規則出問題時
只跑一次            反覆循環              每次危機只用一次      記錄後由人類啟動改進
      │                   │                      │                     │
      └───────────────────┴──────────────────────┴─────────────────────┘
                               統一的核心原則
                     TDD · SSOT · SOLID · ADR · 交班文件

asset-workflow（美術素材版，和 dev-workflow 並列）
──────────────
作品外觀與素材：先定基準 → 主代理自己對照基準逼近 → 人類審基準、試作品、成品
其中的程式修改仍經 DEV-A、DEV-B
```

### project-init｜專案初始化

新專案建立時執行，包含需求訪談、技術棧評估、目錄結構、文件骨架、測試基礎建設、靜態檢查、CI/CD 設定。**每個專案只跑一次。**

INIT-A／INIT-B 保留人類確認。全新專案兩關通過且明確委託後，可由主代理派工、審查範圍內
執行計畫與 DBG-A、退修並驗收步驟 6–12 的完整骨架；詳細流程只在選用時讀
[初始化協作程序](project-init/references/supervised-initialization.md)。規格同意不自動選用代審，
brownfield 沿原導入路線。必要驗證尚待建立時保留待驗項，全部適用項目完成才可宣告初始化完成；
空測試、本地 CI 設定或未實跑部署不得算作相應功能已驗證。Git 與後續功能依實際委託，
可交付「骨架已驗收，Git 未提交」。

### dev-workflow｜標準開發循環

13 步驟的人機協作開發流程，涵蓋 TDD 紅綠重構循環、靜態檢查、文件更新、冒煙測試，
並設有兩個強制審核點（DEV-A、DEV-B）。預設由主代理代審：人類核准一頁白話計畫後，主代理派 agent 執行並審核，
寫的人和審的人不能是同一個；人類可隨時改選其他模式。**每個功能或修復都跑**；純文件或錯字級修正可走文件快速路徑（仍保留 DEV-B）。
文件快速路徑的 L3 不再假設固定 guard 名稱；它執行專案 `AGENTS.md`「Quick validation profile」段列出的命令，
沒有宣告或宣告的檔案不存在時在修改前停止、改回完整步驟3。文件快速路徑用自然語言或直接執行 Skill 啟動。
熟練使用者可選精簡輸出模式；它只縮短說明，不會省略 TDD、guard、審核點或適用的授權核對。

### debug-escalation｜除錯升級

當 AI 偵測到自己陷入除錯迴圈（重複相同動作三次）時觸發，保留失敗交班、執行根本原因分析、
撰寫修復計畫並經 DBG-A 審核。主代理代審（預設）時由主代理分派新的分析上下文，同模型也可如實使用；
其他模式由人類切換高階模型。**卡住時才用，解完回來源流程的精確中斷點。** 初始化事故回原 project-init
步驟；dev 事故回原 dev 步驟與 DEV-B，原 FAIL 及同問題修正上限不因換 agent 而清零。

### improvement-loop｜改進迴圈

ToukaDev 的 13 步驟與審核點都是因實際出過大錯才加上去的；這個 Skill 讓流程本身的改進有固定管道。
**平常記錄**：照做或沒照做而出重大錯誤、問題到合併後或由人類才發現、人類對同一件事第二次糾正或表示流程
造成困擾、某個步驟花了成本卻沒有作用（白做工）時，AI 在主要專案資料夾的本機 `.toukadev/lessons/` 記一筆，
記完繼續原本的工作；紀錄不是授權。
**改進任務只由人類啟動**（人類說要開始，或在大任務的一頁計畫核准做完後跑改進；後者在主要任務合併並清理後才開始）：
AI 讀累積的紀錄（第一次會問要讀哪些專案），整理成一頁白話計畫，人類逐條核准後，
照一般 dev-workflow（含 DEV-A、DEV-B）修改 ToukaDev。13 步驟、審核點、授權、安全刪法與改進迴圈自己的
人類關卡等受保護的規則預設保留，要移除或弱化時必須單獨列出並附上當初的源頭。程序見
[記錄程序](improvement-loop/references/recording.md) 與 [改進任務程序](improvement-loop/references/improvement-run.md)。

### asset-workflow｜美術素材流程

影片、插畫、遊戲美術、配樂與音效這類「驗收標準是對照人類核可的參考基準」的作品外觀與素材使用；
軟體介面與分不清的情況走 dev-workflow。美感沒辦法先寫測試，所以把「先寫測試」換成**先定基準**：
開工前人類和主代理來回確認參考基準（例如十張概念圖、一段實拍影片）與衡量方式（ART-0），之後主代理
自己對照基準逼近，中間版本不請人類看圖；人類再看試作品（ART-1）與成品（ART-2）。量化通過不等於核可；
改共用素材要和已核可的作品逐段比對；交付的版本合併、確認能重現並歸檔到成品庫後才打 tag。
其中的程式修改仍經 DEV-A、DEV-B 與 commit 授權。程序見
[基準與對照](asset-workflow/references/reference-review.md) 與 [素材管理與交付](asset-workflow/references/asset-management.md)。

---

## 核心設計原則

**TDD（測試驅動開發）**
先寫測試、確認失敗、再實作、確認通過、重構。AI 不得先寫實作再補測試。

**SSOT（單一事實來源）**
每個常數、型別定義、設定值只在一個地方定義，其他地方引用。搭配驗證腳本自動檢查違反。

**SOLID**
單一職責、開放封閉、里氏替換、介面隔離、依賴反轉。依語言、範式與當次變更逐項說明
設計證據或合理不適用原因，不為湊項目新增無需求的 class、繼承、interface 或 Registry。
lint 與測試提供部分證據，不能取代設計審查或證明任意程式完整符合 SOLID。

**ADR（架構決策記錄）**
重要技術決策必須記錄原因，讓後續 AI 不重複踩坑。

**交班文件**
只有狀態、阻礙或下一步改變才更新根 HANDOVER.md，讓新 AI 按精確連結接手；指定文件唯讀問答可直達。
平台 Memory 可補充長期偏好，但不會保存或代表當次審核、資料傳輸、多代理、實作或 commit 授權。

**審核點與人類決策**
每個 Skill 都有明確標記的介入點，其餘由 AI 自動執行：project-init 是 INIT-A／INIT-B（維持人類審核）；
dev-workflow 是 DEV-A（實作計畫）與 DEV-B（實際變更與驗證證據，通過後才合併或提交進共用分支）；
debug-escalation 是 DBG-OP 與 DBG-A；improvement-loop 由人類逐條核准一頁計畫，再走 DEV-A、DEV-B；
asset-workflow 是 ART-0（基準）、ART-1（試作品）、ART-2（成品）三個人類審核點，其中的程式修改仍有 DEV-A、DEV-B。

DEV-A／DEV-B 依 `dev-workflow/references/review-protocol.md` 提供五種模式：
人類、單一獨立 AI 代審、人類加 AI、對抗式多代理複審、主代理代審（預設 `SUPERVISOR_DELEGATED`）。
寫的人和審的人不能是同一個，寫的人不得推翻審的人提出的 `HIGH`／`BLOCKING`。
`HIGH` 只有命中具體觸發條件才會建議多代理，`CRITICAL` 會強烈建議一次，每次都必須取得人類明確同意。
送資料到其他 AI 服務前也要先取得同意，無法說明對方條件時不得傳送；任何成果合併進共用分支前都必須通過 DEV-B。

**主代理代審（預設）**
主代理把計畫整理成一頁白話版，經非作者的 reviewer 審、人類核准後即為本任務的委託；之後派工、審核、
退修與驗收，超出委託或無法收斂才返回人類。進度記在本機 `.toukadev/progress/` 並轉成網頁，人類雙擊
`index.html` 就能看；任務的暫存一建立就登記，結束時只用安全刪法清理，預設與共用分支永遠不刪，其他先問人類。
詳見 [主代理代審程序](dev-workflow/references/supervisor-delegation.md) 與 [進度紀錄程序](dev-workflow/references/progress-record.md)。
一頁計畫派兩個以上執行者並行或一次核准多段計畫時，角色、各工具的名詞對照與派工見 [多個執行者程序](dev-workflow/references/team-roles.md)。

---

## 工具相容性

| 工具 | 支援 | Skill 觸發方式 |
|------|------|---------------|
| Codex desktop／CLI | ✅ | 依 SKILL.md 觸發 |
| Claude Code | ✅ | 自動——依 SKILL.md 的描述與任務關鍵字觸發 |
| Gemini CLI | ✅ | 手動——指示 AI「讀取並依照 ○○ Skill 執行」 |
| Antigravity | ✅ | 手動——同上 |
| Cline | ✅ | 手動——同上 |
| Cursor / Windsurf | ✅ | 手動——同上，或將 SKILL.md 掛進工具的 rules 機制 |

Skills 是工具無關的（tool-agnostic）。只要工具支援讀取 SKILL.md，即可使用；「自動觸發」則是 Claude Code 的機制。

表中的「支援」只表示能讀取並遵循 Markdown 流程，不代表工具一定能自動建立合格的獨立 reviewer。
要取得嚴格獨立 reviewer 資格，還必須能證明全新上下文、候選工作樹唯讀與禁止 delegation。
原四模式的 AI reviewer 無法確認實際使用的模型時必須說明，結論最高 `PASS_WITH_NOTES`，不能滿足
`AI_DELEGATED` 的自動繼續或 commit。缺少必要能力時，改用隔離審核包、手動交接或人類審核。
主代理代審使用另一份流程契約，不以 runtime attestation 作入口條件，也不聲稱
未知能力已獲證明。Codex、Claude Code 是首批試行環境；其他工具不因名稱而被排除，各平台及
調度方式是否實跑通過以當次 evidence 為準，上表不構成新模式端到端驗證。

所有 ToukaDev 專案統一使用 `AGENTS.md` 作為規則正本，但各工具是否自動載入該檔仍由工具本身決定。需要其他規則檔名的工具，應以匯入或設定指向 `AGENTS.md`，不要維護第二份完整規則。

---

## 語言與框架相容性

| 語言 | 測試框架 | 靜態檢查 |
|------|---------|---------|
| Python | pytest | ruff |
| JavaScript | Jest | ESLint |
| TypeScript | Vitest | ESLint |
| 混合專案 | 兩者並存 | 兩者並存 |

適用於 Web 後端、前端、API、資料管線、CLI 工具、DevOps 自動化等大多數開發場景。

共通品質原則以 AGENTS 共同區塊為正本；Python 保留型別與模組頂層匯入要求，React 保留元件
分責及領域 Custom Hooks，其他 UI 框架依自身慣例建立領域資料存取抽象。spec 在 INIT-B 記錄
品質與初始化驗收條件，實際命令集中於專案 AGENTS「技術棧與執行命令」及其引用的工具配置。
品質分層不改 AGENTS 的 quick 宣告，也不省略已宣告的檢查命令。

上述 Python／JS／TS 是現有工具流程；Rust、Go、Java、C# 等可採用共通原則，但尚未提供
完整初始化模板與原生檢查 adapter。INIT-A／INIT-B 須揭露模板、測試、lint、型別與安全掃描
缺口，補齊本專案必要驗證方式前不承諾自主完成，不能以現有守衛通過宣稱全面支援。

> **注意**：守衛腳本（`guard_*.py`）一律以 Python 實作——純 JS/TS 專案也需要安裝 uv（Python 環境）才能執行靜態守衛。

---

## 開發 ToukaDev framework

根目錄是由 uv 管理的 non-package Python project。Python minor version、uv 版本、測試與靜態檢查
依賴分別由 `.python-version`、`pyproject.toml` 與 `uv.lock` 管理；不得改用全域 pytest／Ruff 或
examples 的虛擬環境。uv 要 0.12.1 以上；CI 固定用 0.12.1。貢獻方式見 [CONTRIBUTING.md](CONTRIBUTING.md)。

```bash
uv sync --locked
uv run --locked pytest tests
uv run --locked ruff check scripts tests project-init dev-workflow
uv run --locked python scripts/guard_framework.py
```

uv 預設建立根目錄 `.venv`。本 repo 將 uv 與 pytest cache 放在同磁碟的 `.uv-cache`，避免依賴
使用者層 cache ACL；兩個目錄都是本機產物，不納入 Git。

---

## 安裝

> **更新既有安裝前，必須先刪除已安裝的舊 Skill 資料夾**（例如 `~/.claude/skills/dev-workflow`）再複製。
> `cp -r`／`Copy-Item` 只會覆蓋或新增檔案，不會刪除舊版留下、新版已移除的檔案。

**macOS / Linux（bash）：**

```bash
# 複製所有 Skills 到 Claude Code
cp -r project-init ~/.claude/skills/
cp -r dev-workflow ~/.claude/skills/
cp -r debug-escalation ~/.claude/skills/
cp -r improvement-loop ~/.claude/skills/
cp -r asset-workflow ~/.claude/skills/
cp glossary.md ~/.claude/skills/   # 術語表（dev-workflow、debug-escalation 的 SKILL.md 會連結到它）
```

**Windows（PowerShell）：**

```powershell
# 複製所有 Skills 到 Claude Code
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force project-init, dev-workflow, debug-escalation, improvement-loop, asset-workflow "$HOME\.claude\skills\"
Copy-Item glossary.md "$HOME\.claude\skills\"   # 術語表（dev-workflow、debug-escalation 的 SKILL.md 會連結到它）
```

重啟 AI 工具後即可使用。Claude Code 會依任務描述自動觸發對應 Skill；其他工具請直接指示 AI「讀取並依照 ○○ Skill 執行」（見上方工具相容性表）。

---

## 使用流程

```
新專案？
  └─ 執行 project-init
       └─ 完成後進入 dev-workflow 循環

既有專案想導入？
  └─ 執行 project-init（步驟前檢查偵測到既有程式碼會詢問）
       └─ 盤點現況 → 反推規格 → 補文件骨架 → 守衛基線 → 進入 dev-workflow 循環

新功能 / 修復 / 重構？
  └─ 執行 dev-workflow
       ├─ [步驟3｜DEV-A] 審核實作計畫 ← 預設主代理代審（人類核准一頁計畫即啟用）
       ├─ AI 自動執行步驟4-11
       ├─ [步驟12｜DEV-B] 審核綁定 git 編號的成果與證據 ← 主代理委託內不重問模式
       └─ [步驟13] DEV-B 通過且取得授權後 commit 或合併進共用分支

AI 卡住（重複三次相同動作）？
  └─ 自動觸發 debug-escalation
       ├─ 當前模型寫交班文件
       ├─ [DBG-OP] 主代理分派新分析上下文（預設），或人類換模型
       ├─ 分析角色完成五維根本原因分析
       ├─ [DBG-A] 有效委託內由主代理代審（預設），或人類確認修復計畫
       └─ 解完回到 dev-workflow

流程或規則出問題（出大錯、問題到合併後才發現、同一件事第二次糾正、白做工）？
  └─ improvement-loop 記錄到本機 .toukadev/lessons/
       └─ 記完繼續原本的工作（紀錄不是授權，不改規則）

想改進 ToukaDev？
  └─ 人類啟動 improvement-loop 的改進任務（或在大任務的一頁計畫核准做完後跑）
       ├─ AI 讀累積的紀錄，整理成一頁白話計畫
       ├─ 人類逐條核准
       └─ 照一般 dev-workflow（DEV-A、DEV-B）修改 ToukaDev

做作品的外觀或素材（影片、插畫、遊戲美術、配樂），要對照參考基準驗收？
  └─ 執行 asset-workflow
       ├─ [ART-0] 人類和主代理定下參考基準與衡量方式，核准計畫
       ├─ 主代理自己對照基準逼近（其中的程式修改仍經 DEV-A）
       ├─ [ART-1] 人類看試作品：並排圖、量化結果、未達標項目
       ├─ [ART-2] 人類核可成品
       └─ DEV-B 通過後合併，確認能重現並歸檔到成品庫，再打 tag
```

---

## 目錄結構

```
ToukaDev/
├── README.md                   ← 你在這裡
├── AGENTS.md                   ← 框架層 AI 規則
├── HANDOVER.md                 ← 目前狀態與精確入口
├── CONTRIBUTING.md             ← 貢獻方式（英文與中文）
├── SECURITY.md                 ← 私下回報安全問題
├── pyproject.toml              ← 根目錄 uv、pytest 與 Ruff 設定
├── uv.lock                     ← 根目錄鎖定依賴
├── .python-version             ← 根目錄 Python minor version
├── glossary.md                 ← 術語表（白話版）
├── project-init/
│   ├── README.md
│   ├── SKILL.md
│   ├── assets/templates/       ← 文件、設定與守衛腳本範本
│   └── references/             ← 訪談／導入指南與按需程序
├── dev-workflow/
│   ├── README.md
│   ├── SKILL.md
│   ├── assets/progress/        ← 本機進度網頁
│   │   ├── render_progress.py  ← 把進度紀錄轉成網頁（Python 標準函式庫）
│   │   ├── check_cleanup.py    ← 清理前檢查（只檢查、不刪除）
│   │   ├── delete_tmp.py       ← 刪除本任務的暫存資料夾（刪前自己重跑清理前檢查）
│   │   └── example.md          ← 進度紀錄範例
│   └── references/             ← 審核協議、按需程序、安全清單
│       ├── progress-record.md  ← 進度紀錄格式、進度網頁與暫存清理
│       └── team-roles.md       ← 多個執行者與多段計畫：角色、名詞對照與派工
├── debug-escalation/
│   ├── README.md
│   ├── SKILL.md
│   └── references/             ← 事故交棒與根因恢復程序
├── improvement-loop/
│   ├── README.md
│   ├── SKILL.md
│   ├── assets/templates/       ← 改進紀錄範本
│   │   └── lesson.md
│   └── references/             ← 記錄與改進任務程序
│       ├── recording.md        ← 什麼要記、位置、格式與何時提醒
│       └── improvement-run.md  ← 人類啟動的改進任務、受保護的規則與一頁計畫
├── asset-workflow/
│   ├── README.md
│   ├── SKILL.md
│   ├── assets/templates/       ← 基準清單與成品紀錄範本
│   │   ├── reference-set.json
│   │   └── releases.json
│   └── references/             ← 基準對照與素材管理程序
│       ├── reference-review.md ← 挑基準、量測、每輪對照與 ART-1 交件
│       └── asset-management.md ← 五種狀態、命名、鎖定、交付與發佈
├── docs/
│   ├── adr/                    ← 框架層架構決策
│   ├── interface/              ← 框架層介面導航（目前沒有框架層介面）
│   └── ssot/                   ← 框架層單一事實來源
├── tests/
│   ├── test_guard_framework.py ← 框架守衛測試
│   ├── test_guard_document_structure.py ← 程序標題、審核點、義務句與交班連結守衛測試
│   ├── test_render_progress.py ← 進度網頁產生程式測試
│   ├── test_check_cleanup.py   ← 清理前檢查程式測試
│   ├── test_tmp_delete.py      ← 暫存資料夾刪除程式（delete_tmp.py）測試
│   ├── test_root_toolchain.py  ← 根目錄 uv 工具鏈契約測試
│   └── test_public_defaults.py ← 共同區塊不含個人偏好、範本的 CI 與 Docker 釘版且用 uv
├── scripts/
│   └── guard_framework.py      ← 框架一致性、AGENTS 命名、共同基線與程序標題檢查
└── examples/                   ← 範例專案（fastapi-todo-api、line-bot）
```

---

## AGENTS.md 的兩個層級

框架與專案都使用標準檔名 `AGENTS.md`，由所在位置決定作用域：

| 檔案 | 位置 | 管什麼 |
|------|------|--------|
| `ToukaDev/AGENTS.md` | 框架根目錄 | 框架本身的 AI 行為規則（維護、改進 ToukaDev 時使用） |
| `[你的專案]/AGENTS.md` | 每個新專案根目錄 | 那個專案的 AI 行為規則（由 project-init 自動建立） |

**一般使用者只需要關心自己專案裡的 `AGENTS.md`。**
`ToukaDev/AGENTS.md` 只在你想修改框架本身時才需要碰。

---

## 需要客製化的部分

project-init 產生的預設路徑與可調整項目見 [project-init/README.md](project-init/README.md)。

---

## 授權

MIT License — 自由使用、修改、分享。
