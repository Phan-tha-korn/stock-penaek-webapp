from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config_loader import load_master_config


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ESP_", case_sensitive=False)

    env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str | None = None
    redis_url: str | None = None

    jwt_secret: str = "dev-secret"
    jwt_issuer: str = "enterprise-stock-platform"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    reauth_after_hours: int = 24

    login_secret_phrase: str = "dev-passphrase"
    failed_login_limit: int = 5
    failed_login_lock_minutes: int = 15
    session_max_per_user: int = 3

    # Google Sheets
    google_sheets_id: str = ""
    google_service_account_key_path: str = "./credentials/google_key.json"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""
    google_oauth_token_path: str = "./credentials/google_oauth_token.json"
    google_sheets_sync_interval_seconds: int = 10
    line_token_stock: str = ""
    line_token_admin: str = ""
    line_token_accountant: str = ""
    line_token_owner: str = ""
    line_token_dev: str = ""

    notification_enabled: bool = False
    notification_low_levels_pct: list[int] = [50, 20, 10, 0]
    notification_high_levels_pct: list[int] = [80, 90, 100]
    notification_roles: list[str] = ["OWNER"]

    enforce_https: bool = False

    @staticmethod
    def from_master_config() -> "Settings":
        cfg = load_master_config()
        s = Settings()
        jwt_secret = str(cfg.get("jwt_secret") or s.jwt_secret)
        if jwt_secret == "CHANGE_ME_IN_INSTALLER":
            jwt_secret = s.jwt_secret
        s.jwt_secret = jwt_secret

        raw_login_phrase = cfg.get("login_secret_phrase", None)
        if raw_login_phrase is not None:
            login_phrase = str(raw_login_phrase)
            if login_phrase == "CHANGE_ME_IN_INSTALLER":
                login_phrase = s.login_secret_phrase
            s.login_secret_phrase = login_phrase
        s.session_max_per_user = int(cfg.get("session_max_per_user") or s.session_max_per_user)
        s.reauth_after_hours = int(cfg.get("reauth_after_hours") or s.reauth_after_hours)
        s.enforce_https = bool(cfg.get("enforce_https") or False) if s.env == "production" else False
        
        google_sheets = cfg.get("google_sheets", {})
        s.google_sheets_id = str(google_sheets.get("sheet_id") or cfg.get("google_sheets_id") or s.google_sheets_id)
        s.google_service_account_key_path = str(
            google_sheets.get("service_account_key_path")
            or cfg.get("google_service_account_key_path")
            or s.google_service_account_key_path
        )
        s.google_oauth_client_id = str(cfg.get("google_oauth_client_id") or google_sheets.get("oauth_client_id") or s.google_oauth_client_id)
        s.google_oauth_client_secret = str(cfg.get("google_oauth_client_secret") or google_sheets.get("oauth_client_secret") or s.google_oauth_client_secret)
        s.google_oauth_redirect_uri = str(cfg.get("google_oauth_redirect_uri") or google_sheets.get("oauth_redirect_uri") or s.google_oauth_redirect_uri)
        s.google_oauth_token_path = str(cfg.get("google_oauth_token_path") or google_sheets.get("oauth_token_path") or s.google_oauth_token_path)
        s.google_sheets_sync_interval_seconds = int(
            google_sheets.get("sync_interval_seconds")
            or cfg.get("google_sheets_sync_interval_seconds")
            or s.google_sheets_sync_interval_seconds
        )

        s.line_token_stock = str(cfg.get("line_token_stock") or s.line_token_stock)
        s.line_token_admin = str(cfg.get("line_token_admin") or s.line_token_admin)
        s.line_token_accountant = str(cfg.get("line_token_accountant") or s.line_token_accountant)
        s.line_token_owner = str(cfg.get("line_token_owner") or s.line_token_owner)
        s.line_token_dev = str(cfg.get("line_token_dev") or s.line_token_dev)

        s.notification_enabled = bool(cfg.get("notification_enabled") or False)
        low_levels = cfg.get("notification_low_levels_pct", None)
        if isinstance(low_levels, list):
            s.notification_low_levels_pct = [int(x) for x in low_levels if str(x).strip() != ""]
        high_levels = cfg.get("notification_high_levels_pct", None)
        if isinstance(high_levels, list):
            s.notification_high_levels_pct = [int(x) for x in high_levels if str(x).strip() != ""]
        roles = cfg.get("notification_roles", None)
        if isinstance(roles, list):
            s.notification_roles = [str(x) for x in roles if str(x).strip()]

        return s

    def resolved_database_url(self) -> str:
        if self.database_url:
            url = self.database_url
            if url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://") :]

            if url.startswith("postgresql+asyncpg://"):
                parts = urlsplit(url)
                qs = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k not in ("sslmode", "channel_binding")]
                url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs), parts.fragment))

            return url
        return "sqlite+aiosqlite:///./server/db/app.db"


settings = Settings.from_master_config()

