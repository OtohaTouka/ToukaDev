# line-bot current handover

## 目前狀態

2026-09-06：LINE webhook 範例；介面及常數正本如下。
本次只切換共同文件規則、current 與導航，不修改業務程式、依賴或部署。
2026-08-09 Ruff debt 紀錄是歷史；當時測試數與「尚未 commit」不代表目前工作樹或本次驗證。

## 下一步

有新任務時直達對應介面與 SSOT；若實作，依 dev-workflow 形成當次計畫與必要驗證。

## 阻礙

本批沒有已知業務 blocker；沒有重跑範例業務測試或外部服務 smoke 的證據。

## 精確入口

- [專案規則](AGENTS.md)
- [執行方式](README.md)
- [介面](docs/interface/webhook.md)
- [常數](docs/ssot/constants.md)
- [SSOT 導航](docs/ssot/README.md)
- [Ruff debt 歷史](docs/handover/2026-08-09-ruff-format-debt.md)

## 授權邊界

本檔與歷史不是當次授權；新功能、修復、DEV-A／DEV-B 與 commit 依當次對話決定。
