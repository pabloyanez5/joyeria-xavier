"""Conversaciones vistas desde el panel del asesor (JOY-62).

El asesor ve qué conversaciones atiende el agente y cuáles fueron escaladas, con la ficha de
contexto que el agente fue recolectando (joya, material, talla, ocasión, presupuesto). Desde
aquí puede responder al cliente por su canal, reactivar el agente o cerrar la conversación, y
crear la orden de producción con los datos ya recolectados en lugar de partir de un formulario
vacío.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.meta_envio import Enviador, ErrorMeta
from app.models import Cliente, Conversacion, Mensaje, Orden, TransicionConversacion
from app.ordenes import nombre_de
from app.webhook import get_enviador

router = APIRouter(prefix="/conversaciones", tags=["conversaciones"])

ESTADOS = ("activa", "escalada", "cerrada")
VISTA_PREVIA = 90  # caracteres del último mensaje que se muestran en la lista

# (clave en el contexto del cliente, etiqueta que ve el asesor)
CAMPOS_FICHA = (
    ("categoria", "Joya"),
    ("material", "Material"),
    ("quilataje", "Quilataje"),
    ("talla", "Talla"),
    ("ocasion", "Ocasión"),
    ("presupuesto", "Presupuesto"),
)


class ItemFicha(BaseModel):
    etiqueta: str
    valor: str


class ConversacionResumen(BaseModel):
    id: int
    cliente_id: int
    cliente: str | None
    canal: str
    estado: str
    actualizado_en: datetime | None
    ultimo_mensaje: str | None
    ultimo_autor: str | None
    total_mensajes: int
    ordenes_activas: int


class MensajeOut(BaseModel):
    id: int
    autor: str  # cliente | agente | asesor
    contenido: str
    creado_en: datetime | None


class TransicionOut(BaseModel):
    estado_anterior: str | None
    estado_nuevo: str
    creado_en: datetime | None


class OrdenSugerida(BaseModel):
    cliente_id: int
    descripcion: str


class ConversacionDetalle(ConversacionResumen):
    ficha: list[ItemFicha]
    motivo_escalamiento: str | None
    historial: list[MensajeOut]
    transiciones: list[TransicionOut]
    orden_sugerida: OrdenSugerida


class RespuestaAsesorIn(BaseModel):
    texto: str = Field(max_length=1000)

    @field_validator("texto")
    @classmethod
    def con_contenido(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El mensaje no puede estar vacío")
        return valor


def _autor(m: Mensaje) -> str:
    if m.direccion == "entrante":
        return "cliente"
    return m.autor or "agente"


def _ficha(cliente: Cliente) -> list[ItemFicha]:
    contexto = dict(cliente.contexto_cualificacion or {})
    if cliente.talla:
        contexto["talla"] = cliente.talla
    return [
        ItemFicha(etiqueta=etiqueta, valor=str(contexto[clave]))
        for clave, etiqueta in CAMPOS_FICHA
        if contexto.get(clave)
    ]


def _resumen(session: Session, c: Conversacion) -> ConversacionResumen:
    cliente = session.get(Cliente, c.cliente_id)
    ultimo = session.scalar(
        select(Mensaje).where(Mensaje.conversacion_id == c.id).order_by(Mensaje.id.desc())
    )
    total = session.scalar(
        select(func.count()).select_from(Mensaje).where(Mensaje.conversacion_id == c.id)
    )
    activas = session.scalar(
        select(func.count())
        .select_from(Orden)
        .where(Orden.cliente_id == c.cliente_id, Orden.etapa_actual != "entregada")
    )
    vista = ultimo.contenido.replace("\n", " ") if ultimo else None
    if vista and len(vista) > VISTA_PREVIA:
        vista = vista[: VISTA_PREVIA - 1].rstrip() + "…"
    return ConversacionResumen(
        id=c.id,
        cliente_id=c.cliente_id,
        cliente=nombre_de(cliente),
        canal=c.canal,
        estado=c.estado,
        actualizado_en=c.actualizado_en,
        ultimo_mensaje=vista,
        ultimo_autor=_autor(ultimo) if ultimo else None,
        total_mensajes=total or 0,
        ordenes_activas=activas or 0,
    )


def _descripcion_de_orden(c: Conversacion, ficha: list[ItemFicha]) -> str:
    datos = "; ".join(f"{i.etiqueta}: {i.valor}" for i in ficha)
    origen = f"Origen: conversación #{c.id} por {c.canal}."
    texto = f"{datos}. {origen}" if datos else origen
    return texto[:1000]


def _detalle(session: Session, c: Conversacion) -> ConversacionDetalle:
    cliente = session.get(Cliente, c.cliente_id)
    ficha = _ficha(cliente)
    mensajes = session.scalars(
        select(Mensaje).where(Mensaje.conversacion_id == c.id).order_by(Mensaje.id)
    ).all()
    transiciones = session.scalars(
        select(TransicionConversacion)
        .where(TransicionConversacion.conversacion_id == c.id)
        .order_by(TransicionConversacion.id)
    ).all()
    motivo = (cliente.contexto_cualificacion or {}).get("motivo_escalamiento")
    return ConversacionDetalle(
        **_resumen(session, c).model_dump(),
        ficha=ficha,
        motivo_escalamiento=motivo if c.estado == "escalada" and motivo else None,
        historial=[
            MensajeOut(id=m.id, autor=_autor(m), contenido=m.contenido, creado_en=m.creado_en)
            for m in mensajes
        ],
        transiciones=[
            TransicionOut(
                estado_anterior=t.estado_anterior, estado_nuevo=t.estado_nuevo, creado_en=t.creado_en
            )
            for t in transiciones
        ],
        orden_sugerida=OrdenSugerida(
            cliente_id=c.cliente_id, descripcion=_descripcion_de_orden(c, ficha)
        ),
    )


def _buscar(session: Session, conversacion_id: int) -> Conversacion:
    conversacion = session.get(Conversacion, conversacion_id)
    if conversacion is None:
        raise HTTPException(404, "La conversación no existe")
    return conversacion


def _cambiar_estado(session: Session, c: Conversacion, nuevo: str) -> None:
    session.add(
        TransicionConversacion(
            conversacion_id=c.id, estado_anterior=c.estado, estado_nuevo=nuevo
        )
    )
    c.estado = nuevo


@router.get("", response_model=list[ConversacionResumen])
def listar_conversaciones(
    estado: str | None = Query(None, description="activa, escalada o cerrada"),
    limite: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """Las escaladas primero (esperan a una persona) y luego las más recientes."""
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(422, f"El estado debe ser uno de: {', '.join(ESTADOS)}")
    consulta = select(Conversacion)
    if estado:
        consulta = consulta.where(Conversacion.estado == estado)
    prioridad = case((Conversacion.estado == "escalada", 0), (Conversacion.estado == "activa", 1), else_=2)
    conversaciones = session.scalars(
        consulta.order_by(prioridad, Conversacion.actualizado_en.desc(), Conversacion.id.desc()).limit(limite)
    ).all()
    return [_resumen(session, c) for c in conversaciones]


@router.get("/{conversacion_id}", response_model=ConversacionDetalle)
def detalle_conversacion(conversacion_id: int, session: Session = Depends(get_session)):
    return _detalle(session, _buscar(session, conversacion_id))


@router.post("/{conversacion_id}/reactivar", response_model=ConversacionDetalle)
def reactivar_agente(conversacion_id: int, session: Session = Depends(get_session)):
    """Devuelve la conversación al agente después de que el asesor la atendió."""
    conversacion = _buscar(session, conversacion_id)
    if conversacion.estado != "escalada":
        raise HTTPException(409, "Solo se puede reactivar una conversación escalada")
    _cambiar_estado(session, conversacion, "activa")
    cliente = session.get(Cliente, conversacion.cliente_id)
    contexto = dict(cliente.contexto_cualificacion or {})
    if contexto.pop("motivo_escalamiento", None) is not None:
        cliente.contexto_cualificacion = contexto
    session.commit()
    return _detalle(session, conversacion)


@router.post("/{conversacion_id}/cerrar", response_model=ConversacionDetalle)
def cerrar_conversacion(conversacion_id: int, session: Session = Depends(get_session)):
    """Termina la conversación; si el cliente vuelve a escribir, empieza una nueva."""
    conversacion = _buscar(session, conversacion_id)
    if conversacion.estado == "cerrada":
        raise HTTPException(409, "La conversación ya está cerrada")
    _cambiar_estado(session, conversacion, "cerrada")
    session.commit()
    return _detalle(session, conversacion)


@router.post("/{conversacion_id}/responder", response_model=ConversacionDetalle)
def responder_como_asesor(
    conversacion_id: int,
    datos: RespuestaAsesorIn,
    session: Session = Depends(get_session),
    enviador: Enviador | None = Depends(get_enviador),
):
    """El asesor escribe al cliente por su mismo canal. Al intervenir una persona, el agente
    deja de responder en esa conversación hasta que se reactive."""
    conversacion = _buscar(session, conversacion_id)
    if conversacion.estado == "cerrada":
        raise HTTPException(409, "La conversación está cerrada")
    if enviador is None:
        raise HTTPException(503, "El envío de mensajes no está configurado")
    cliente = session.get(Cliente, conversacion.cliente_id)
    try:
        enviado = enviador.enviar(conversacion.canal, cliente.id_canal, datos.texto)
    except ErrorMeta as e:
        raise HTTPException(502, f"No se pudo enviar el mensaje: {str(e)[:200]}") from e
    if not enviado:
        raise HTTPException(422, f"El envío por {conversacion.canal} todavía no está disponible")
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="saliente",
            contenido=datos.texto,
            autor="asesor",
        )
    )
    if conversacion.estado == "activa":
        _cambiar_estado(session, conversacion, "escalada")
    conversacion.actualizado_en = func.now()
    session.commit()
    return _detalle(session, conversacion)
