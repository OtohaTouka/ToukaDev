"""
設定層：所有環境變數必須透過此模組取得。
禁止在其他模組直接使用 os.environ 或 os.getenv。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_port: int = 8000
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
