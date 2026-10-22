"""
單元測試：Todo 資料模型。
測試模型的欄位行為，不依賴資料庫連線。

注意：SQLAlchemy 的 Column default 在 INSERT 時才生效（不是 Python 物件建立時）。
      「建立 Todo 後 completed 預設為 False」的行為由整合測試 test_create_todo_returns_201 驗證。
"""

from src.constants import DEFAULT_COMPLETED
from src.models import Todo


def test_todo_completed_false_value_matches_ssot_constant():
    """SSOT 常數 DEFAULT_COMPLETED 的值應為 False（不是 None、0 或其他）。"""
    assert DEFAULT_COMPLETED is False


def test_todo_explicit_completed_false():
    """建立 Todo 時明確傳入 completed=False，屬性應正確儲存。"""
    todo = Todo(title="測試 Todo", completed=False)
    assert todo.completed is False
    assert todo.completed == DEFAULT_COMPLETED


def test_todo_explicit_completed_true():
    """建立 Todo 時明確傳入 completed=True，屬性應正確儲存。"""
    todo = Todo(title="已完成的 Todo", completed=True)
    assert todo.completed is True


def test_todo_title_is_set_correctly():
    """建立 Todo 時，title 應正確儲存。"""
    todo = Todo(title="買牛奶")
    assert todo.title == "買牛奶"


def test_todo_description_is_optional():
    """description 為選填欄位，不傳時應為 None。"""
    todo = Todo(title="無描述的 Todo")
    assert todo.description is None


def test_todo_with_description():
    """有傳 description 時應正確儲存。"""
    todo = Todo(title="有描述的 Todo", description="記得買低脂牛奶")
    assert todo.description == "記得買低脂牛奶"
