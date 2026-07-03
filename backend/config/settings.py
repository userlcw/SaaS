"""应用全局配置：从环境变量 / .env 读取。"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：<repo>/python/
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
# 后端目录：<repo>/python/backend/
BACKEND_ROOT: Path = Path(__file__).resolve().parents[1]
# 日志目录：<repo>/python/logs/
LOG_DIR: Path = PROJECT_ROOT / "logs"
# 后端运行时数据目录（SQLite 数据库、缓存等）：<repo>/python/backend/data/
DATA_DIR: Path = BACKEND_ROOT / "data"


def _resolve_sqlite_url(url: str) -> str:
    """将 sqlite 相对 URL 归一化到 DATA_DIR，避免落到项目根目录。"""
    if not url.startswith("sqlite"):
        return url
    prefix, sep, rest = url.partition(":///")
    if not sep or not rest:
        return url
    # 已是绝对路径（Windows 盘符或以 / 开头）
    if len(rest) >= 2 and rest[1] == ":":
        return url
    if rest.startswith("/"):
        return url
    # sqlite:///./app.db 或 sqlite:///app.db → 归一到 DATA_DIR
    filename = Path(rest.lstrip("./")).name or "app.db"
    return f"{prefix}:///{(DATA_DIR / filename).as_posix()}"


class Settings(BaseSettings):
    """全局设置。"""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / "config" / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    app_name: str = "login-backend"
    app_env: str = "dev"
    api_v1_prefix: str = "/api/v1"

    # 服务监听（部署时覆盖，避免硬编码本地地址）
    host: str = "0.0.0.0"
    port: int = 8000

    # 安全
    secret_key: str = Field(default="please-change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "refresh_token"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # 登录失败限流（账号级）
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    # 登录失败限流（IP 级）
    ip_rate_limit_max: int = 20
    ip_rate_limit_window_seconds: int = 60
    ip_rate_limit_block_seconds: int = 300

    # 数据库
    database_url: str = "sqlite:///./app.db"

    # CORS
    cors_origins: str = "*"

    # ---------------- 邮件（SMTP） ----------------
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "Docker Ops Console"
    smtp_from_addr: str = ""

    # 邮箱验证码
    email_code_length: int = 6
    email_code_ttl_seconds: int = 600
    email_code_resend_seconds: int = 60
    email_code_max_per_hour: int = 5

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def smtp_from(self) -> str:
        return self.smtp_from_addr or self.smtp_user

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.cors_origins or self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # 归一化 sqlite URL 到 DATA_DIR
    s.database_url = _resolve_sqlite_url(s.database_url)
    return s


settings = get_settings()

# 确保关键目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
