"""
整合測試：LINE webhook 端點。
透過 HTTP client 測試完整的 webhook 流程，使用 mock 避免實際呼叫 LINE API。
"""

import json
from unittest.mock import patch

from tests.conftest import make_line_signature

# ── 測試用 webhook payload 工廠函式 ────────────────────────────────────────────


def _message_body(text: str, reply_token: str = "test_reply_token") -> bytes:
    """建立 LINE 文字訊息事件的 webhook 請求內容。"""
    return json.dumps(
        {
            "destination": "Utest",
            "events": [
                {
                    "type": "message",
                    "mode": "active",
                    "timestamp": 1234567890000,
                    "replyToken": reply_token,
                    "webhookEventId": "01ABCDEFGHIJKLMNOPQRSTUVWX",
                    "deliveryContext": {"isRedelivery": False},
                    "source": {"type": "user", "userId": "Udeadbeef"},
                    "message": {
                        "id": "468789577898323",
                        "type": "text",
                        "quoteToken": "test",
                        "text": text,
                    },
                }
            ],
        }
    ).encode("utf-8")


def _follow_body(reply_token: str = "test_follow_token") -> bytes:
    """建立 LINE 加入好友事件的 webhook 請求內容。"""
    return json.dumps(
        {
            "destination": "Utest",
            "events": [
                {
                    "type": "follow",
                    "mode": "active",
                    "timestamp": 1234567890000,
                    "replyToken": reply_token,
                    "webhookEventId": "01ABCDEFGHIJKLMNOPQRSTUVWX",
                    "deliveryContext": {"isRedelivery": False},
                    "source": {"type": "user", "userId": "Udeadbeef"},
                    "follow": {"isUnblocked": False},
                }
            ],
        }
    ).encode("utf-8")


def _post_webhook(client, body: bytes):
    """發送帶有正確 LINE 簽名的 webhook 請求。"""
    return client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": make_line_signature(body),
        },
    )


# ── 健康檢查 ────────────────────────────────────────────────────────────────


def test_health_check(client):
    """GET /health 應回傳 200。"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── 文字訊息：Echo ────────────────────────────────────────────────────────────


def test_webhook_echoes_text_message(client):
    """Given: 普通文字訊息 / When: POST /webhook / Then: 呼叫 send_reply 原文回傳。"""
    body = _message_body("你好")
    with patch("src.main.send_reply") as mock_send:
        response = _post_webhook(client, body)

    assert response.status_code == 200
    mock_send.assert_called_once_with("test_reply_token", "你好")


# ── 文字訊息：幫助指令 ─────────────────────────────────────────────────────────


def test_webhook_help_command_returns_help_text(client):
    """Given: 「幫助」訊息 / When: POST /webhook / Then: 呼叫 send_reply 回傳說明。"""
    from src.constants import HELP_TEXT

    body = _message_body("幫助")
    with patch("src.main.send_reply") as mock_send:
        response = _post_webhook(client, body)

    assert response.status_code == 200
    mock_send.assert_called_once_with("test_reply_token", HELP_TEXT)


# ── 加入好友事件 ──────────────────────────────────────────────────────────────


def test_webhook_follow_event_sends_welcome(client):
    """Given: 加入好友事件 / When: POST /webhook / Then: 呼叫 send_reply 發送歡迎訊息。"""
    from src.constants import WELCOME_MESSAGE

    body = _follow_body()
    with patch("src.main.send_reply") as mock_send:
        response = _post_webhook(client, body)

    assert response.status_code == 200
    mock_send.assert_called_once_with("test_follow_token", WELCOME_MESSAGE)


# ── 簽名驗證 ───────────────────────────────────────────────────────────────────


def test_webhook_invalid_signature_returns_400(client):
    """Given: 錯誤的 X-Line-Signature / When: POST /webhook / Then: 回傳 400。"""
    body = _message_body("你好")
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": "invalid_signature",
        },
    )
    assert response.status_code == 400


def test_webhook_missing_signature_returns_400(client):
    """Given: 缺少 X-Line-Signature header / When: POST /webhook / Then: 回傳 400。"""
    body = _message_body("你好")
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
