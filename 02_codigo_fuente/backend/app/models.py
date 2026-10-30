from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (UniqueConstraint("canal", "id_canal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(String(20))
    id_canal: Mapped[str] = mapped_column(String(100))
    nombre_perfil: Mapped[str | None] = mapped_column(String(200))
    nombre_preferido: Mapped[str | None] = mapped_column(String(100))
    talla: Mapped[str | None] = mapped_column(String(20))
    contexto_cualificacion: Mapped[dict | None] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint("rol IN ('asesor', 'taller', 'admin')", name="ck_usuarios_rol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    rol: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Conversacion(Base):
    __tablename__ = "conversaciones"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('activa', 'escalada', 'cerrada')", name="ck_conversaciones_estado"
        ),
        Index("ix_conversaciones_cliente_id", "cliente_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    canal: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), default="activa")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TransicionConversacion(Base):
    __tablename__ = "transiciones_conversacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversacion_id: Mapped[int] = mapped_column(
        ForeignKey("conversaciones.id"), index=True
    )
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    estado_nuevo: Mapped[str] = mapped_column(String(20))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Mensaje(Base):
    __tablename__ = "mensajes"
    __table_args__ = (
        CheckConstraint(
            "direccion IN ('entrante', 'saliente')", name="ck_mensajes_direccion"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversacion_id: Mapped[int] = mapped_column(
        ForeignKey("conversaciones.id"), index=True
    )
    direccion: Mapped[str] = mapped_column(String(10))
    contenido: Mapped[str] = mapped_column(Text)
    id_externo: Mapped[str | None] = mapped_column(String(200), unique=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    categoria: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Precio(Base):
    __tablename__ = "precios"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    material: Mapped[str] = mapped_column(String(50))
    quilataje: Mapped[str | None] = mapped_column(String(10))
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)


class Orden(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    etapa_actual: Mapped[str] = mapped_column(String(50))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HistorialEtapa(Base):
    __tablename__ = "historial_etapas"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id"), index=True)
    etapa: Mapped[str] = mapped_column(String(50))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )