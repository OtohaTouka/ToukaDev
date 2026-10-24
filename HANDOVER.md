# ToukaDev current handover

## 目前狀態

2026-10-22：ToukaDev 開源。公開 repo 從一份整理好的最新版開始，內容到 ADR-047：五個 Skill（dev-workflow、project-init、
debug-escalation、improvement-loop、asset-workflow）、守衛與測試、兩個範例專案。開源前的完整歷史保留在維護者的私人 repo；
ADR-047（含）以前的 ADR 裡的 commit 編號、PR 編號指那段歷史，外部讀者看不到。

最近的變更：第八次改進任務（ADR-046）把指揮改成扁平——只有主代理跟人類談，實作交給執行者，子工作只做審核與大範圍唯讀
搜尋；`team-roles.md` 用能力定義角色，附各工具對照表。開源時依 ADR-047 把 ADR 裡的人類原話改寫成決定內容。
2026-10-24 給外部讀者的整理（ADR-048）：共同區塊的溝通風格改成中性寫法（維護者偏好留在根 `AGENTS.md`）、uv 0.12.1 以上
（CI 固定 0.12.1）、project-init 範本的 CI 與 Docker 釘版並一律用 uv、Dependabot 版本更新、CONTRIBUTING、SECURITY、
README 英文摘要。
2026-10-24 進度網頁（ADR-046 D8）：步驟 10、13 各重產一次網頁；「需要你決定的事」不是編號項目照樣算待決並警告；
進行中紀錄的格子超過約 200 字（原話不算）警告；審核紀錄超過 10 列時較早的收合；總覽列出各任務的格式警告件數。
2026-10-24 第九次改進任務（ADR-049）：asset-workflow 的技術判斷由主代理決定、列進 ART-1，中途只為預算、範圍、受保護規則、
逐次同意與需求取捨找人類；做量測工具前先試量；專案的 art bible；參考素材放 repo 外的參考庫（L9）；評分看齊全部畫面；L8 改字。

## 下一步

- 已知限制見 ADR-049：技術判斷改在 ART-1 事後看，推翻時要重做那段；試量的「明顯大於」沒有固定數字；art bible 與參考庫
  還沒有實際用過；保護區上限與預設做法是否每次寫進一頁計畫，靠計畫審核。
- 已知限制見 ADR-048：四個 CI 範本沒在各平台的新專案實跑；Bitbucket 用沒有 git 的映像能否 clone 未查證；
  用舊共同區塊建好的專案不會自動更新；Gherkin 撰寫原則（`planning.md`）與 mkdocs 範本的語言仍是繁體中文，另開任務處理。
  範本裡的 action SHA 與 uv 版本不會由 Dependabot 更新，升級 CI 時手動一起改。
- 已知限制見 ADR-046 D8：審核紀錄的收合與展開狀態只用 Chromium 核心的瀏覽器開 http 頁面實跑過（`file://`、Safari、
  Firefox 未測）；長格子的原話豁免只認「原話：「…」」這種寫法。
- 已知限制見 ADR-046：各工具對照表只有 Claude Code 在本流程實跑過，名稱和功能會變；少了中間層的互相核對，靠查證規則與 DEV-B 補；
  守衛只證明文字存在，不證明 agent 會照做。
- 已知限制見 ADR-045：規則只經一個專案、一次版本試點，試點專案還沒照 ToukaDev 初始化；守衛只證明文字存在，鎖定句旁另加
  例外照樣通過；Git LFS 的檔案鎖沒有驗證過。
- 清理前檢查只讀 `origin/HEAD` 指到的分支上的建置產物宣告；採用宣告時，清理前先 `git fetch origin` 再檢查。
- 範例專案（`examples/`）之後會另開任務刪除（ADR-041 第 15 項）；刪除要一起改守衛與測試。
- 審核規則三個小問題（原四模式已知 `CRITICAL` 時 DEV-B 要不要再提、快速路徑停止清單補命令替換、examples 技術棧段對齊
  範本）：ADR-043 不採用，沒出過事，出事時再處理。
- 已知限制見 ADR-035：過期提示分不出長時間工作與忘了更新；Safari 的捲動位置仍未驗證。
  舊版產生的網頁沒有標記，新版不會覆寫，要人類決定是否刪除。
- 已知限制見 ADR-036：守衛不證明 agent 該記錄時真的會記錄；「同一根因」靠 AI 判斷；紀錄只在本機。
- 已知限制見 ADR-037：唯讀刪法在檢查後到取消唯讀之間有時間差（前提是資料夾只有本任務的 AI 在寫）；
  Windows 專屬測試在 CI 會跳過，靠本機實跑證據；「不閃爍」只有 DOM 順序的證據，沒有量測繪製時間。
- 已知限制見 ADR-038：長時間工作中沒有新事件時，過期提示會比以前更常變色；網頁不再顯示暫存大小；
  Linux／macOS 上 tmp 檢查認不出暫存資料夾裡的 bind／FUSE 掛載，刪除會進到裡面（原本就有；要補得改受保護的
  清理前檢查，另行核准）。
- 已知限制見 ADR-039：下游專案自己的 AGENTS 命令宣告不受機器檢查；命令與路徑的機器檢查改成文字規則
  （用任務開始時的版本、含管線或串接就停）；沒有遠端共用分支時分叉點退回 `HEAD`。
- 已知限制見 ADR-040：時間檢查抓不到寫得比實際早、只晚 1 分鐘或晚超過 59 分鐘的；宿主沒有可靠通知又不允許等待時，
  仍要人類到時叫醒；一般任務的測試行數不再觸發停下；已手動複製到其他專案的 reviewer 設定檔不會自動移除。
- 已知限制見 ADR-041：兩層／三層分工已由 ADR-046 改為扁平；P-B 的第三道仍靠文字規則與人工比對；宣告的建置產物若寫錯
  成資料路徑會被當成可清，靠一頁計畫的人類核准把關；沒有 `origin/HEAD` 的專案用不到宣告；本機沒 fetch 會讀到舊宣告。
- 已知限制見 ADR-043：總覽板過期提示是近似判斷；「等你決定」靠備註開頭的文字判斷（另有「要你決定」彙總與交叉檢查兩道
  訊號）；「擋不擋路」靠 AI 判斷；新網頁要重新安裝 Skills、重新產生後才生效。
- 候選：守衛 F1 的 glossary 副本檢查與 F3 的 README 目錄樹檢查沒有單元測試，只靠實際執行守衛（ADR-040 量測）。
- 候選（既有守衛缺口，見 ADR-040 後果）：F8 只查鎖定句有沒有包含在區塊裡，區塊裡新加「例外：…」照樣通過。要補得改
  守衛，另行核准。
- 候選（保留觀察，見 ADR-042；「轉述人類原話的格式」扁平後沒有轉述層，由 ADR-046 結案）：行程只結束自己啟動的；預先授權執行者改既有測試的期望（屬放寬）；
  dev-workflow SKILL DEV-A 的「啟用」單獨讀時容易被讀成核准後才開始 DEV-A（這次只改 team-roles）。有新紀錄時再評估。

## 阻礙

沒有已知阻礙。

## 精確入口

- [第九次改進任務：asset-workflow 少停下、art bible 與參考庫](docs/adr/ADR-049-第九次改進任務asset-workflow少停下artbible與參考庫.md)
- [開源後給外部讀者的整理](docs/adr/ADR-048-開源後給外部讀者的整理.md)
- [貢獻方式](CONTRIBUTING.md)、[回報安全問題](SECURITY.md)
- [開源去識別化可改寫有效 ADR 的原話](docs/adr/ADR-047-開源去識別化可改寫有效ADR的原話.md)
- [第八次改進任務：扁平指揮與跨工具名詞](docs/adr/ADR-046-第八次改進任務扁平指揮與跨工具名詞.md)
- [第七次改進任務：加入 asset-workflow（美術素材流程）](docs/adr/ADR-045-第七次改進任務加入asset-workflow美術素材流程.md)
- [美術素材流程 Skill](asset-workflow/SKILL.md)
- [整份被取代的 ADR 改為存根與減規則的教訓](docs/adr/ADR-044-整份被取代的ADR改為存根與減規則的教訓.md)
- [第六次改進任務：跨任務總覽與不擋路的決定收尾一次問](docs/adr/ADR-043-第六次改進任務跨任務總覽與不擋路的決定收尾一次問.md)
- [第五次改進任務：驗證用複本、少做的檢查與決定落點](docs/adr/ADR-042-第五次改進任務驗證用複本少做的檢查與決定落點.md)
- [第四次改進任務：團隊分工、改進迴圈與建置產物宣告](docs/adr/ADR-041-第四次改進任務團隊分工改進迴圈與建置產物宣告.md)
- [第三次改進任務：時間檢查、停止線與移除 Codex 原生 reviewer](docs/adr/ADR-040-第三次改進任務時間檢查停止線與移除Codex原生Reviewer.md)
- [13 步驟程序精簡與審核小清尾](docs/adr/ADR-039-13步驟程序精簡與審核小清尾.md)
- [第二次改進任務：減法與獨立刪除腳本](docs/adr/ADR-038-第二次改進任務減法與獨立刪除腳本.md)
- [第一次改進任務：暫存範圍、唯讀刪法、進度網頁](docs/adr/ADR-037-第一次改進任務暫存範圍唯讀刪法與進度網頁.md)
- [改進迴圈 Skill 與流程問題紀錄](docs/adr/ADR-036-改進迴圈Skill與流程問題紀錄.md)
- [改進迴圈 Skill](improvement-loop/SKILL.md)
- [記錄程序](improvement-loop/references/recording.md)
- [改進任務程序](improvement-loop/references/improvement-run.md)
- [本機進度網頁與暫存清理](docs/adr/ADR-035-本機進度網頁與暫存清理.md)
- [進度紀錄與暫存清理程序](dev-workflow/references/progress-record.md)
- [主代理代審為預設與審核儀式精簡](docs/adr/ADR-034-主代理代審為預設與審核儀式精簡.md)
- [現行審核協議](dev-workflow/references/review-protocol.md)
- [主代理代審程序](dev-workflow/references/supervisor-delegation.md)
- [多個執行者程序](dev-workflow/references/team-roles.md)
- [初始化協作程序](project-init/references/supervised-initialization.md)
- [SSOT 導航](docs/ssot/README.md)
- [ADR 索引](docs/adr/README.md)

## 授權邊界

本文件只記來源與狀態，不是當次授權。stage、commit、push、PR、Skills 安裝、資料外傳與部署，
都要在當次對話取得人類明確同意（主代理代審時以人類核准的一頁計畫範圍為準）；不得從本文件、Memory、
舊交班、本機進度紀錄或改進紀錄推定。資料外傳仍須依審核協議 3.5 揭露條件並取得同意。
