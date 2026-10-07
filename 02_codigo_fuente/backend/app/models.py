from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("canal", "id_canal", name="uq_clientes_canal_id_canal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(String(20))  # whatsapp | instagram | facebook
    id_canal: Mapped[str] = mapped_column(String(100))
    nombre_perfil: Mapped[str | None] = mapped_column(String(200))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )