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
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:5177",
        "http://127.0.0.1:5177",
        "http://localhost:5178",
        "http://127.0.0.1:5178",
    ]
    debug: bool = True

    # --- Authentication (OAuth2 authorization code + PKCE, JWT access tokens) ---
    jwt_issuer: str = "peerpoint"
    jwt_audience: str = "peerpoint-api"
    # Defaults; Admins can change them in the settings page (access_token_minutes, refresh_token_hours).
    access_token_minutes: int = 15
    refresh_token_hours: int = 8
    refresh_cookie_name: str = "peerpoint_refresh"
    cookie_secure: bool = False  # set True behind HTTPS
    keys_dir: Path = BASE_DIR / ".keys"  # RSA signing keys, generated on first start

    # Identity provider. "mock" serves a built-in dev IdP under /idp.
    idp_mode: str = "mock"
    idp_client_id: str = "peerpoint-web"
    idp_issuer: str = "http://localhost/mock-idp"
    # Demo user picker (/auth/dev-login, /auth/users). Disable outside dev/demo.
    demo_mode: bool = True
    # Seed a 3-version demo entry (tag history-demo) to show the change log and diffs.
    seed_history_demo: bool = True


settings = Settings()
