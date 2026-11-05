"""Órdenes de producción digitales y cola del taller (JOY-17 / US-09)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Cliente, HistorialEtapa, Orden, Producto, Usuario

router = APIRouter(prefix="/ordenes", tags=["ordenes"])

ETAPA_INICIAL = "en_cola"
ROLES_QUE_CREAN = ("asesor", "admin")


class OrdenIn(BaseModel):
    cliente_id: int
    producto_id: int | None = None
    descripcion: str = Field(max_length=1000)
    usuario_id: int | None = None  # asesor que la crea (aún no hay inicio de sesión)

    @field_validator("descripcion")
    @classmethod
    def descripcion_con_contenido(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("La descripción debe tener al menos 3 caracteres")
        return valor


class OrdenOut(BaseModel):
    id: int
    codigo: str
    cliente_id: int
    cliente: str | None
    producto_id: int | None
    producto: str | None
    descripcion: str
    etapa_actual: str
    acuse_pendiente: bool
    publicada_en: datetime | None
    creado_en: datetime | None


def nombre_de(cliente: Cliente | None) -> str | None:
    if cliente is None:
        return None
    return cliente.nombre_preferido or cliente.nombre_perfil or f"Cliente {cliente.id}"


def armar_salida(session: Session, orden: Orden) -> OrdenOut:
    producto = session.get(Producto, orden.producto_id) if orden.producto_id else None
    return OrdenOut(
        id=orden.id,
        codigo=f"OP-{orden.id:06d}",
        cliente_id=orden.cliente_id,
        cliente=nombre_de(session.get(Cliente, orden.cliente_id)),
        producto_id=orden.producto_id,
        producto=producto.nombre if producto else None,
        descripcion=orden.descripcion,
        etapa_actual=orden.etapa_actual,
        acuse_pendiente=orden.acuse_pendiente,
        publicada_en=orden.publicada_en,
        creado_en=orden.creado_en,
    )


@router.post("", response_model=OrdenOut, status_code=201)
def crear_orden(datos: OrdenIn, session: Session = Depends(get_session)):
    """Crea la orden y la publica de inmediato en la cola del taller con el acuse pendiente."""
    if session.get(Cliente, datos.cliente_id) is None:
        raise HTTPException(404, "El cliente no existe")
    if datos.producto_id is not None:
        producto = session.get(Producto, datos.producto_id)
        if producto is None or not producto.activo:
            raise HTTPException(404, "El producto no existe")
    if datos.usuario_id is not None:
        usuario = session.get(Usuario, datos.usuario_id)
        if usuario is None or not usuario.activo:
            raise HTTPException(404, "El usuario no existe")
        if usuario.rol not in ROLES_QUE_CREAN:
            raise HTTPException(422, "Solo un asesor puede crear órdenes")

    orden = Orden(
        cliente_id=datos.cliente_id,
        producto_id=datos.producto_id,
        descripcion=datos.descripcion,
        etapa_actual=ETAPA_INICIAL,
        acuse_pendiente=True,
        publicada_en=datetime.now(timezone.utc),
    )
    session.add(orden)
    session.flush()  # asigna el ID único
    session.add(
        HistorialEtapa(orden_id=orden.id, etapa=ETAPA_INICIAL, usuario_id=datos.usuario_id)
    )
    session.commit()
    session.refresh(orden)
    return armar_salida(session, orden)


@router.get("/cola", response_model=list[OrdenOut])
def cola_del_taller(session: Session = Depends(get_session)):
    """Órdenes esperando al taller, las más antiguas primero."""
    ordenes = session.scalars(
        select(Orden)
        .where(Orden.etapa_actual == ETAPA_INICIAL)
        .order_by(Orden.creado_en, Orden.id)
    ).all()
    return [armar_salida(session, o) for o in ordenes]


@router.get("/{orden_id}", response_model=OrdenOut)
def detalle_orden(orden_id: int, session: Session = Depends(get_session)):
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    return armar_salida(session, orden)


@router.post("/{orden_id}/acuse", response_model=OrdenOut)
def confirmar_acuse(orden_id: int, session: Session = Depends(get_session)):
    """El taller confirma que recibió la orden (quita el indicador de acuse pendiente)."""
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    if orden.acuse_pendiente:
        orden.acuse_pendiente = False
        session.commit()
        session.refresh(orden)
    return armar_salida(session, orden)
