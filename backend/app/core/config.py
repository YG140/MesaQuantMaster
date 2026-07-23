from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "Mesa Quant Master"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    BRAPI_BASE_URL: str = "https://brapi.dev"
    BRAPI_API_KEY: str = ""
    BRAPI_TIMEOUT_SECONDS: float = 10
    BRAPI_QUOTE_CACHE_SECONDS: int = 60
    BRAPI_SEARCH_CACHE_SECONDS: int = 600
    BRAPI_PROFILE_CACHE_SECONDS: int = 3600
    TESOURO_TRANSPARENTE_DATASET_URL: str = ""
    CVM_CACHE_DIR: str = ".cache/cvm"
    CVM_TIMEOUT_SECONDS: float = 60
    CVM_MAX_DOWNLOAD_BYTES: int = 83886080
    CVM_MAX_UNCOMPRESSED_BYTES: int = 1073741824
    CVM_CACHE_TTL_HOURS: int = 24

    @field_validator("FRONTEND_ORIGINS", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
