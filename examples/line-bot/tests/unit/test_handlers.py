"""
單元測試：業務邏輯處理函式。
直接測試 handler 函式，不需要 LINE SDK 或 HTTP。
"""

from src.constants import HELP_KEYWORD, HELP_TEXT, WELCOME_MESSAGE
from src.handlers.follow import handle_follow
from src.handlers.message import handle_text_message

# ── 文字訊息處理 ──────────────────────────────────────────────────────────────


def test_echo_returns_same_text():
    """Given: 普通文字 / When: handle_text_message / Then: 回傳原文（Echo 模式）。"""
    assert handle_text_message("你好") == "你好"


def test_echo_preserves_whitespace():
    """Echo 模式下應保留訊息的原始內容（不 strip）。"""
    assert handle_text_message("  hello  ") == "  hello  "


def test_help_keyword_returns_help_text():
    """Given: 「幫助」關鍵字 / When: handle_text_message / Then: 回傳說明文字。"""
    assert handle_text_message(HELP_KEYWORD) == HELP_TEXT


def test_help_keyword_with_leading_trailing_spaces():
    """「幫助」前後有空白時，應仍然觸發說明文字（.strip() 處理）。"""
    assert handle_text_message("  幫助  ") == HELP_TEXT
    assert handle_text_message("\t幫助\n") == HELP_TEXT


def test_non_keyword_text_is_echoed():
    """非關鍵字的訊息應原文回傳。"""
    for text in ["hello", "謝謝", "123", "幫助一下"]:
        result = handle_text_message(text)
        if text.strip() != HELP_KEYWORD:
            assert result == text


# ── 加入好友事件處理 ───────────────────────────────────────────────────────────


def test_follow_returns_welcome_message():
    """Given: 加入好友事件 / When: handle_follow / Then: 回傳歡迎訊息。"""
    assert handle_follow() == WELCOME_MESSAGE


def test_welcome_message_is_non_empty():
    """歡迎訊息不應為空字串。"""
    assert len(handle_follow()) > 0


# ── SSOT 常數驗證 ─────────────────────────────────────────────────────────────


def test_help_keyword_is_non_empty_string():
    """HELP_KEYWORD 應為非空字串。"""
    assert isinstance(HELP_KEYWORD, str)
    assert len(HELP_KEYWORD) > 0


def test_help_text_mentions_help_keyword():
    """HELP_TEXT 應包含 HELP_KEYWORD，讓使用者知道指令名稱。"""
    assert HELP_KEYWORD in HELP_TEXT
