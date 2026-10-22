"""
Pydantic 資料驗證 schema。
API 的請求與回應格式定義集中於此。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from src.constants import MAX_TITLE_LENGTH


class TodoCreate(BaseModel):
    """建立 Todo 的請求格式。"""

    title: str = Field(..., min_length=1, max_length=MAX_TITLE_LENGTH, description="Todo 標題")
    description: str | None = Field(None, description="Todo 詳細描述（可選）")


class TodoResponse(BaseModel):
    """Todo 的回應格式。"""

    id: int
    title: str
    description: str | None
    completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
