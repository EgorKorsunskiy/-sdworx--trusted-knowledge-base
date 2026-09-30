from pathlib import Path

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "peerpoint.db"


class Settings(BaseSettings):
    app_name: str = "Peerpoint"
    database_url: str = f"sqlite:///{DB_PATH}"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    session_cookie_name: str = "peerpoint_session"
    debug: bool = True


settings = Settings()
