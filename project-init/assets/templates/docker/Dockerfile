# ============================================================
# Dockerfile 骨架（由 project-init 步驟6建立，僅 Docker 專案）
# ⚠️ 基底映像、依賴安裝、啟動指令需依實際技術棧調整。
# 預設為 Python + uv；JS/TS 專案見檔尾改寫參考。
# ============================================================
FROM python:3.12-slim

# 取得 uv 執行檔（本框架一律以 uv 管理 Python 依賴；版本釘住並和本機一致，升級時一起改）
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

WORKDIR /app

# 先安裝依賴（單獨成層，程式碼變動時不需重裝依賴）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再複製程式碼並完成同步
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# [啟動指令依實際進入點調整]
# FastAPI 範例：CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["uv", "run", "python", "-m", "src.main"]

# ── JS/TS 專案改寫參考 ──────────────────────────────────────
# FROM node:22-slim
# WORKDIR /app
# COPY package.json package-lock.json ./
# RUN npm ci --omit=dev
# COPY src/ ./src/
# CMD ["node", "src/main.js"]
