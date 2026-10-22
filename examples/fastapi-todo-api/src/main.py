"""
FastAPI 應用程式進入點。
"""

from fastapi import FastAPI

from src.database import Base, engine
from src.routers import todos


def create_app() -> FastAPI:
    app = FastAPI(
        title="Todo API",
        description="ToukaDev 範例專案：使用 FastAPI + SQLAlchemy 建立的 Todo 管理 API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 建立所有資料表（開發用；正式環境應改用 Alembic migration）
    Base.metadata.create_all(bind=engine)

    # 掛載路由
    app.include_router(todos.router)

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()
