"""
整合測試：Todo API 端點。
透過 HTTP client 測試完整的請求/回應流程。
"""


# ── 建立 Todo ─────────────────────────────────────────────────────────────────


def test_create_todo_returns_201(client):
    """Given: 有效的 Todo 資料 / When: POST /todos / Then: 回傳 201 與建立的 Todo。"""
    response = client.post("/todos", json={"title": "買牛奶"})
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "買牛奶"
    assert data["completed"] is False
    assert "id" in data
    assert "created_at" in data


def test_create_todo_with_description(client):
    """Given: 含描述的 Todo 資料 / When: POST /todos / Then: 描述應正確回傳。"""
    response = client.post("/todos", json={"title": "買牛奶", "description": "記得買低脂"})
    assert response.status_code == 201
    assert response.json()["description"] == "記得買低脂"


def test_create_todo_missing_title_returns_422(client):
    """Given: 缺少 title 的請求 / When: POST /todos / Then: 回傳 422 驗證錯誤。"""
    response = client.post("/todos", json={"description": "沒有標題"})
    assert response.status_code == 422


def test_create_todo_empty_title_returns_422(client):
    """Given: 空字串 title / When: POST /todos / Then: 回傳 422 驗證錯誤。"""
    response = client.post("/todos", json={"title": ""})
    assert response.status_code == 422


# ── 列出 Todo ─────────────────────────────────────────────────────────────────


def test_list_todos_returns_all(client):
    """Given: 已建立 3 個 Todo / When: GET /todos / Then: 回傳全部 3 筆。"""
    client.post("/todos", json={"title": "Todo 1"})
    client.post("/todos", json={"title": "Todo 2"})
    client.post("/todos", json={"title": "Todo 3"})

    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_list_todos_empty_returns_empty_list(client):
    """Given: 沒有任何 Todo / When: GET /todos / Then: 回傳空陣列。"""
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []


def test_list_todos_filter_completed_true(client):
    """Given: 1 個已完成、1 個未完成 / When: GET /todos?completed=true / Then: 只回傳已完成。"""
    client.post("/todos", json={"title": "未完成的 Todo"})
    r = client.post("/todos", json={"title": "待完成的 Todo"})
    client.patch(f"/todos/{r.json()['id']}/complete")

    response = client.get("/todos?completed=true")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "待完成的 Todo"


def test_list_todos_filter_completed_false(client):
    """Given: 1 個已完成、2 個未完成 / When: GET /todos?completed=false / Then: 只回傳未完成的 2 筆。"""
    client.post("/todos", json={"title": "未完成 1"})
    client.post("/todos", json={"title": "未完成 2"})
    r = client.post("/todos", json={"title": "已完成"})
    client.patch(f"/todos/{r.json()['id']}/complete")

    response = client.get("/todos?completed=false")
    assert response.status_code == 200
    assert len(response.json()) == 2


# ── 標記完成 ─────────────────────────────────────────────────────────────────


def test_complete_todo_returns_200(client):
    """Given: 一個未完成的 Todo / When: PATCH /todos/{id}/complete / Then: 回傳 200 且 completed=true。"""
    todo = client.post("/todos", json={"title": "要完成的 Todo"}).json()

    response = client.patch(f"/todos/{todo['id']}/complete")
    assert response.status_code == 200
    assert response.json()["completed"] is True


def test_complete_nonexistent_todo_returns_404(client):
    """Given: 不存在的 Todo id / When: PATCH /todos/99999/complete / Then: 回傳 404。"""
    response = client.patch("/todos/99999/complete")
    assert response.status_code == 404


# ── 刪除 Todo ─────────────────────────────────────────────────────────────────


def test_delete_todo_returns_204(client):
    """Given: 存在的 Todo / When: DELETE /todos/{id} / Then: 回傳 204 且 Todo 消失。"""
    todo = client.post("/todos", json={"title": "要刪除的 Todo"}).json()

    response = client.delete(f"/todos/{todo['id']}")
    assert response.status_code == 204

    # 確認 Todo 已不存在
    list_response = client.get("/todos")
    assert all(t["id"] != todo["id"] for t in list_response.json())


def test_delete_nonexistent_todo_returns_404(client):
    """Given: 不存在的 Todo id / When: DELETE /todos/99999 / Then: 回傳 404。"""
    response = client.delete("/todos/99999")
    assert response.status_code == 404
