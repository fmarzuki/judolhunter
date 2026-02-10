"""Application configuration with environment-based database switching."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory
BASE_PATH = Path(__file__).parent.parent


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./judolhunter.db"
    # For MySQL: "mysql+aiomysql://user:password@localhost:3306/judolhunter"

    # Security
    SECRET_KEY: str = "change-this-in-production-use-openssl-rand-hex-32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Application
    APP_NAME: str = "Judol Hunter"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ["*"]

    # Rate Limiting
    REDIS_URL: str = "redis://localhost:6379/0"
    # If Redis is unavailable, falls back to in-memory

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:8000", "http://localhost:3000"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Scanning
    SCAN_TIMEOUT: float = 15.0
    MAX_URLS_PER_SCAN_UNAUTH: int = 5
    MAX_DOMAINS_PER_WEEK_UNAUTH: int = 2
    MAX_URLS_PER_SCAN_FREE: int = 20
    MAX_DOMAINS_PER_WEEK_FREE: int = 3

    # Upload/Export limits
    MAX_EXPORT_ROWS: int = 10000

    # Paths
    BASE_PATH: Path = BASE_PATH

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_type(self) -> Literal["sqlite", "mysql"]:
        """Detect database type from DATABASE_URL."""
        if self.DATABASE_URL.startswith("sqlite"):
            return "sqlite"
        elif self.DATABASE_URL.startswith("mysql"):
            return "mysql"
        return "sqlite"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.DEBUG and self.DATABASE_URL.startswith("mysql")


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
