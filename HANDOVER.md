# ToukaDev current handover

## 目前狀態

2026-10-22：ToukaDev 開源。公開 repo 從一份整理好的最新版開始，內容到 ADR-047：五個 Skill（dev-workflow、project-init、
debug-escalation、improvement-loop、asset-workflow）、守衛與測試、兩個範例專案。開源前的完整歷史保留在維護者的私人 repo；
ADR-047（含）以前的 ADR 裡的 commit 編號、PR 編號指那段歷史，外部讀者看不到。

最近的變更（細節與已知限制在各 ADR）：

- 2026-11-08（ADR-051）：第十一次改進任務：進度紀錄比對 git 與 GitHub（`sync_progress.py`，主代理可補合併後的固定欄位）、「已移出」狀態、可能可以標已結束的提示、叫醒要實測過、外部原因的紅燈同樣會擋、攻擊型紅燈測試與測試共用狀態。
- 2026-11-04（ADR-050）：第十次改進任務：交班整理、審查不收斂、說法要實測、機械工作可交低能力模型、紅燈測試的匯入副作用、外部審查上限、美術流程的核可紀錄與狀態。
- 2026-10-24（ADR-049）：第九次改進任務：asset-workflow 少停下、art bible、參考庫。
- 2026-10-24（ADR-048）：給外部讀者的整理：中性的溝通風格、CI 與 Docker 釘版、Dependabot 開到 dev、CONTRIBUTING、SECURITY。
- 2026-10-24（ADR-046 D8）：進度網頁的格式警告與審核紀錄收合。
- 2026-10-22（ADR-046）：指揮改成扁平；`team-roles.md` 用能力定義角色。

## 下一步

各項開頭是加入日期。超過 `AGENTS.md` 定的天數還沒動的搬到[候選清單](docs/candidates.md)或寫明原因。

- 2026-11-04：文件分流通用化：`improvement-run.md` 的減法也量專案常駐文件、規則分流寫進 `project-init` 範本，等實際跑過幾個任務再做。
- 2026-10-24：setup-uv 10.3.0、ruff 0.17.1 的升級沒做（Dependabot 開到 main 的那兩個 PR 不合併）；Dependabot 可能不再提這兩個版本，
  之後提出更新版時照 ADR-048 D3（沿用 ADR-015 的升級規則）審。
- 2026-10-24：Gherkin 撰寫原則（`planning.md`）與 mkdocs 範本的語言仍是繁體中文，另開任務處理。
- 2026-10-24：範本裡的 action SHA 與 uv 版本不會由 Dependabot 更新，升級 CI 時手動一起改。
- 2026-10-13：範例專案（`examples/`）之後會另開任務刪除（ADR-041 第 15 項）；刪除要一起改守衛與測試。
- 2026-10-13：清理前檢查只讀 `origin/HEAD` 指到的分支上的建置產物宣告；採用宣告時，清理前先 `git fetch origin` 再檢查。

各 ADR 的已知限制不再抄到這裡；要查某段規則的限制時看對應那份 ADR。

## 阻礙

沒有已知阻礙。

## 精確入口

- [ADR 索引](docs/adr/README.md)、[SSOT 導航](docs/ssot/README.md)、[候選清單](docs/candidates.md)
- [貢獻方式](CONTRIBUTING.md)、[回報安全問題](SECURITY.md)
- [現行審核協議](dev-workflow/references/review-protocol.md)、[主代理代審程序](dev-workflow/references/supervisor-delegation.md)、
  [多個執行者程序](dev-workflow/references/team-roles.md)
- [進度紀錄與暫存清理程序](dev-workflow/references/progress-record.md)
- [改進迴圈 Skill](improvement-loop/SKILL.md)、[記錄程序](improvement-loop/references/recording.md)、
  [改進任務程序](improvement-loop/references/improvement-run.md)
- [美術素材流程 Skill](asset-workflow/SKILL.md)
- [初始化協作程序](project-init/references/supervised-initialization.md)

## 授權邊界

本文件只記來源與狀態，不是當次授權。stage、commit、push、PR、Skills 安裝、資料外傳與部署，
都要在當次對話取得人類明確同意（主代理代審時以人類核准的一頁計畫範圍為準）；不得從本文件、Memory、
舊交班、本機進度紀錄或改進紀錄推定。資料外傳仍須依審核協議 3.5 揭露條件並取得同意。
