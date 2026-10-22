"""
SQLAlchemy 資料模型。
使用 SQLAlchemy 2.0 的 Mapped + mapped_column API，確保 Python 物件建立時就套用預設值。
"""

from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.constants import DEFAULT_COMPLETED, MAX_TITLE_LENGTH
from src.database import Base


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(MAX_TITLE_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True, default=None)
    completed: Mapped[bool] = mapped_column(default=DEFAULT_COMPLETED, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
