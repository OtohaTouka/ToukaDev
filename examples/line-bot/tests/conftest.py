"""
pytest 共用設定與 fixtures。

重要：LINE_CHANNEL_SECRET 和 LINE_CHANNEL_ACCESS_TOKEN 必須在 import src.main
之前設定，否則模組層級的 WebhookHandler 和 Configuration 會拿到空字串。
"""

import base64
import hashlib
import hmac
import os

# ── 設定測試用環境變數（必須在任何 src.* import 之前）──────────────────────────
TEST_CHANNEL_SECRET = "test_channel_secret_for_pytest"
TEST_CHANNEL_TOKEN = "test_channel_access_token"

os.environ["LINE_CHANNEL_SECRET"] = TEST_CHANNEL_SECRET
os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = TEST_CHANNEL_TOKEN

# ── 現在才 import app（會讀到上面設定的環境變數）───────────────────────────────
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.main import app  # noqa: E402


def make_line_signature(body: bytes) -> str:
    """計算 LINE webhook 的 HMAC-SHA256 簽名。"""
    digest = hmac.new(
        TEST_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


@pytest.fixture
def client():
    """提供測試用 HTTP client。"""
    with TestClient(app) as c:
        yield c
