"""
Conexión a base de datos.
- Producción (Railway): PostgreSQL via DATABASE_URL
- Desarrollo local: SQLite (data/valuex.db)
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()

def _get_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        os.makedirs("data", exist_ok=True)
        url = "sqlite:///data/valuex.db"
        logger.warning("DATABASE_URL no configurada — usando SQLite local")
    return url

_url = _get_url()
_engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in _url else {},
)
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def init_db():
    """Crea todas las tablas si no existen."""
    from src.db import models  # noqa: F401
    Base.metadata.create_all(bind=_engine)
    logger.info("Base de datos inicializada (%s)", _url.split("@")[-1] if "@" in _url else _url)


def get_session():
    """Genera una sesión de DB (usar con context manager)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
