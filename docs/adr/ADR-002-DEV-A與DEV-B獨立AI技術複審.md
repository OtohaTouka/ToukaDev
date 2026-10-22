# ADR-002：DEV-A 與 DEV-B 獨立 AI 技術複審

- **現況：** 多代理建議與模型證據由 ADR-003 取代；資料條件語意由 ADR-004 取代；預設模式由 ADR-034 修訂。
- **日期：** 2026-07-23
- **狀態：** 已接受；多代理建議與模型證據部分由 ADR-003 取代，資料條件語意部分由 ADR-004 取代
- **影響範圍：** `dev-workflow` 的 DEV-A、DEV-B；共同 `AGENTS.md` 基線；Commands 與框架守衛

## 問題

ToukaDev 的主要使用者可能不會寫程式，卻必須在 DEV-A 審核實作計畫、在 DEV-B 審核完成工作。
只要求人類技術審核會形成虛假把關；只讓原作者模型自我檢查，又無法有效降低單一模型盲點。

## 決策

1. DEV-A、DEV-B 改為「強制審核點」，不再限定只能由人類技術審核。
2. 預設模式為人類加一個獨立 AI reviewer；使用者在每個審核點都能改選。
3. 提供人類、AI 委託、人類加 AI、對抗式多代理四種模式。
4. 以能力相對層級路由 reviewer，不把特定模型名稱當成永久 SSOT。
5. 高風險任務主動建議、關鍵風險任務強烈建議多代理複審，但未取得人類逐次明確同意前絕不啟動。
6. 單 reviewer 必須使用獨立、唯讀上下文並禁止委派 subagent。
7. 測試、lint、guard 等確定性證據先於 AI reviewer，且不能被 AI 或人類 override 弱化。
8. DEV-B 審核完整候選 commit，包含 untracked 內容；核准快照與實際 staged commit 必須一致。
9. 跨供應商或 premium reviewer 需要獨立的資料知情同意；資料條件的查核與無保證語意改由
   ADR-004 定義。
10. 審核材料視為不可信資料；無法隔離候選規則、強制唯讀或禁止 delegation 時不得取得 AI 通過。
11. `AI_DELEGATED` 只有純 `PASS` 可依事前授權繼續，其他結論都返回人類。
12. 本次只套用 DEV-A、DEV-B；INIT-A、INIT-B、DBG-A 留待後續獨立變更。

完整規則由 `dev-workflow/references/review-protocol.md` 作為唯一正本。

## 理由

- 人類仍能決定需求、成本及不可逆動作，不必假裝能讀懂程式碼。
- 獨立 reviewer 能發現作者上下文中的錯誤假設。
- 模型名稱、供應狀況和跨工具能力會變動，能力路由比硬編碼產品名稱可靠。
- 多代理成本高，而且模型可能自行委派；明確同意與技術限制都是必要條件。
- 結構化證據與異議紀錄比模型多數決更可稽核。

## 影響

- DEV-A、DEV-B 會多一次模式選擇與風險判定。
- 預設流程增加 reviewer 的時間與額度消耗。
- 部分工具不能直接啟動其他模型，必須改用標準審核包手動交接。
- 平台若無法證明新上下文、唯讀、實際模型或禁止 delegation，不得宣稱完成獨立 AI 複審。
- Fable 等高自主模型的自我檢查不算獨立審核；外部模型的資料條件必須在執行時查核並依
  ADR-004 分級揭露。
- commit 前多一次 manifest／patch 雜湊比對，避免 DEV-B 核准後夾帶新檔或秘密。

## 參考

- [OpenAI Codex Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)
- [OpenAI Codex Code Review](https://learn.chatgpt.com/docs/code-review?surface=app)
- [Anthropic Claude Fable 5](https://www.anthropic.com/claude/fable)
