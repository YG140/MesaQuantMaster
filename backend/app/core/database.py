from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


_is_memory_sqlite = settings.DATABASE_URL == "sqlite:///:memory:"
_is_postgres = settings.DATABASE_URL.startswith(("postgresql://", "postgresql+"))
# Neon Free suspende a compute quando ocioso: conexões antigas morrem.
# pool_pre_ping + tamanho pequeno evitam conexão quebrada e consumo
# desnecessário de conexões em um banco serverless gratuito.
_connection_options = {
    "pool_pre_ping": True,
    **(
        {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        if _is_memory_sqlite else {}
    ),
    **(
        {
            "connect_args": {"connect_timeout": 12},
            "pool_size": 2,
            "max_overflow": 1,
            "pool_timeout": 15,
            "pool_recycle": 300,
        }
        if _is_postgres else {}
    ),
}
engine = create_engine(settings.DATABASE_URL, **_connection_options)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
