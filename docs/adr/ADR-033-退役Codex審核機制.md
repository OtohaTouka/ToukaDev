# ADR-033：退役 Codex 審核機制

- 日期：2026-10-09
- 狀態：已接受（DEV-A：HUMAN_AI，人類核准）
- 取代：ADR-005～010、ADR-012～014、ADR-016～018、ADR-020～028；部分取代 ADR-003（模型證據三級）、
  ADR-004（資料條件三級）

## 問題

2026-08-09（`c53914b`）時 ToukaDev 約 1.2 萬行，之後一個多月成長到約 8.7 萬行，其中約 6 萬行是
四套 Codex 專屬的審核機制：

- **A. 嚴格單 reviewer runner**：PF-1 預檢、consent request 與精確 receipt、manifest v5、production runner、
  秘密掃描、`codex-adapter.md`。
- **B. 對抗式多代理**：TEST_ONLY 的契約、consent、claim、fan-out 與彙整程式，從未上線。
- **C. Codex 原生 profile**：`codex-native-single.md`、`codex-native-adversarial.md` 與守衛 F12。
- **D. reviewer 部署生命週期**：把 12 行的 reviewer 設定檔部署到各專案的交易、當機復原、控制器與
  AST 守衛 F13～F16。

這些機制是因為當時 Codex 原生 subagent 不成熟、想自建替代品而寫出來的。ADR-031 的主代理代審上線後，
主代理已能自行管理 subagent，這些機制不再需要。實際使用也很少：A 只做過一次真實試跑，B 從未上線；
D 的紀錄說部署過三個專案，但在 GitHub 與本機都找不到部署結果。

## 決策

1. **A 整套刪除**：`dev-workflow/scripts/`、相關 JSON schema、`codex-adapter.md`、介面文件與測試。
2. **B、C、D 只留寬鬆文字**：程式、schema、介面文件、測試與守衛 F9、F12～F16 刪除；用法與限制合併成
   [`dev-workflow/references/codex-notes.md`](../../dev-workflow/references/codex-notes.md)，作為審核協議唯一明列的
   平台 adapter。reviewer 設定檔與範本保留，改由人類需要時手動複製，兩份副本由守衛 F1 保持一致。
3. **兩條 Codex 時期的一般規則簡化**（人類核准）：
   - 模型證據三級改為：原四模式的 AI reviewer 無法確認實際模型時必須說明，結論最高 `PASS_WITH_NOTES`，
     不能滿足 `AI_DELEGATED` 的自動繼續或 commit。主代理代審不受這條規則限制。
   - 資料條件三級與 SHA-256 綁定的同意改為：送到其他 AI 服務前說明送什麼、送去哪、對方有無保證，
     取得人類明確同意；無法說明對方條件時不得傳送。
4. **共同基線兩行改寫**（人類核准）：Codex 原生 reviewer 只算參考意見；Codex 原生多代理在說明風險並取得
   同意後，可把規則檔候選當不可信證據審查。四份 AGENTS.md 同步。
5. **守衛**：保留 F1～F8、F10、F11、F17。原 F9 的跨 session 授權規則併入 F8；F8 新增選單預設（選項 3
   與「若未指定，採用 3」）的檢查。F9、F12～F16 的編號保留不重用。
6. **歷史文件**：根目錄的 `docs/handover/`、`docs/evidence/`、`docs/proposal/` 刪除，內容保留在 git 歷史
   （刪除前最後一版為 `main` 的 `aa195a5`）。既有 ADR 內文不改寫，其中指向已刪檔案的連結以 git 歷史為準。

## 不變的部分

13 個步驟、INIT-A／INIT-B／DEV-A／DEV-B／DBG-OP／DBG-A 審核點、5 種審核模式與預設 `HUMAN_AI`、
DEV-B 的完整候選快照、主代理代審、文件快速路徑與 validation profile、文件路由，以及下游專案範本
（除共同基線兩行、glossary 同步與範本 reviewer toml 描述修改（2026-10-10 更正）外），全部維持原樣。這些流程來自實際事故，不屬於本次退役範圍。

## 影響

- 已安裝的 Skills 要先刪除舊資料夾再重新複製，否則舊的 scripts 與 references 會殘留。
- 曾用過舊部署工具的專案或電腦，可依 `codex-notes.md` 手動清理留下的 state、lock 與 transaction 檔。
- 守衛只證明有限的文字契約與連結；不證明 agent 的實際行為。
