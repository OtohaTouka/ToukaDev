# debug-escalation

除錯升級 Skill，可由支援讀取 Skill 的 coding agent 使用；主代理模式的調度與實跑證據另行確認。

## 這個 Skill 做什麼

當 AI 陷入除錯迴圈（重複相同動作達三次）時，自動觸發升級流程：

- 當前模型停止嘗試，撰寫完整除錯交班文件（三次失敗記錄、已排除原因、懷疑方向）
- 主代理代審（預設）時，由主代理派給新的分析上下文；其他模式提示人類切換到高階模型
- 分析角色強制執行五面向根本原因分析（錯誤訊息、模式、邏輯追蹤、環境、SSOT）
- 撰寫與前三次方向不同的修復計畫
- 依模式由人類或已受委託的主代理審核計畫，再交執行者修復（守 TDD/SOLID/SSOT）
- 解完回來源流程的精確中斷點；dev 回原 dev 步驟及 DEV-B，初始化回 project-init 原步驟

## 觸發條件

**主要條件（符合即觸發）：**

- 相同的錯誤訊息出現 3 次以上（最明確的迴圈信號）

**輔助條件（三項中符合兩項以上即觸發）：**

- 連續三次執行相同或幾乎相同的指令
- 連續三次修改相同的檔案但問題未解決
- 連續三次的解法邏輯相同，只是換了寫法

## 操作與審核點

| 審核點 | 時機 | 確認什麼 |
|--------|------|---------|
| DBG-OP（操作點） | 步驟2後 | 手動切換高階模型 |
| DBG-A（審核點） | 步驟5後 | 確認根本原因分析與修復計畫 |

上表的人類操作是其他模式的路線。主代理代審（預設）時，主代理在有效委託內負責 DBG-OP 派工與
DBG-A 代審，結論標示 `SUPERVISOR_ACCEPTANCE`；分析及修復由執行者完成。可用子代理、其他
對話、CLI 實例或等效方式，同模型的新分析上下文也可用，不需新增框架。
同一未解問題預設最多重新分析兩輪，初始委託可另定合理上限；換執行者不清零，無進展才返回人類。
完整模式邊界依已安裝 dev-workflow 的 `references/supervisor-delegation.md`，主代理代審時讀取。
必要 sibling Skill 以環境 catalog／locator 解析實際安裝根，不依賴下游專案具有 ToukaDev repo。
初始化只有兩個人類 gate 通過且主代理委託有效，才可代審範圍內 DBG-A；實質技術棧、規格
或權限變更仍返回原核准 gate。各模式原有邊界保持，初始化驗收不當成 dev 的 DEV-B。

## 安裝

```bash
# macOS / Linux（於框架根目錄執行）
cp -r debug-escalation ~/.claude/skills/
cp glossary.md ~/.claude/skills/   # 術語表（SKILL.md 內連結需要）
```

```powershell
# Windows（PowerShell），於框架根目錄執行
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse -Force debug-escalation "$HOME\.claude\skills\"
Copy-Item glossary.md "$HOME\.claude\skills\"   # 術語表（SKILL.md 內連結需要）
```

## ⚠️ 使用時機

**每次除錯危機只使用一次。** 解完立即回來源流程的精確步驟，不在此流程內循環。
初始化步驟 6／8 尚無 tests、lint、guards 時，保留最小重現、原始 FAIL 與補驗責任／步驟，
標尚待建立／驗證，不標 PASS；已適用且已建立者仍必跑，最終初始化前收斂全部待驗項。
依核准技術棧不適用者列理由，不能改寫既有必跑義務。Git 與後續功能不由事故解除推定。

## 與其他 Skill 的關係

```
dev-workflow／project-init →（第三次同方向失敗）→ debug-escalation
          ↑（來源流程與原精確步驟）                    ↓（分析、DBG-A、修復）
          └─────────────────────────────────────────┘
```

## 事故與接手入口

新事故讀 [事故交棒程序](references/incident-handoff.md)，以唯一 incident-id 保存事故；
有可用文件位置時建立 docs/evidence/<incident-id>.md，早期則用已授權且可用位置，不提前建骨架。
同日事故不可覆寫，原 FAIL 保留。已有根 HANDOVER.md 只放 current 摘要與精確連結。
接手讀 [根因恢復程序](references/root-cause-recovery.md)，只沿指定事故，完成五維分析與 DBG-A 後才修復。
正常 TDD RED 或一般問題不自動觸發升級；歷史 PASS 不是當次修復授權。
