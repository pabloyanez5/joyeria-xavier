import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase


def get_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+pg8000://joyeria:cambia-esto@localhost:5432/joyeria",
    )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)
    return url


class Base(DeclarativeBase):
    pass


engine = create_engine(get_database_url())