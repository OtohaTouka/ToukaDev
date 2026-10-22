"""
資料庫連線設定。
SQLAlchemy engine、Session factory、Base class 集中於此，其他模組 import 引用。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings

engine = create_engine(
    settings.database_url,
    # SQLite 需要此設定以允許多執行緒存取
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依賴注入用的資料庫 session 工廠。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
