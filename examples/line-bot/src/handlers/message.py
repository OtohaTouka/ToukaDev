"""
文字訊息處理邏輯（純函式，不依賴 LINE SDK）。
DIP 原則：業務邏輯與 SDK 呼叫分離，方便單元測試。
"""

from src.constants import HELP_KEYWORD, HELP_TEXT


def handle_text_message(text: str) -> str:
    """處理文字訊息，回傳要回覆的文字。

    Args:
        text: 使用者傳入的文字訊息

    Returns:
        Bot 要回覆的文字
    """
    if text.strip() == HELP_KEYWORD:
        return HELP_TEXT
    return text  # Echo 模式：原文回傳
