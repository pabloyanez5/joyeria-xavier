from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index,
    Numeric, String, Text, UniqueConstraint, func, true,
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
    # Datos de contacto que confirma el asesor al crear una orden (no los pide el agente).
    nombre_completo: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(30))
    talla: Mapped[str | None] = mapped_column(String(20))
    contexto_cualificacion: Mapped[dict | None] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Usuario(Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "rol IN ('asesor', 'taller', 'direccion', 'admin')", name="ck_usuarios_rol"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    rol: Mapped[str] = mapped_column(String(20))
    # Clave cifrada (PBKDF2); None = el usuario todavía no puede iniciar sesión.
    clave_hash: Mapped[str | None] = mapped_column(String(255))
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
    # Quién escribió un mensaje saliente: None = el agente; "asesor" = una persona desde el panel.
    autor: Mapped[str | None] = mapped_column(String(20))
    # Asesor que escribió el mensaje desde el panel (solo cuando autor = "asesor").
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    # Qué redactó una respuesta del agente: modelo | respaldo | reglas | menu | guardrail.
    origen: Mapped[str | None] = mapped_column(String(20))
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
    # Insumos de la cotización por fórmula: peso de la pieza y mano de obra del taller.
    peso_gramos: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    mano_obra: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    imagen_url: Mapped[str | None] = mapped_column(String(500))


class TarifaMaterial(Base):
    """Precio por gramo de un material (y quilataje), con historial por fecha de vigencia."""

    __tablename__ = "tarifas_material"

    id: Mapped[int] = mapped_column(primary_key=True)
    material: Mapped[str] = mapped_column(String(50))
    quilataje: Mapped[str | None] = mapped_column(String(10))
    precio_gramo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)


class Precio(Base):
    __tablename__ = "precios"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"), index=True)
    material: Mapped[str] = mapped_column(String(50))
    quilataje: Mapped[str | None] = mapped_column(String(10))
    precio: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    vigente_desde: Mapped[date] = mapped_column(Date)


class Pedido(Base):
    """Agrupa las órdenes que un cliente encarga juntas (una orden por joya)."""

    __tablename__ = "pedidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Orden(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"))
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedidos.id"), index=True)
    descripcion: Mapped[str] = mapped_column(Text)
    etapa_actual: Mapped[str] = mapped_column(String(50))
    # Datos de la orden (RF-03). Son None solo en órdenes anteriores a JOY-79.
    peso_gramos: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fecha_entrega_taller: Mapped[date | None] = mapped_column(Date)
    fecha_entrega_cliente: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    abono: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    foto_referencia_url: Mapped[str | None] = mapped_column(String(500))
    # Verificación del abono: quién la registró y cuándo. Recién ahí pasa a la cola del taller.
    verificada_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    verificada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cola del taller: la orden se publica al crearse y queda con el acuse pendiente
    # hasta que el taller confirma que la recibió.
    acuse_pendiente: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    publicada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Acuse de recibo del taller: quién lo confirmó y cuándo.
    acuse_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    acuse_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    # etapa (avance normal) | modificacion | retroceso | cancelacion (JOY-23)
    tipo: Mapped[str] = mapped_column(String(20), default="etapa", server_default="etapa")
    # Qué cambió y por qué (obligatorio en modificaciones, retrocesos y cancelaciones).
    nota: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )