"""
FastAPI 應用程式進入點與 LINE webhook 路由。
"""

from fastapi import FastAPI, Header, HTTPException, Request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

from src.config import settings
from src.handlers.follow import handle_follow
from src.handlers.message import handle_text_message
from src.line_client import send_reply

webhook_handler = WebhookHandler(settings.line_channel_secret)


def create_app() -> FastAPI:
    app = FastAPI(
        title="LINE Bot",
        description="ToukaDev 範例專案：LINE Messaging API Bot",
        version="0.1.0",
    )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.post("/webhook")
    async def webhook(
        request: Request,
        x_line_signature: str = Header(None),
    ):
        """LINE Messaging API webhook 端點。"""
        body = await request.body()
        if not x_line_signature:
            raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")
        try:
            webhook_handler.handle(body.decode("utf-8"), x_line_signature)
        except (InvalidSignatureError, Exception) as e:
            if "signature" in str(e).lower() or isinstance(e, InvalidSignatureError):
                raise HTTPException(status_code=400, detail="Invalid signature")
            raise
        return "OK"

    return app


app = create_app()


# ── 事件處理器（handler decorator 必須在 app 建立後才能註冊）──────────────────


@webhook_handler.add(MessageEvent, message=TextMessageContent)
def on_text_message(event: MessageEvent) -> None:
    """處理文字訊息事件。"""
    reply_text = handle_text_message(event.message.text)
    send_reply(event.reply_token, reply_text)


@webhook_handler.add(FollowEvent)
def on_follow(event: FollowEvent) -> None:
    """處理加入好友事件。"""
    welcome_text = handle_follow()
    send_reply(event.reply_token, welcome_text)
