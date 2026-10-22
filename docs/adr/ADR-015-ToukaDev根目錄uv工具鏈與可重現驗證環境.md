# ADR-015：ToukaDev 根目錄 uv 工具鏈與可重現驗證環境

- **日期：** 2026-08-18
- **狀態：** 已接受
- **影響範圍：** framework root Python、pytest、Ruff、F10 quick profile、CI、開發文件

## 問題

ToukaDev framework root 原本沒有 `pyproject.toml`、`uv.lock`、`.python-version` 或 `.venv`。
`AGENTS.md` 與 CI 直接執行裸 `python`，因此本機可能命中 WindowsApps shim、任意 host Python 或
沒有 pytest 的 uv managed runtime。兩個 examples 雖各有自己的 uv project，但其依賴與虛擬環境
只服務各自子專案，不能成為 framework root 的測試 SSOT。

這個缺口曾造成三次相同 `No module named pytest`，測試未進入 collection，不能形成有效 TDD
RED。預設 uv cache 在當時 execution identity 下也有 ACL 拒絕，進一步證明 root 驗證不能依賴
使用者層 cache 或未宣告的全域工具。

## 決策

1. framework root 建立 non-package uv project。`pyproject.toml` 是 Python 相容範圍、uv required
   version、dev dependency、pytest 與 Ruff 設定的正本；`uv.lock` 必須納入版本控制。
2. `.python-version` 固定 Python 3.12 minor series，與 framework CI 基線一致；`requires-python`
   拒絕 3.12 以外的 runtime。patch release 可由 uv 在該 minor series 內更新，實際版本必須留在
   驗證證據中。
3. root 不是可發布套件，固定 `tool.uv.package=false`。runtime dependencies 為空；dev group 精確
   鎖定 pytest 與 Ruff，不因 project-init 範本含有其他工具就擴張 root 依賴。
4. uv required version 固定為 0.12.1。CI 的 setup-uv action 使用 immutable commit SHA，並由
   `pyproject.toml` 取得 uv 版本；checkout action 同樣固定 immutable commit SHA，且不持久化
   credentials。
5. `.venv/` 與 `.uv-cache/` 是本機產物並由 Git 忽略。uv cache 固定在 `.uv-cache`，與 `.venv`
   位於相同 filesystem；pytest cache 固定在 `.uv-cache/pytest`，不依賴既有 `.pytest_cache` ACL。
6. pytest 設定將 repository root 放入 `pythonpath`，讓既有測試以 `from scripts import ...` 收集；
   strict config 與 strict markers 保持 fail closed。
7. framework quick profile 改為 argv-only 的
   `uv run --locked python scripts/guard_framework.py`。ADR-011 第 6 點的 framework 裸 `python`
   runtime 決策由本 ADR 取代；project-init 範本與 examples 的 profile 不變。
8. CI 必須依序執行 `uv sync --locked`、完整 pytest、Ruff undefined-name 基線與 framework guard。
   所有 `uv run` 都帶 `--locked`，禁止驗證階段隱式更新 lock。
9. host uv 的安裝與更新來源不屬 repo SSOT。開發者可以用原套件管理器安裝 required version，
   但不得讓 host Python、全域 pytest／Ruff 或 example `.venv` 取代 root project environment。

## 理由

- root-level project metadata 讓本機、CI 與後續 debug 使用相同 dependency graph 與命令入口。
- non-package project 避免為了工具環境虛構 build backend 或安裝 framework repo 本身。
- project-local cache 同時避開使用者層 ACL 問題並符合 uv 對 cache／environment 同 filesystem 的
  效能建議。
- exact dev dependency 與 locked execution 讓工具升級成為可審核變更，不會在測試時漂移。
- 保留 Python minor pin 可取得同系列安全 patch；驗證仍記錄實際 patch，避免誤稱 byte-identical
  interpreter。

## 未採用方案

### 重用 example 的 `.venv`

拒絕。example 依賴是各子專案 SSOT，從 root 借用會造成作用域反轉與無法重現的隱性依賴。

### 繼續使用 host Python 與全域 pytest

拒絕。host PATH 已包含不可存取的 WindowsApps shim，且全域工具版本不受 repo lock 約束。

### 使用預設使用者層 uv／pytest cache

拒絕。既有 execution identity 已出現 ACL 拒絕；workspace cache 能以相對路徑表達且不需硬編磁碟
代號。

### 把 project-init 的全部 dev dependencies 複製到 root

拒絕。root 沒有 MkDocs config 或 coverage gate，也不在執行時解析 Docker YAML；無需求的工具會
擴大供應鏈與維護面。

## 代價與殘餘限制

- 初次 `uv sync --locked` 需要下載 Python packages；缺少相容 Python 時 uv 也可能下載 managed
  Python。
- `.python-version` 固定 minor 而非 patch，本機與 CI 可能使用不同 3.12 patch；測試證據必須記錄
  實際版本。
- required uv version 升級、pytest／Ruff 升級或 Python minor 升級都需要新的 DEV-A、lock 更新與
  全量回歸。
- `.pytest_cache` 若由舊 identity 建立且不可寫，本 ADR 不授權強制刪除；新設定不再使用它。
- 本 ADR 使用正式 ADR-015；先前未提交 Batch 6.2 交班所預留的 ADR-015 與 exact path manifest
  因此失效，恢復該工作前必須重新編號並重新取得 DEV-A。

## 回復方式

若 root uv 環境造成無法收集或 CI 不相容，停止使用新 quick profile，整體回復
`pyproject.toml`、`.python-version`、`uv.lock`、CI、AGENTS profile、F10 constant／tests、README、
SSOT、ADR-015／index與對應 handover。不得只刪除 lock 或退回裸 `python` 而保留「已鎖定」宣稱。
`.venv` 與 `.uv-cache` 僅在確認是本次建立、不是 reparse point 且位於 repo root 後才可刪除。

## 參考

- [ADR-011](ADR-011-以AGENTS宣告文件快速路徑ValidationProfile.md)
- [ToukaDev framework SSOT](../ssot/README.md)
- [uv project layout](https://docs.astral.sh/uv/concepts/projects/layout/)
- [uv cache](https://docs.astral.sh/uv/concepts/cache/)
- [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)
