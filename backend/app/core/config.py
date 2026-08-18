from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "Mesa Quant Master"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_DOCS_ENABLED: bool = True

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_MAX_ENTRIES: int = 10000
    MAX_REQUEST_BODY_BYTES: int = 2097152
    SECURITY_HSTS_ENABLED: bool = False
    SECURITY_HSTS_MAX_AGE_SECONDS: int = 31536000
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Mesa Quant Master"
    SMTP_USE_TLS: bool = True
    SMTP_TIMEOUT_SECONDS: float = 10
    FRONTEND_PUBLIC_URL: str = "http://localhost:5173"
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    AUTH_EMAIL_REQUEST_COOLDOWN_SECONDS: int = 60
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
    # Recurso oficial "Taxas dos Títulos Ofertados pelo Tesouro Direto"
    # (Tesouro Nacional / Tesouro Transparente, CKAN público, sem
    # autenticação) -- confirmado vigente por auditoria direta (HTTP HEAD +
    # amostra de conteúdo) antes desta implementação. Não é segredo: pode
    # ficar como default público, permitindo que uma instalação padrão use
    # o fallback oficial sem exigir que o usuário descubra a URL
    # manualmente. Uma string vazia em .env continua desligando o fallback
    # (ver IndicatorResolverService._default_treasury_provider).
    TESOURO_TRANSPARENTE_DATASET_URL: str = (
        "https://www.tesourotransparente.gov.br/ckan/dataset/"
        "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
        "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/"
        "precotaxatesourodireto.csv"
    )
    TESOURO_TRANSPARENTE_CACHE_DIR: str = ".cache/tesouro_transparente"
    TESOURO_TRANSPARENTE_TIMEOUT_SECONDS: float = 30
    # ~40 MiB: o recurso vigente tem ~13,7 MiB; a margem suporta
    # crescimento razoável do histórico diário sem permitir download
    # ilimitado.
    TESOURO_TRANSPARENTE_MAX_DOWNLOAD_BYTES: int = 41943040
    # 6h: dataset publicado diariamente e treasury_rate/current_price têm
    # só 2 dias de validade no catálogo -- 24h deixaria o cache defasado
    # por quase um dia antes de revalidar. Revalidação é condicional
    # (ETag/Last-Modified, 304 sem redownload), então 6h não gera tráfego
    # desnecessário.
    TESOURO_TRANSPARENTE_CACHE_TTL_HOURS: int = 6
    CVM_CACHE_DIR: str = ".cache/cvm"
    CVM_TIMEOUT_SECONDS: float = 60
    CVM_MAX_DOWNLOAD_BYTES: int = 83886080
    CVM_MAX_UNCOMPRESSED_BYTES: int = 1073741824
    CVM_CACHE_TTL_HOURS: int = 24
    CVM_FII_CACHE_DIR: str = ".cache/cvm_fii"
    CVM_FII_TIMEOUT_SECONDS: float = 60
    CVM_FII_MAX_DOWNLOAD_BYTES: int = 41943040
    CVM_FII_MAX_UNCOMPRESSED_BYTES: int = 536870912
    CVM_FII_CACHE_TTL_HOURS: int = 24
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5-mini"
    AI_AGENT_ENABLED: bool = False
    AI_AGENT_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=300)
    AI_AGENT_MAX_ITERATIONS: int = Field(default=6, ge=1, le=20)
    AI_AGENT_MAX_TOOL_CALLS: int = Field(default=8, ge=1, le=50)
    AI_AGENT_MAX_MESSAGE_LENGTH: int = Field(default=4000, ge=1, le=20000)
    AI_AGENT_MAX_COMPARE_ASSETS: int = Field(default=10, ge=2, le=50)
    AI_AGENT_MAX_OUTPUT_TOKENS: int = Field(default=1200, ge=1, le=10000)
    PORTFOLIO_UNIVERSE_MAX_ASSETS: int = Field(default=200, ge=1, le=2000)

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
