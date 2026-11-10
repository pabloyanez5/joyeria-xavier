import fakeredis
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.cache import CacheIdentidad
from app.db import Base


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


@pytest.fixture
def cache():
    return CacheIdentidad(fakeredis.FakeRedis(decode_responses=True))

@pytest.fixture(autouse=True)
def sin_modelo_real(monkeypatch):
    """Ninguna prueba debe llamar a Gemini aunque haya GEMINI_API_KEY en el entorno."""
    from app.agente.rutas import get_modelo_chat

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_modelo_chat.cache_clear()


@pytest.fixture(autouse=True)
def sin_credenciales_de_meta(monkeypatch):
    """Ninguna prueba debe mandar mensajes reales a Meta aunque haya variables en el entorno."""
    for nombre in ("META_ACCESS_TOKEN", "META_PHONE_NUMBER_ID", "META_APP_SECRET", "META_PAGE_ID", "META_PAGE_ACCESS_TOKEN"):
        monkeypatch.delenv(nombre, raising=False)


@pytest.fixture(autouse=True)
def sin_esperas_de_red(monkeypatch):
    """Los reintentos de envío no deben frenar las pruebas."""
    from app import meta_envio

    monkeypatch.setattr(meta_envio.time, "sleep", lambda s: None)
