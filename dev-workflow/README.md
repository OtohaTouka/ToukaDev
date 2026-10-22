# dev-workflow

核心入口保留硬規則與兩個 gate；準備計畫讀 [planning](references/planning.md)，
開始修改／驗證讀 [implementation](references/implementation.md)，更新狀態／交付讀 [delivery](references/delivery.md)。
唯讀問答不啟動實作循環；HUMAN_ONLY 不載入 reviewer 操作手冊。

先確定審核模式，再選調度方式；預設的主代理代審 `SUPERVISOR_DELEGATED` 讀
[主代理代審程序](references/supervisor-delegation.md)，人類改選原四模式時不預載。


標準人機協作開發流程 Skill，適用於 Codex desktop／CLI、Claude Code、Gemini CLI、
Antigravity、Cline、Cursor、Windsurf。

## 安裝

更新既有安裝前，先刪除已安裝的舊 `dev-workflow` 資料夾再複製；`cp -r`／`Copy-Item`
不會刪除新版已移除的舊檔案。

```bash
# 複製到 Claude Code 的 skills 目錄（於框架根目錄執行）
cp -r dev-workflow ~/.claude/skills/
cp glossary.md ~/.claude/skills/   # 術語表（SKILL.md 內連結需要）

# 或使用 npx skills（若已安裝）
npx skills add <your-repo>/dev-workflow
```

```powershell
# Windows（PowerShell），於框架根目錄執行
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force dev-workflow "$HOME\.claude\skills\"
Copy-Item glossary.md "$HOME\.claude\skills\"   # 術語表（SKILL.md 內連結需要）
```

## 這個 Skill 做什麼

強制執行 13 步驟：讀 current 與必要正本（1-2）→ 實作計畫與 DEV-A（3-4）→ TDD 紅綠重構（5-8）→
靜態檢查與守衛（9）→ 文件與 current（10）→ 冒煙測試（11）→ DEV-B 與提交（12-13）。
步驟與硬規則見 [SKILL.md](SKILL.md)，各階段細節見上方三份程序。

- **審核**：DEV-A／DEV-B 的五種模式、風險分級、reviewer qualification、多代理明確同意與結論狀態，
  以 `references/review-protocol.md` 為唯一正本。預設主代理代審，人類可隨時改選；
  `HIGH` 只有命中具體觸發條件才建議對抗式複審，`CRITICAL` 強烈建議一次，都不會自動啟動多代理。
- **主代理代審**：一頁白話計畫經非作者的 reviewer 審、人類核准，即為本任務的委託；寫的人和審的人
  不能是同一個。程序見 [主代理代審程序](references/supervisor-delegation.md)。
- **進度與暫存**：進度紀錄、本機網頁與暫存清理以 [進度紀錄程序](references/progress-record.md) 為正本。
- **多個執行者**：派兩個以上執行者並行或一次核准多段計畫時，角色、各工具的名詞對照與派工見 [多個執行者程序](references/team-roles.md)。
- **精簡輸出模式**只縮短說明文字，不省略步驟、審核點或授權核對；`模式：精簡` machine token 維持相容。
- **文件快速路徑**（純文件／typo）依最近作用域 `AGENTS.md` 的「Quick validation profile」執行，
  沒有宣告就改回完整步驟3；細節見 SKILL.md。
- 全新專案的初始化協作見 project-init；Debug 一律回事故來源流程的精確中斷點。
- 「可讀取 Skill」不等於「可自動建立獨立 reviewer」；reviewer 資格、實際模型與外部傳輸同意依審核協議。
