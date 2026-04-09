from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import secrets

from .config_loader import load_master_config
from .paths import app_db_path, ensure_local_data_layout


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ESP_", case_sensitive=False)

    env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str | None = None
    redis_url: str | None = None

    jwt_secret: str = ""
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
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    notification_email_stock: str = ""
    notification_email_admin: str = ""
    notification_email_accountant: str = ""
    notification_email_owner: str = ""
    notification_email_dev: str = ""
    dev_backup_password: str = ""
    login_rate_limit_per_minute: int = 10
    notification_lock_seconds: int = 120
    notification_worker_batch_size: int = 25
    notification_max_retry_attempts: int = 4
    notification_max_batch_size: int = 100
    notification_processing_timeout_seconds: int = 30
    notification_delivery_timeout_seconds: int = 20

    notification_enabled: bool = False
    notification_low_levels_pct: list[int] = [50, 20, 10, 0]
    notification_high_levels_pct: list[int] = [80, 90, 100]
    notification_roles: list[str] = ["OWNER"]

    search_result_limit_max: int = 200
    search_query_timeout_seconds: int = 5
    report_query_timeout_seconds: int = 10
    historical_query_max_days: int = 366
    snapshot_max_payload_bytes: int = 65536

    enforce_https: bool = False

    @staticmethod
    def from_master_config() -> "Settings":
        cfg = load_master_config()
        s = Settings()
        jwt_secret = str(cfg.get("jwt_secret") or s.jwt_secret)
        if jwt_secret in ("CHANGE_ME_IN_INSTALLER", "dev-secret", ""):
            jwt_secret = secrets.token_urlsafe(48)
        s.jwt_secret = jwt_secret

        s.dev_backup_password = str(cfg.get("dev_backup_password") or s.dev_backup_password)

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
        s.smtp_host = str(cfg.get("smtp_host") or s.smtp_host)
        s.smtp_port = int(cfg.get("smtp_port") or s.smtp_port)
        s.smtp_username = str(cfg.get("smtp_username") or s.smtp_username)
        s.smtp_password = str(cfg.get("smtp_password") or s.smtp_password)
        s.smtp_from_email = str(cfg.get("smtp_from_email") or s.smtp_from_email)
        s.smtp_use_tls = bool(cfg.get("smtp_use_tls", s.smtp_use_tls))
        s.notification_email_stock = str(cfg.get("notification_email_stock") or s.notification_email_stock)
        s.notification_email_admin = str(cfg.get("notification_email_admin") or s.notification_email_admin)
        s.notification_email_accountant = str(cfg.get("notification_email_accountant") or s.notification_email_accountant)
        s.notification_email_owner = str(cfg.get("notification_email_owner") or s.notification_email_owner)
        s.notification_email_dev = str(cfg.get("notification_email_dev") or s.notification_email_dev)
        s.notification_lock_seconds = int(cfg.get("notification_lock_seconds") or s.notification_lock_seconds)
        s.notification_worker_batch_size = int(cfg.get("notification_worker_batch_size") or s.notification_worker_batch_size)
        s.notification_max_retry_attempts = int(cfg.get("notification_max_retry_attempts") or s.notification_max_retry_attempts)
        s.notification_max_batch_size = int(cfg.get("notification_max_batch_size") or s.notification_max_batch_size)
        s.notification_processing_timeout_seconds = int(
            cfg.get("notification_processing_timeout_seconds") or s.notification_processing_timeout_seconds
        )
        s.notification_delivery_timeout_seconds = int(
            cfg.get("notification_delivery_timeout_seconds") or s.notification_delivery_timeout_seconds
        )

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

        s.search_result_limit_max = int(cfg.get("search_result_limit_max") or s.search_result_limit_max)
        s.search_query_timeout_seconds = int(cfg.get("search_query_timeout_seconds") or s.search_query_timeout_seconds)
        s.report_query_timeout_seconds = int(cfg.get("report_query_timeout_seconds") or s.report_query_timeout_seconds)
        s.historical_query_max_days = int(cfg.get("historical_query_max_days") or s.historical_query_max_days)
        s.snapshot_max_payload_bytes = int(cfg.get("snapshot_max_payload_bytes") or s.snapshot_max_payload_bytes)

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
        ensure_local_data_layout()
        return f"sqlite+aiosqlite:///{app_db_path().resolve().as_posix()}"


settings = Settings.from_master_config()


def refresh_runtime_settings_from_master_config() -> None:
    updated = Settings.from_master_config()
    for field_name, value in updated.model_dump().items():
        setattr(settings, field_name, value)

