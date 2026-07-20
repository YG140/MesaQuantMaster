import importlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.backtesting import router as backtesting_router
from app.api.brokerages import router as brokerages_router
from app.api.users import router as users_router
from app.api.assets import router as assets_router
from app.api.operations import router as operations_router
from app.api.portfolio import router as portfolio_router
from app.api.dashboard import router as dashboard_router
from app.api.market import router as market_router
from app.api.watchlist import router as watchlist_router
from app.api.order_simulator import router as order_simulator_router
from app.api.orders import router as orders_router
from app.api.alerts import router as alerts_router
from app.api.scanner import router as scanner_router
from app.api.risk import router as risk_router
from app.api.strategy import router as strategy_router
from app.api.intelligence import router as intelligence_router

from app.core.config import settings
from app.core.database import Base, engine
from app.core.sqlite_compat import ensure_sqlite_compat_schema

importlib.import_module("app.models")

Base.metadata.create_all(bind=engine)
ensure_sqlite_compat_schema(engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
Mesa Quant Master

Plataforma profissional para:

• Gestão Inteligente de Carteira
• Dashboard Quantitativo
• Home Broker Inteligente
• Scanner Quantitativo
• Risk Engine
• Strategy Engine
• IA Quant Advisor
• Backtesting
• Integração com Corretoras
""",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get(
    "/",
    tags=["Sistema"],
)
def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "online",
    }


@app.get(
    "/health",
    tags=["Sistema"],
)
def health():
    return {
        "status": "healthy",
    }


# ===========================
# Rotas
# ===========================

app.include_router(auth_router)

app.include_router(users_router)

app.include_router(assets_router)

app.include_router(operations_router)

app.include_router(brokerages_router)

app.include_router(portfolio_router)

app.include_router(dashboard_router)

app.include_router(market_router)

app.include_router(watchlist_router)

app.include_router(order_simulator_router)

app.include_router(orders_router)

app.include_router(alerts_router)

app.include_router(scanner_router)

app.include_router(risk_router)

app.include_router(strategy_router)

app.include_router(backtesting_router)

app.include_router(intelligence_router)
