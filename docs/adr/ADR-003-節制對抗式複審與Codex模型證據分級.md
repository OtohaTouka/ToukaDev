# ADR-003：節制對抗式複審與 Codex 模型證據分級

- **現況：** 模型證據三級由 ADR-033 簡化（ADR-033 寫明「部分取代」）。
- **日期：** 2026-08-09
- **狀態：** 已接受；資料條件語意由 ADR-004、輸出相容性由 ADR-005、授權與候選綁定由 ADR-006 補充
- **影響範圍：** DEV-A／DEV-B 審核建議、Codex desktop／CLI 適配、跨 session 治理、框架守衛

## 問題

ADR-002 建立了獨立 AI reviewer 與對抗式多代理複審，但實際使用出現三個問題：

1. `HIGH` 風險會固定觸發多代理建議，導致即使單 reviewer 與確定性測試已足夠，AI 仍反覆
   推薦高額度複審；
2. Codex CLI 可以固定 requested model、隔離輸入並停用 delegation，卻沒有可用的供應端
   actual-model 正向遙測；把「未觀察到 fallback」當成證明不誠實，完全拒用又浪費可用證據；
3. Codex 專案沒有可依賴的跨 session Memory。使用者必須重複說明非互動 CLI reviewer 的
   方法，但若直接把舊同意存進 Memory，又會破壞逐次授權。

## 決策

1. 保留 `STANDARD`／`HIGH`／`CRITICAL` 風險分級，但將「風險分級」與「是否建議多代理」
   分離。
2. `HIGH` 只有命中審核協議列出的具體條件才建議 `ADVERSARIAL`；`CRITICAL` 強烈建議一次。
   使用者拒絕後，除非範圍或風險實質改變，不得重複施壓。
3. 檔案數、泛稱模型盲點、額度可能足夠、模型遙測不足，均不得單獨構成多代理建議理由。
4. 模型證據分為 `ATTESTED`、`REQUESTED_ONLY`、`UNKNOWN`。`REQUESTED_ONLY` 明確保留
   actual model 與 fallback 的不確定性，reviewer 結論最高為 `PASS_WITH_NOTES`，因此不能
   滿足 `AI_DELEGATED` 所需的純 `PASS`。
5. 新增版本化 `dev-workflow/references/codex-adapter.md`，保存 Codex 的隔離、證據、預檢與
   跨 session 方法；`review-protocol.md` 仍是模式與通過條件 SSOT。
6. `AGENTS.md`、交班文件與平台 Memory 只保存長期規則、偏好、能力限制與歷史。當次模式、
   資料傳輸、多代理、開始實作與 commit 授權一律重新取得。
7. 新增 F9 守衛，防止 adapter、模型證據分級、使用端引用或授權邊界在後續修改中漂移。

## 理由

- 對抗式複審應針對單 reviewer 與確定性證據無法有效降低的具體風險，而不是風險標籤的
  自動附加動作。
- `REQUESTED_ONLY` 把可驗證事實與未知部分拆開：既不虛構供應端遙測，也不丟棄隔離良好的
  技術審核意見。
- 版本化 repo 文件能被每個新 session 讀取，比依賴特定產品的隱性 Memory 更可攜、可審計。
- 將「背景記錄」與「逐次授權」分離，可以減少重複解釋，同時避免永久同意。

## 影響

- 一般 `HIGH` 任務不再固定收到多代理推薦；使用者仍可隨時主動選擇 `ADVERSARIAL`。
- Codex CLI 在只能證明 requested model 時，可以提供標示限制的獨立技術意見，但不能單獨
  自動授權實作或 commit。
- 每個 Codex session 會從 repo adapter 恢復平台方法；容易變動的 CLI flags、版本、模型供應、
  留存與區域條件仍須在啟動 reviewer 前重新預檢。
- 第二批依本 ADR 新增只允許一個 reviewer 的 `codex_review_runner.py`、封閉結果 Schema、
  sealed authorization manifest 與 fake-CLI 測試；它不推定授權，也不把 requested model
  冒充 actual-model attestation。
- 本 ADR 尚不改變對抗式 reviewer 的數量與編排；受控 fan-out 仍屬後續批次。
- 已安裝在工具全域目錄的 Skill 副本不會由 repo 修改自動覆寫，仍需依安裝流程同步。

## 實作狀態

- 第一批：治理規則、模型證據分級、跨 session 邊界與 F9 adapter 守衛已完成。
- 第二批：單一 runner、結果 Schema、輸入／授權／隔離／事件證據與 F9 artifact 守衛已完成；
  DEV-B 預檢發現原本把「供應商無固定承諾」與「未查證」混為一談，現依 ADR-004 將 manifest
  升級為 schema version 2；第一次經授權的真實 reviewer 因結果 Schema 不相容而失格，現依
  ADR-005 加入啟動前 Schema 相容性預檢與精確 JSONL 事件分類，修復後尚未重新外傳。
- 第三批：多 reviewer 數量上限、consent record 與一次 fan-out 尚未實作。

## 取代與保留

本 ADR 取代 ADR-002 中「所有 `HIGH` 都主動建議多代理」與「缺少 actual-model 正向證據一律
不能產生任何可計入意見」的部分；其餘關於預設 `HUMAN_AI`、逐次同意、唯讀隔離、候選
commit 綁定、不可信輸入與確定性守衛的決策繼續有效。

## 參考

- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode.md)
- [Codex authentication](https://learn.chatgpt.com/docs/auth.md)
- [Codex cyber safety and rerouting](https://learn.chatgpt.com/docs/cyber-safety.md)
- [ADR-002](ADR-002-DEV-A與DEV-B獨立AI技術複審.md)
- [ADR-004](ADR-004-區分資料條件無保證與未查證.md)
- [ADR-005](ADR-005-Codex審核輸出Schema預檢與事件分類.md)
- [ADR-006](ADR-006-Codex審核授權與候選快照綁定.md)
