"""
pytest 共用 fixtures。
所有測試使用 in-memory SQLite，完全隔離，每個測試函式都從空白資料庫開始。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app

# 測試用 in-memory SQLite，不會影響開發資料庫
# StaticPool 確保所有連線共用同一個記憶體資料庫，避免「no such table」問題
TEST_DATABASE_URL = "sqlite://"


@pytest.fixture
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = testing_session_local()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """提供測試用 HTTP client，已注入隔離的測試資料庫。"""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
