# 骨架與驗證程序（步驟 6–14）

INIT-B 通過後按適用技術棧展開；`assets/` 與 `references/` 以 Skill 根目錄為基準。
新專案只建立根 HANDOVER.md；不建立 active docs/handover/ 或空 HISTORY、roadmap、evidence。
舊交班模板僅供 legacy 來源辨識，不再用於新專案輸出。

已選初始化主代理代審時，同時依 `references/supervised-initialization.md` 管理步驟 6–12、
範圍內修正與最後骨架驗收；未選用仍走原路線。兩個人類 gate 及原始核准規格不由候選改寫。
每階段分清已適用且已建立、依序尚待建立及依核准技術棧不適用的驗證；前期工具未建立
不標 PASS、不永久豁免，記錄補驗步驟與責任人，最終完成前須收斂全部適用待驗項目。
實際命令以專案 AGENTS 及其引用的工具配置為正本；以下命令是依技術棧選用的建置示例。

## 步驟6｜建立目錄結構


根據選定的技術棧，建立以下通用結構（依技術棧調整子目錄名稱）：

```
[專案名稱]/
├── src/                    # 主要程式碼
├── tests/
│   ├── unit/               # 單元測試
│   ├── integration/        # 整合測試
│   ├── smoke/              # 冒煙測試
│   └── fixtures/           # 測試夾具（mock 資料）
├── docs/
│   ├── spec.md             # 已建立（步驟5）
│   ├── index.md            # 文件站首頁（步驟7g建立，完整流程限定）
│   ├── ssot/               # 單一事實來源文件
│   ├── adr/                # 架構決策記錄
│   ├── api/                # API 文件
│   └── interface/          # 系統介面文件
├── scripts/
│   ├── guard_all.py        # SSOT 驗證腳本（一律 Python 實作）
│   ├── guard_security.py   # 安全性檢查腳本（S1–S9，所有專案必生）
│   └── guard_dependencies.py  # 依賴性檢查腳本（僅 Docker 專案，步驟10-4生成）
├── .env.example            # 環境變數範本
├── .gitignore
├── README.md               # 步驟12建立
├── AGENTS.md               # 步驟7建立
├── HANDOVER.md             # 目前狀態與精確入口
├── mkdocs.yml              # 步驟7g建立（完整專案初始化限定，小型專案初始化無）
└── [技術棧設定檔]          # 如 pyproject.toml、package.json 等
```

**若需要 Docker（步驟3確認需要）：**
```
├── docker/
│   └── Dockerfile          # 容器建置設定
├── docker-compose.yml      # 置於專案根（docker compose 與 guard_dependencies.py 的預設讀取位置）
```

> 📄 **範本**：`assets/templates/docker/Dockerfile` → `docker/Dockerfile`；`assets/templates/docker/docker-compose.yml` → 專案根 `docker-compose.yml`。依技術棧替換基底映像、啟動指令、服務名稱與埠號；服務需要的環境變數同步補進 `.env.example`。

---

## 步驟7｜建立文件骨架


### 7a. AGENTS.md

> 📝 **作用域：** 所有正式規則檔都命名為 `AGENTS.md`。框架層與專案層由檔案位置區分；新專案獨立使用時，專案根 `AGENTS.md` 就是該專案的規則正本。

> 📄 **範本**：`assets/templates/AGENTS.md` → 專案根 `AGENTS.md`（填入技術棧、測試與執行命令；「使用者模式」依標準或精簡輸出模式寫入對應 machine token）。

產生的 `AGENTS.md` 必須保留「Quick validation profile」段的命令清單，其 ssot（`guard_all.py`）、
security（`guard_security.py`）與條件式 docs（有 `mkdocs.yml` 時的文件建置）命令不得因技術棧或
輸出模式而刪除。小型專案初始化沒有 `mkdocs.yml` 時，文件建置那一行依條件不執行，不得改寫清單或
靜默替換其他命令。

### 7b. docs/ssot/ 初始文件

建立 `docs/ssot/README.md`：
> 📄 **範本**：`assets/templates/docs-ssot-README.md` → `docs/ssot/README.md`。

### 7c. docs/adr/ 初始文件

建立 `docs/adr/README.md` 和第一筆 ADR：

> 📄 **範本**：`assets/templates/docs-adr-ADR-001.md` → `docs/adr/ADR-001-技術棧選擇.md`（填入步驟2 結論）。

### 7d. 根 HANDOVER.md

使用 `assets/templates/HANDOVER.md` 建立根 `HANDOVER.md`，填入已知狀態、阻礙、下一步及精確連結。
只保留真實已建立的連結，沒有長期記錄需求就不新增其他目錄。
此時狀態應為 project-init 初始化中，記精確步驟、已核准規格、委託來源及待驗項目，
不能因 AGENTS 或 HANDOVER 已生成便記已完成；既有檔案先恢復狀態，不覆蓋重建。

### 7e. docs/api/ 和 docs/interface/ 初始文件

API 有適用內容時建立 README；介面入口使用 `assets/templates/docs-interface-README.md` → `docs/interface/README.md`，填入真實端點／source 對應表，不另造多層導航。

### 7f. docs/glossary.md 術語表

> 📄 **範本**：`assets/templates/glossary.md` → `docs/glossary.md`，讓專案成員在專案內就能查閱術語說明，不需要找到框架目錄。

### 7g. mkdocs.yml 文件站設定（完整流程限定）

> 📄 **範本**：`assets/templates/mkdocs.yml` → 專案根 `mkdocs.yml`（填入專案名稱）。
> 同時建立 `docs/index.md` 作為文件站首頁：一段話介紹專案，並連結 `spec.md` 與 `glossary.md`。
> 小型專案初始化跳過此項（未安裝 MkDocs 依賴；dev-workflow 步驟10e 依 `mkdocs.yml` 是否存在自動跳過，兩邊一致）。

---

## 步驟8｜建置虛擬環境與依賴管理


### Python（uv）

> 💡 尚未安裝 uv？一行指令即可安裝（Windows／macOS／Linux 皆支援）：
> https://docs.astral.sh/uv/getting-started/installation/

```bash
# 初始化專案（若尚未初始化）
uv init

# 新增執行依賴
uv add fastapi uvicorn

# 新增開發依賴
uv add --dev pytest pytest-cov ruff mkdocs mkdocs-material

# Docker 專案（步驟3確認需要）：步驟10 的依賴性檢查腳本需要 pyyaml
uv add --dev pyyaml

# 同步環境
uv sync
```

⚠️ 不使用 `python -m venv`，不使用 `pip install`，一律透過 `uv` 管理依賴。

### JavaScript/TypeScript

```bash
npm init -y
# 或
pnpm init
```

⚠️ **純 JS/TS 專案也需要 uv**：守衛腳本（`guard_*.py`）一律以 Python 實作，請同樣執行上方的 `uv init`，並視情況加裝：完整流程 `uv add --dev mkdocs mkdocs-material`（文件系統）、Docker 專案 `uv add --dev pyyaml`，讓 `uv run python scripts/guard_*.py` 與 `uv run mkdocs build` 可以執行。

### 建立 .env.example

> 📄 **範本**：`assets/templates/env.example` → 專案根 `.env.example`。

同時在 `docs/spec.md` 的「環境規劃」區塊補充以下說明（若尚未加入）：

> 📄 **附加段落**：`assets/templates/spec-env-management-note.md` —— 補進 `docs/spec.md` 的「環境規劃」區塊。

### 建立 .gitignore

> 📄 **範本**：`assets/templates/gitignore` → 專案根 `.gitignore`。

---

## 步驟9｜建立測試目錄與基礎設定


### Python 專案

建立以下檔案（AI 直接以檔案工具建立，跨平台皆可，不依賴 `touch` 等 shell 指令）：

- `tests/conftest.py`（pytest 共用夾具）：
  > 📄 **範本**：`assets/templates/conftest.py` → `tests/conftest.py`。
- `tests/fixtures/__init__.py`（空檔案）

建立 `pytest.ini` 或在 `pyproject.toml` 加入：
> 📄 **範本**：`assets/templates/pytest-config.toml` —— 合併進 `pyproject.toml`。

### JavaScript/TypeScript 專案

建立 `tests/fixtures/index.js`（或 `.ts`，空檔案，AI 直接以檔案工具建立）。

`jest.config.js` 或 `vitest.config.js` 基礎設定（依選定框架）。

按 INIT-B 核准的可執行骨架能力建立至少一個可觀察成功與失敗的最小測試，新增／修復
可測行為仍先 RED 再 GREEN。沒有可執行能力者記不適用理由，不為湊測試增加業務功能。
實際執行專案宣告的測試並記錄收集數與結果；只有空 fixtures、配置存在或零收集不得宣稱通過。

---

## 步驟10｜設定靜態檢查與守衛腳本


> ⚠️ 本步驟必須在目錄結構（步驟6）、環境建置（步驟8）和技術棧確認（INIT-A）之後執行。
> 守衛腳本（10-3 起）一律以 Python 實作（單一模板、行為跨專案一致）；純 JS/TS 專案也透過 uv 執行（見步驟8）。
> 所有腳本生成後必須實際執行一次（10-7），確認零錯誤才繼續。

### 10-1｜Python 靜態檢查：ruff

建立 `pyproject.toml` 的 ruff 區段（若已存在則合併）：

> 📄 **範本**：`assets/templates/pyproject-ruff.toml` —— 合併進 `pyproject.toml`（已存在則 merge）。

⚠️ 這是推薦預設值。若專案有自訂規則，初始化完成後告知 AI 更新。

---

### 10-2｜JS/TS 靜態檢查：ESLint

建立 `eslint.config.mjs`（ESLint 9+ flat config，`.mjs` 確保不受 package.json 的 `type` 設定影響）：

> 📄 **範本**：`assets/templates/eslint.config.mjs` → 專案根 `eslint.config.mjs`（JS/TS 專案）。

⚠️ 這是推薦預設值。若專案有自訂規則，初始化完成後告知 AI 更新。

---

### 10-3｜生成 `scripts/guard_all.py`

此腳本是專案所有 SSOT 靜態檢查的**單一入口**。
AI 根據技術棧自動生成，包含基礎版檢查項目，並預留進階擴充區。

**生成邏輯：**

AI 必須根據以下模板生成 `scripts/guard_all.py`，並將檔頭的 `SRC`、`FRONTEND_SRC`、`OPENAPI_PATH`、`DOCKER_COMPOSE` 等佔位變數替換為步驟6建立的實際目錄路徑：

> 🐍 **腳本範本**：`assets/templates/scripts/guard_all.py` → 複製到專案 `scripts/guard_all.py`，依步驟6 實際目錄替換檔頭 `SRC`/`FRONTEND_SRC`/`OPENAPI_PATH`/`DOCKER_COMPOSE` 等佔位變數。

---

### 10-4｜生成 `scripts/guard_dependencies.py`

**僅在步驟3確認需要 Docker 時生成此腳本。**
若不需要 Docker，跳過此步驟。

**生成邏輯：**

AI 必須讀取步驟6生成的專案根 `docker-compose.yml` 內容，
再根據以下模板生成 `scripts/guard_dependencies.py`，
並將服務名稱、目錄路徑替換為實際值：

> 🐍 **腳本範本**：`assets/templates/scripts/guard_dependencies.py` → `scripts/guard_dependencies.py`（僅 Docker 專案；讀實際 `docker-compose.yml` 後替換服務/路徑）。

---

### 10-5｜生成 `scripts/guard_security.py`（安全守衛，**所有專案必生**）

安全風險不分專案大小、且多為不可逆（如金鑰外洩），故**無條件生成**（不像進階 SSOT 檢查那樣選配）。

> 🐍 **腳本範本**：`assets/templates/scripts/guard_security.py` → 複製到 `scripts/guard_security.py`，依步驟6 替換檔頭 `SRC`／`FRONTEND_SRC`（無前端設 `None`）；若已知公開的寫入端點（如 webhook），填入 `PUBLIC_ROUTES`。內含 S1–S9（金鑰外洩、.env 同步、SQL 拼接、localStorage、端點認證、錯誤洩漏、弱雜湊、弱 RNG、無 schema 輸入），預設全開；細節見 `docs/ssot/guard_guide.md` 的「安全守衛」章節。

---

### 10-6｜生成 `scripts/export_openapi.py`

**僅在技術棧包含 FastAPI 時生成此腳本。**

此腳本在每次修改後端 API 後執行，匯出最新的 `openapi.json`，
供 `guard_all.py` 的前後端同步檢查使用。

> 🐍 **腳本範本**：`assets/templates/scripts/export_openapi.py` → `scripts/export_openapi.py`（僅 FastAPI；替換 `src.main`/`app` 為實際路徑）。

---

### 10-7｜腳本生成後的必要動作（執行驗證）

腳本全部生成後，AI 必須依序執行：

```bash
# 1. 確認腳本可執行
uv run python scripts/guard_all.py
uv run python scripts/guard_security.py
uv run python scripts/guard_dependencies.py   # 僅 Docker 專案

# 2. FastAPI 專案額外執行
uv run python scripts/export_openapi.py

# 3. 完整流程專案額外執行：確認文件站可建置
uv run mkdocs build

# 4. 確認各項輸出對應的成功訊息：
# guard_all.py          → ✅ 無 ERROR，可以繼續。
# guard_security.py     → ✅ 無安全性 ERROR，可以繼續。
# guard_dependencies.py → ✅ 依賴性檢查通過，零問題。
# export_openapi.py     → ✅ openapi.json 已匯出至：[路徑]
# mkdocs build          → 建置完成且無 WARNING / ERROR（僅完整流程）
```

若輸出為錯誤，AI 必須修復後才能繼續步驟11。依原始錯誤追查實際環境或生成階段，
不預先假定只可能是步驟6／7的設定。第三次同方向相同錯誤按 debug-escalation 保留 FAIL、
五維分析與 DBG-A；修復後回 project-init 步驟 10-7，不提前交棒 dev-workflow。
尚未建立工具的前期故障按階段記待驗；已到此步驟的必要工具仍不可用或驗證失敗不得略過。

---

### 10-8｜進階項目啟用說明（寫入 `docs/ssot/guard_guide.md`）

AI 必須建立此文件，讓使用者知道未來如何擴充：

> 📄 **範本**：`assets/templates/docs-ssot-guard_guide.md` → `docs/ssot/guard_guide.md`。

---

## 步驟10 完成確認清單

```
□ pyproject.toml 已加入 ruff 設定
□ eslint.config.mjs 已建立（JS/TS 專案）
□ scripts/guard_all.py 已生成並執行通過
□ scripts/guard_security.py 已生成並執行通過（零 ERROR 基線）
□ scripts/guard_dependencies.py 已生成並執行通過（Docker 專案）
□ scripts/export_openapi.py 已生成（FastAPI 專案）
□ mkdocs.yml 已建立且 mkdocs build 無 WARNING/ERROR（完整流程）
□ docs/ssot/guard_guide.md 已建立
□ 所有腳本執行結果為零錯誤
```

---

## 步驟11｜設定 CI/CD


沿用 INIT-A／INIT-B 及步驟4 已確認的 CI/CD 平台；不需要或小型專案已核准省略時跳過。
只有缺少且影響產出的決定才詢問，不再次要求人類選同一平台。核准規格實質改變時返回
原核准 gate；依選定平台建立基礎設定檔，本地檔案檢查不等於遠端 CI 實跑或部署成功。

**GitHub Actions（`.github/workflows/ci.yml`）骨架：**
> 📄 **範本**：`assets/templates/ci/github-actions-ci.yml` → `.github/workflows/ci.yml`。

**GitLab CI（`.gitlab-ci.yml`）骨架：**
> 📄 **範本**：`assets/templates/ci/gitlab-ci.yml` → `.gitlab-ci.yml`。

**Bitbucket Pipelines（`bitbucket-pipelines.yml`）骨架：**
> 📄 **範本**：`assets/templates/ci/bitbucket-pipelines.yml` → `bitbucket-pipelines.yml`。

**CircleCI（`.circleci/config.yml`）骨架：**
> 📄 **範本**：`assets/templates/ci/circleci-config.yml` → `.circleci/config.yml`。

⚠️ 告知人類：CI/CD 設定檔只是骨架，需要根據實際技術棧和部署環境調整。

---

## 步驟12｜建立 README.md


> 📄 **範本**：`assets/templates/README.md` → 專案根 `README.md`（填入專案名稱、結構等）。

### 最終骨架驗收

依 INIT-B 的品質與初始化驗收表核對完整候選：核准目錄及文件齊全、必要欄位填妥、
跨檔案整合一致、工具鏈可用、實際測試／lint／guard／適用文件建置及匯出都有原始結果，
所有適用待驗項目均完成。必要 HIGH／BLOCKING 問題、工具缺口或驗證失敗未解時，
只能交付部分成果與阻礙，不能宣告初始化完成。

有可執行骨架者須符合步驟9的最小行為驗收；CI/CD 設定、遠端 CI、業務功能與部署分開
標示，未實跑者為 NOT RUN。主代理模式暫停候選寫入，依專用程序收齊完整候選與原 FAIL、
驗證證據及偏差，作初始化 SUPERVISOR_ACCEPTANCE；此驗收不是 dev-workflow DEV-B。
候選有差異須重建並重新驗收，不能用各執行者摘要取代整體核對。
步驟14所需的完成狀態、限制與下一步先由執行者納入這份候選；Git 尚未執行時據實記
未提交／待執行，實際 Git 結果另以可核對的交付紀錄報告，不為寫入 commit hash 自行改候選。

## 步驟13｜初始 git commit


先展示完整候選與驗證結果，逐項核對當次 git init／stage／commit 授權；不可由 INIT-B
或骨架驗收推定。當次委託已明確包含者不重問；沒有相應授權者跳過該操作，交付未提交
候選並進入步驟14記錄終態，不強迫提交。以下只示範已明確授權的操作；已有 repo 不重新 init。

```bash
git init
git add -- [人類核准的明確路徑]
git status   # 確認沒有不該提交的檔案（特別確認 .env 不在清單內）
git commit -m "init: 專案初始化

- 技術棧：[選定的技術棧]
- 目錄結構：src/, tests/, docs/, scripts/
- 文件骨架：spec.md, SSOT, ADR-001, HANDOVER.md
- 靜態檢查：ruff / ESLint, SSOT腳本
- CI/CD：[平台名稱] 骨架設定
- README.md, AGENTS.md, .gitignore, .env.example"
```

stage 前核對候選範圍與 secrets。選用初始化主代理時，只 stage 驗收時記下的路徑，commit 前以
`git write-tree` 比對驗收時記下的 tree 編號，相同才 commit，提交後核對 `HEAD^{tree}`；其他路線只使用
核准清單，核對 staged 路徑、狀態、內容及差異均與完整候選相符，提交後核對實際 commit。任何不同或漂移
返回骨架驗收，不混入其他工作。

---

## 步驟14｜交棒 dev-workflow


只有最終骨架驗收通過才記完成，可宣告「骨架已驗收，Git 未提交」或列實際 commit。
尚有必要待驗或阻礙時維持「初始化中／部分成果」，列原步驟及缺少證據，不自動進 dev。

更新 `HANDOVER.md`：
- 記錄 project-init 的精確終態、所驗完整候選與原始驗證證據、選定技術棧及限制。
- 分別記 Git 狀態、CI/CD 設定與實跑；未測或未執行項據實說明。
- 下一步可列第一個功能及 dev-workflow 入口；一般初始化委託到完成即結束，只有當次
  原始委託已明確涵蓋其功能範圍與 DEV 審核才接續。交棒本身不新增功能、Git 或部署權限。

上述狀態內容在最終骨架驗收前整合；若本步驟仍修改已受審的 tracked／untracked 候選，
須由執行者重建並回到完整骨架驗收。必要時明示驗收後新增的未提交差異，不推定額外 commit 授權。

---
