"""
Todo 路由：定義所有 /todos 相關的 API 端點。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import Todo
from src.schemas import TodoCreate, TodoResponse

router = APIRouter(prefix="/todos", tags=["todos"])


@router.post("", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(todo_in: TodoCreate, db: Session = Depends(get_db)):
    """建立一個新的 Todo。"""
    todo = Todo(**todo_in.model_dump())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.get("", response_model=list[TodoResponse])
def list_todos(completed: bool | None = None, db: Session = Depends(get_db)):
    """列出所有 Todo。可用 ?completed=true 或 ?completed=false 篩選。"""
    query = db.query(Todo)
    if completed is not None:
        query = query.filter(Todo.completed == completed)
    return query.order_by(Todo.created_at.desc()).all()


@router.patch("/{todo_id}/complete", response_model=TodoResponse)
def complete_todo(todo_id: int, db: Session = Depends(get_db)):
    """將指定 Todo 標記為已完成。"""
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo id={todo_id} 不存在",
        )
    todo.completed = True
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, db: Session = Depends(get_db)):
    """刪除指定 Todo。"""
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo id={todo_id} 不存在",
        )
    db.delete(todo)
    db.commit()
