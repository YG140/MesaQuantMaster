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
    AUTH_PUBLIC_REGISTRATION_ENABLED: bool = True
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
    # APIs externas opcionais, apenas no backend. Nunca expor ao frontend.
    COINGECKO_DEMO_API_KEY: str = ""
    TWELVEDATA_API_KEY: str = ""
    # SEC EDGAR requer identificação real do solicitante; sem ela a checagem fica indisponível.
    # Exemplo: "MesaQuantMaster contato@seudominio.com". Nunca usar contato fictício.
    SEC_USER_AGENT: str = ""
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
    # Fonte oficial B3 (COTAHIST) para fechamento/histórico não ajustado --
    # confirmado vigente por auditoria direta (HTTP HEAD real, sem
    # autenticação) antes desta implementação. Layout público "PUBLIC
    # INFORMATION" (b3.com.br). Ver B3_EOD_BASE_URL abaixo para o arquivo
    # diário (COTAHIST_D<DDMMAAAA>.ZIP) usado como fallback de fechamento
    # recente, e B3_HISTORICAL_BASE_URL para o arquivo anual
    # (COTAHIST_A<AAAA>.ZIP) usado para histórico multi-ano.
    B3_COTAHIST_BASE_URL: str = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
    B3_CACHE_DIR: str = ".cache/b3"
    B3_TIMEOUT_SECONDS: float = 60
    # ~2 MiB: o arquivo diário observado tem ~0,5 MiB; a margem suporta
    # pregões de maior volume sem permitir download ilimitado.
    B3_DAILY_MAX_DOWNLOAD_BYTES: int = 2097152
    B3_DAILY_MAX_UNCOMPRESSED_BYTES: int = 20971520
    # ~100 MiB: o arquivo anual observado tem ~85 MiB.
    B3_ANNUAL_MAX_DOWNLOAD_BYTES: int = 104857600
    B3_ANNUAL_MAX_UNCOMPRESSED_BYTES: int = 1073741824
    # 20h: um único pregão por dia útil -- folga generosa sobre a janela de
    # publicação noturna do arquivo diário, sem redownload a cada request.
    B3_CACHE_TTL_HOURS: int = 20
    # BVBG.186 (EquitiesSimplifiedPriceReport) e BVBG.028 (InstrumentReport)
    # são produtos do "Legacy Channel" da B3 (UP2DATA), que a documentação
    # oficial (b3.com.br/en_us/market-data-and-indices/data-services/
    # up2data/available-data/) descreve como exigindo "contracted access" --
    # nenhuma URL pública determinística e estável foi confirmada durante a
    # auditoria (ver relatório). Strings vazias (default) mantêm os
    # adaptadores B3DailyPriceSource/B3InstrumentRegistrySource
    # estruturalmente prontos (parser testado com fixtures do schema
    # oficial), mas retornando NOT_CONFIGURED em vez de simular suporte.
    # Preencher aqui SOMENTE se uma URL pública real for confirmada, ou via
    # variável de ambiente local -- nunca um valor inventado.
    B3_BVBG186_URL: str = ""
    B3_BVBG028_URL: str = ""
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
