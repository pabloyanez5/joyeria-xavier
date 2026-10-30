import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def get_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+pg8000://joyeria:cambia-esto@localhost:5432/joyeria",
    )
    return url.replace("postgresql://", "postgresql+pg8000://", 1)


class Base(DeclarativeBase):
    pass


engine = create_engine(get_database_url())
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def get_session():
    with SessionLocal() as session:
        yield session