"""
加入好友事件處理邏輯（純函式，不依賴 LINE SDK）。
"""

from src.constants import WELCOME_MESSAGE


def handle_follow() -> str:
    """處理加入好友事件，回傳歡迎訊息。

    Returns:
        Bot 要發送的歡迎訊息文字
    """
    return WELCOME_MESSAGE
