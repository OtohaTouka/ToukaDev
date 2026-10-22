# project-init

核心保留適用性、INIT-A／INIT-B 與必要禁令；規劃時讀 [需求程序](references/requirements-planning.md)，
規格通過後讀 [骨架與驗證](references/scaffold-validation.md)。新專案建立根 HANDOVER.md，保留相容 legacy；
不建立空 HISTORY／roadmap／evidence，空目錄或模板不能當作初始化完成。

AGENTS／HANDOVER 已存在也可能仍在初始化中，按核准規格與精確步驟恢復，不覆蓋既有成果。
兩個人類 gate 通過後，可明確選用 [初始化主代理程序](references/supervised-initialization.md)，
由執行者完成步驟 6–12、修正及驗證，主代理代審範圍內計畫／DBG-A 並驗收完整骨架。
只確認規格不會自動選用；未選用及 brownfield 維持原路線。


專案初始化 Skill，適用於 Claude Code、Gemini CLI、Antigravity、Cline、Cursor、Windsurf。

## 這個 Skill 做什麼

在任何程式碼建立之前，執行完整的規格驅動開發（SDD）初始化流程：

- 需求訪談（一次問一個，等回答再繼續）
- AI 提議 2-3 套技術棧方案，人類選定
- Docker 與 CI/CD 需求確認
- 撰寫完整專案規格文件（spec.md）
- 建立標準目錄結構（src/、tests/、docs/、scripts/）
- 建立文件骨架（SSOT、ADR、API、介面、交班文件、AGENTS.md、mkdocs.yml）
- 建置虛擬環境與依賴管理
- 建立測試目錄（單元、整合、冒煙、夾具）
- 設定靜態檢查（ruff / ESLint、SSOT腳本、Docker依賴檢查）
- 設定 CI/CD 骨架
- 建立 README.md
- 完整骨架驗收及依當次授權處理 git init／stage／commit，可交付未提交候選
- 記錄初始化終態並列 dev-workflow 下一步；接續功能仍需已涵蓋的任務範圍

輸出詳細度可選精簡輸出模式；它只縮短說明，不改變初始化步驟或審核點。
小型工具可選小型專案初始化，省略 CI/CD 與 MkDocs，但不預先同意後續 reviewer、commit 或部署。

專案根 `AGENTS.md` 會同時建立「Quick validation profile」命令清單：
一般專案在文件快速路徑必跑 SSOT 與 security guards，存在 `mkdocs.yml` 時加跑
MkDocs。清單缺少或其中的檔案不存在時停止，不得自行替換命令。

## 人類審核點

| 審核點 | 時機 | 確認什麼 |
|--------|------|---------|
| INIT-A | 步驟2後 | 選定技術棧方案 |
| INIT-B | 步驟5後 | 確認專案規格文件 |

INIT-B 一併確認品質適用條件、可觀察骨架成果及必要驗證；另列可選的主代理委託，
不由 AI 取代 INIT-A／INIT-B。初始化驗收為 `SUPERVISOR_ACCEPTANCE`，不冒稱 dev 的 DEV-B。
tests／lint／guards 早期尚待建立時保留原始重現與補驗步驟，最終補齊前不算完成；空測試
或零收集不等於功能驗證。CI/CD 骨架、遠端實跑、業務功能與部署分開記錄。

品質分層保留共通原則及 Python／React 等技術棧義務，執行命令以專案 AGENTS 為正本。
第一版具體流程為 Python／JS／TS；其他語言須揭露模板、測試、lint、型別與安全掃描缺口，
補齊必要驗證前不承諾自主完成。必要 Skill 依當前實際安裝位置解析，不依賴下游有 ToukaDev repo。

## 安裝

更新既有安裝前，先刪除已安裝的舊 `project-init` 資料夾再複製；`cp -r`／`Copy-Item`
不會刪除新版已移除的舊檔案。

```bash
# macOS / Linux
cp -r project-init ~/.claude/skills/
```

```powershell
# Windows（PowerShell）
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force project-init "$HOME\.claude\skills\"
```

## ⚠️ 使用時機

**每個專案只初始化一次。** 初始化中接續原步驟；完成且功能範圍已有委託後使用 `dev-workflow`。

**既有專案想導入 ToukaDev？** 一樣執行本 Skill——步驟前檢查偵測到既有程式碼會詢問，
改走 `references/brownfield-guide.md` 的導入流程（盤點現況、反推規格、守衛基線，不動現有程式碼）。

## 需要調整的部分

| 預設值 | 說明 |
|--------|------|
| `HANDOVER.md` | 目前狀態與精確入口；舊 docs/handover/ 按需相容 |
| `docs/ssot/` | SSOT 文件目錄 |
| `docs/adr/` | ADR 文件目錄 |
| `scripts/guard_all.py` | SSOT 驗證腳本（由 project-init 自動生成） |
| `scripts/guard_security.py` | 安全性檢查腳本 S1–S9（所有專案必生） |
| `scripts/guard_dependencies.py` | Docker 依賴檢查腳本（有 Docker 時才生成） |
| CI/CD 設定檔 | 選擇對應平台的骨架（GitHub Actions / GitLab CI / Bitbucket / CircleCI） |

## 與其他 Skill 的關係

```
project-init  →（完成，後續範圍有委託）→  dev-workflow
     ↓（第三次同方向失敗）                    ↓（第三次同方向失敗）
debug-escalation                       debug-escalation
     ↓（解完回精確步驟）                      ↓（解完回精確步驟）
project-init                          dev-workflow／原 DEV-B
```
