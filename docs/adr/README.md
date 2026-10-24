# ToukaDev 架構決策記錄

本目錄記錄 ToukaDev 框架層的重要技術與治理決策。ADR 編號只往後追加，不重編、不重用。

ADR-047（含）以前的 ADR 裡的 commit 編號和 PR 編號指開源前的私人歷史 repo，外部讀者看不到；整份被取代的 ADR 存根裡的 `git show` 在公開 repo 會失敗。

## 決策清單

| 編號 | 標題 | 狀態 |
|---|---|---|
| [ADR-001](ADR-001-統一AGENTS檔名與共同規則基線.md) | 統一 AGENTS.md 檔名與共同規則基線 | 已接受 |
| [ADR-002](ADR-002-DEV-A與DEV-B獨立AI技術複審.md) | DEV-A 與 DEV-B 獨立 AI 技術複審 | 部分由 ADR-003、ADR-004 取代；預設模式由 ADR-034 修訂 |
| [ADR-003](ADR-003-節制對抗式複審與Codex模型證據分級.md) | 節制對抗式複審與 Codex 模型證據分級 | 已接受；模型證據三級由 ADR-033 簡化 |
| [ADR-004](ADR-004-區分資料條件無保證與未查證.md) | 區分資料條件無保證與未查證 | 已由 ADR-033 簡化 |
| [ADR-005](ADR-005-Codex審核輸出Schema預檢與事件分類.md) | Codex 審核輸出 Schema 預檢與事件分類 | 已歸檔（由 ADR-033 取代） |
| [ADR-006](ADR-006-Codex審核授權與候選快照綁定.md) | Codex 審核授權與候選快照綁定 | 已歸檔（由 ADR-033 取代） |
| [ADR-007](ADR-007-Codex審核執行身分與TOCTOU封閉.md) | Codex 審核執行身分與 TOCTOU 封閉 | 已歸檔（由 ADR-033 取代） |
| [ADR-008](ADR-008-延長Codex審核授權最大生命週期至四小時.md) | 延長 Codex 審核授權最大生命週期至四小時 | 已歸檔（由 ADR-033 取代） |
| [ADR-009](ADR-009-Codex審核包Python參照秘密掃描邊界.md) | Codex 審核包 Python 參照秘密掃描邊界 | 已歸檔（由 ADR-033 取代） |
| [ADR-010](ADR-010-Codex預檢純決策與非授權診斷邊界.md) | Codex 預檢純決策與非授權診斷邊界 | 已歸檔（由 ADR-033 取代） |
| [ADR-011](ADR-011-以AGENTS宣告文件快速路徑ValidationProfile.md) | 以 AGENTS.md 宣告文件快速路徑 Validation Profile | 已歸檔（framework runtime 部分由 ADR-015 取代；其餘由 ADR-039 取代） |
| [ADR-012](ADR-012-Codex單Reviewer兩階段ConsentRequest與精確Receipt.md) | Codex 單 reviewer 兩階段 Consent Request 與精確 Receipt | 已歸檔（由 ADR-033 取代） |
| [ADR-013](ADR-013-CodexProductionRunner共用PF1Policy.md) | Codex Production Runner 共用 PF-1 Policy | 已歸檔（由 ADR-033 取代） |
| [ADR-014](ADR-014-Codex對抗式ParentChild契約與純狀態機.md) | Codex 對抗式 Parent／Child 契約與純狀態機 | 已歸檔（由 ADR-033 取代） |
| [ADR-015](ADR-015-ToukaDev根目錄uv工具鏈與可重現驗證環境.md) | ToukaDev 根目錄 uv 工具鏈與可重現驗證環境 | 已接受；D4（uv 版本）由 ADR-048 修訂 |
| [ADR-016](ADR-016-Codex對抗式ParentConsent與單次Claim.md) | Codex 對抗式 Parent Consent 與單次 Claim | 已歸檔（由 ADR-033 取代） |
| [ADR-017](ADR-017-Codex對抗式TestOnlyFanout與結算政策.md) | Codex 對抗式 TEST_ONLY Fan-out 與結算政策 | 已歸檔（由 ADR-033 取代） |
| [ADR-018](ADR-018-Codex對抗式TestOnlyAggregation與少數異議保存.md) | Codex 對抗式 TEST_ONLY Aggregation 與少數異議保存 | 已歸檔（由 ADR-033 取代） |
| [ADR-019](ADR-019-新手審核漸進揭露與使用者可見名詞契約.md) | 新手審核漸進揭露與使用者可見名詞契約 | 已接受；技術收據由 ADR-034 移除 |
| [ADR-020](ADR-020-Codex原生Subagent對抗式複審Profile.md) | Codex 原生 Subagent 對抗式複審 Profile | 已歸檔（由 ADR-033 取代） |
| [ADR-021](ADR-021-Codex原生Reviewer逐Child唯讀Sandbox.md) | Codex 原生 Reviewer 逐 Child 唯讀 Sandbox | 已歸檔（由 ADR-033 取代） |
| [ADR-022](ADR-022-Codex原生對抗式複審務實信任邊界.md) | Codex 原生對抗式複審務實信任邊界 | 已歸檔（由 ADR-033 取代） |
| [ADR-023](ADR-023-F12結構化Markdown政策分析器.md) | F12 結構化 Markdown 政策分析器 | 已歸檔（由 ADR-033 取代） |
| [ADR-024](ADR-024-Codex專案Reviewer可攜式生命週期.md) | Codex 專案 Reviewer 可攜式生命週期 | 已歸檔（由 ADR-033 取代） |
| [ADR-025](ADR-025-Codex單專案Reviewer兩階段安全部署.md) | Codex 單專案 Reviewer 兩階段安全部署 | 已歸檔（由 ADR-033 取代） |
| [ADR-026](ADR-026-Codex登記專案交易與崩潰復原.md) | Codex 登記專案交易與崩潰復原 | 已歸檔（由 ADR-033 取代） |
| [ADR-027](ADR-027-Codex專案Reviewer更新與移除控制器.md) | Codex 專案 Reviewer 更新與移除控制器 | 已歸檔（由 ADR-033 取代） |
| [ADR-028](ADR-028-Codex原生單Reviewer有限HUMAN_AIProfile.md) | Codex 原生單 Reviewer 有限 HUMAN_AI Profile | 已歸檔（由 ADR-033 取代） |
| [ADR-029](ADR-029-文件路由契約與交班相容基礎.md) | 文件路由契約與交班相容基礎 | 已接受；文件路由契約與 helper 由 ADR-034 取代 |
| [ADR-030](ADR-030-文件路由原子切換與按需程序載入.md) | 文件路由原子切換與按需程序載入 | 已接受；文件路由契約由 ADR-034 取代，F17 由 ADR-034 精簡 |
| [ADR-031](ADR-031-主代理代審與任務範圍自主協作.md) | 主代理代審與任務範圍自主協作 | 已接受；預設模式與寫審分工由 ADR-034 修訂 |
| [ADR-032](ADR-032-初始化主代理協作與品質適用性分層.md) | 初始化主代理協作與品質適用性分層 | source 測試通過；行為試行待同意，待主代理 DEV-B；品質分層鎖定句的措辭由 ADR-039 修訂 |
| [ADR-033](ADR-033-退役Codex審核機制.md) | 退役 Codex 審核機制 | 已接受；「不變的部分」中的預設審核模式、完整候選快照與文件路由由 ADR-034 修訂；D2 保留的原生 reviewer 說明與設定檔、D4 共同基線兩行由 ADR-040 移除；D6（既有 ADR 內文不改寫）由 ADR-044 修訂，整份被取代的 ADR 可以換成存根；ADR-047 再加開源去識別化的例外 |
| [ADR-034](ADR-034-主代理代審為預設與審核儀式精簡.md) | 主代理代審為預設與審核儀式精簡 | 已接受；D3（工作資料夾位置）與 D8（進度紀錄欄位與格式）由 ADR-035 修訂；D1（一頁計畫內容）由 ADR-038 修訂；D4（暫時 index 刪掉後的審法）、D9（`CRITICAL` 提出時機、第 9 條措辭）、後果中的已知不一致與「不變的部分」中的 validation profile 由 ADR-039 修訂 |
| [ADR-035](ADR-035-本機進度網頁與暫存清理.md) | 本機進度網頁與暫存清理 | 已接受；D2（自動重新整理與主題）與 D4 第 1 種項目的刪法由 ADR-037 修訂；D1（更新時間行）、D2（網頁功能）與 D4（不寫刪除程式）由 ADR-038 修訂；D4 的收尾做法（清理清單列好就可以結束）由 ADR-043 修訂 |
| [ADR-036](ADR-036-改進迴圈Skill與流程問題紀錄.md) | 改進迴圈 Skill 與流程問題紀錄 | 已接受；D3（改進任務的寫法）由 ADR-038 修訂；D2（提醒）、D3（啟動）由 ADR-041 修訂；D3 另因 ADR-041 的三道防改鬆檢查修訂（受保護規則的處理方式）；D3（是否重新安裝 Skills）由 ADR-043 修訂 |
| [ADR-037](ADR-037-第一次改進任務暫存範圍唯讀刪法與進度網頁.md) | 第一次改進任務：暫存範圍、唯讀刪法、進度網頁 | 已接受；D2（刪除程式的位置）由 ADR-038 修訂；D3（不改清理前檢查）由 ADR-041 推翻，改認預設分支宣告的建置產物 |
| [ADR-038](ADR-038-第二次改進任務減法與獨立刪除腳本.md) | 第二次改進任務：減法與獨立刪除腳本 | 已接受；D1（細部格式警告）由 ADR-040 部分推翻，加回審核時間檢查 |
| [ADR-039](ADR-039-13步驟程序精簡與審核小清尾.md) | 13 步驟程序精簡與審核小清尾 | 已接受 |
| [ADR-040](ADR-040-第三次改進任務時間檢查停止線與移除Codex原生Reviewer.md) | 第三次改進任務：時間檢查、停止線與移除 Codex 原生 reviewer | 已接受；D2（幾件要決定的事合成一則）由 ADR-041 修訂 |
| [ADR-041](ADR-041-第四次改進任務團隊分工改進迴圈與建置產物宣告.md) | 第四次改進任務：團隊分工、改進迴圈與建置產物宣告 | 已接受；D12（reviewer 的匯出複本）由 ADR-042 修訂；D1 決定權表的重新安裝 Skills 由 ADR-043 修訂；D1 兩層／三層分工由 ADR-046 改為扁平 |
| [ADR-042](ADR-042-第五次改進任務驗證用複本少做的檢查與決定落點.md) | 第五次改進任務：驗證用複本、少做的檢查與決定落點 | 已接受；D2 的 `--no-index` 寫法由 ADR-043 補完整；D4（等你決定的保留）、D5（交接板改稱總覽板）由 ADR-043 修訂 |
| [ADR-043](ADR-043-第六次改進任務跨任務總覽與不擋路的決定收尾一次問.md) | 第六次改進任務：跨任務總覽與不擋路的決定收尾一次問 | 已接受 |
| [ADR-044](ADR-044-整份被取代的ADR改為存根與減規則的教訓.md) | 整份被取代的 ADR 改為存根與減規則的教訓 | 已接受；D1 由 ADR-047 加開源去識別化的例外 |
| [ADR-045](ADR-045-第七次改進任務加入asset-workflow美術素材流程.md) | 第七次改進任務：加入 asset-workflow（美術素材流程） | 已接受；D5（L8）由 ADR-049 改字；D2、D3 的基準存放由 ADR-049 改成參考庫 |
| [ADR-046](ADR-046-第八次改進任務扁平指揮與跨工具名詞.md) | 第八次改進任務：扁平指揮與跨工具名詞 | 已接受 |
| [ADR-047](ADR-047-開源去識別化可改寫有效ADR的原話.md) | 開源去識別化可改寫有效 ADR 的原話 | 已接受 |
| [ADR-048](ADR-048-開源後給外部讀者的整理.md) | 開源後給外部讀者的整理：共同區塊中性寫法、uv 版本下限與範本釘版 | 已接受 |
| [ADR-049](ADR-049-第九次改進任務asset-workflow少停下artbible與參考庫.md) | 第九次改進任務：asset-workflow 少停下、art bible 與參考庫 | 已接受 |
