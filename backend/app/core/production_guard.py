"""Validação de configuração para evitar implantação insegura por engano."""

from sqlalchemy.engine import make_url


def assert_production_ready(settings) -> None:
    if settings.APP_ENV.strip().lower() != "production":
        return
    errors = []
    database = make_url(settings.DATABASE_URL)
    if not database.drivername.startswith("postgresql"):
        errors.append("DATABASE_URL deve ser PostgreSQL persistente em produção")
    # Conexão externa ao Neon deve exigir criptografia TLS; nunca aceite
    # string simplificada sem sslmode ao lidar com carteira financeira.
    if (database.host or "").endswith(".neon.tech") and database.query.get("sslmode") not in {
        "require", "verify-ca", "verify-full"
    }:
        errors.append("Banco Neon exige sslmode=require (ou validação TLS superior)")
    secret = settings.SECRET_KEY.strip()
    if len(secret) < 32 or secret in {"change-me-in-local-env", "secret", "development"}:
        errors.append("SECRET_KEY deve ser uma chave forte de pelo menos 32 caracteres")
    if settings.DEBUG or settings.API_DOCS_ENABLED:
        errors.append("DEBUG e API_DOCS_ENABLED devem estar desativados")
    if not settings.SECURITY_HSTS_ENABLED:
        errors.append("SECURITY_HSTS_ENABLED deve estar ativado")
    if settings.SMTP_HOST and not settings.SMTP_USE_TLS:
        errors.append("SMTP_USE_TLS deve estar ativado para SMTP em produção")
    if settings.AUTH_PUBLIC_REGISTRATION_ENABLED:
        errors.append("AUTH_PUBLIC_REGISTRATION_ENABLED deve estar desativado em produção privada")
    if not settings.FRONTEND_ORIGINS or any(
        not origin.startswith("https://") or origin.endswith("/")
        for origin in settings.FRONTEND_ORIGINS
    ):
        errors.append("FRONTEND_ORIGINS deve conter somente origens HTTPS exatas")
    if errors:
        raise RuntimeError("Configuração de produção insegura: " + "; ".join(errors))
