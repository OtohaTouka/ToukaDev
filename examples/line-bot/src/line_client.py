"""
LINE API 呼叫層（適配器）。
集中所有 LINE SDK 呼叫，讓業務邏輯層不依賴 SDK，方便測試時 mock。
"""

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

from src.config import settings

_configuration = Configuration(access_token=settings.line_channel_access_token)


def send_reply(reply_token: str, text: str) -> None:
    """透過 LINE API 發送回覆訊息。

    Args:
        reply_token: LINE 事件的 reply token
        text: 要回覆的文字內容
    """
    with ApiClient(_configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)],
            )
        )
