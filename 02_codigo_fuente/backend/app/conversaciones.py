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

from app.acceso import requiere
from app.agente import intereses
from app.clientes import nombre_para_saludar
from app.db import get_session
from app.meta_envio import Enviador, ErrorMeta
from app.models import (
    Cliente, Conversacion, Mensaje, Orden, TransicionConversacion, Usuario,
)
from app.ordenes import codigo_de_orden, nombre_de
from app.webhook import get_enviador

# Las conversaciones y la ficha del cliente son solo para el asesor (y el rol admin).
puede_atender = requiere("asesor")

router = APIRouter(
    prefix="/conversaciones", tags=["conversaciones"], dependencies=[Depends(puede_atender)]
)

ESTADOS = ("activa", "escalada", "cerrada")
VISTA_PREVIA = 90  # caracteres del último mensaje que se muestran en la lista

# (clave en el interés del cliente, etiqueta que ve el asesor)
CAMPOS_FICHA = intereses.ETIQUETAS


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
    # Solo en respuestas del agente: modelo | respaldo | reglas | menu | guardrail.
    origen: str | None = None
    usuario: str | None = None  # asesor que escribió el mensaje desde el panel
    contenido: str
    creado_en: datetime | None


class TransicionOut(BaseModel):
    estado_anterior: str | None
    estado_nuevo: str
    creado_en: datetime | None


class OrdenSugerida(BaseModel):
    cliente_id: int
    descripcion: str


class InteresOut(BaseModel):
    """Una joya que le interesa al cliente, con sus propios datos (JOY-80)."""

    numero: int
    activo: bool  # de esta se está hablando
    titulo: str
    datos: list[ItemFicha]
    descripcion_de_orden: str
    # Si ya se creó la orden de esta joya: su código y etapa. Así no se ofrece crearla de nuevo.
    orden: str | None = None
    etapa_de_la_orden: str | None = None


class ConversacionDetalle(ConversacionResumen):
    ficha: list[ItemFicha]  # la joya de la que se está hablando
    datos_del_cliente: list[ItemFicha]  # nombre preferido, canal e intención detectada
    intereses: list[InteresOut]
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


def _nombre_de_usuario(session: Session, usuario_id: int | None) -> str | None:
    usuario = session.get(Usuario, usuario_id) if usuario_id else None
    return usuario.nombre if usuario else None


def _autor(m: Mensaje) -> str:
    if m.direccion == "entrante":
        return "cliente"
    return m.autor or "agente"


def _items(interes: dict) -> list[ItemFicha]:
    return [
        ItemFicha(etiqueta=etiqueta, valor=str(interes[clave]))
        for clave, etiqueta in CAMPOS_FICHA
        if interes.get(clave)
    ]


def _intereses_de(cliente: Cliente) -> list[dict]:
    """Las joyas que le interesan. La talla de una ficha antigua se suma a su única joya."""
    guardados = intereses.lista(cliente.contexto_cualificacion)
    if cliente.talla and not any(i.get("talla") for i in guardados):
        if not guardados:
            guardados = [{}]
        if len(guardados) == 1:
            guardados[0]["talla"] = cliente.talla
    return guardados


def _ficha(cliente: Cliente) -> list[ItemFicha]:
    guardados = _intereses_de(cliente)
    if not guardados:
        return []
    indice = intereses.indice_activo(cliente.contexto_cualificacion)
    return _items(guardados[indice if indice is not None else -1])


def _datos_del_cliente(cliente: Cliente, c: Conversacion) -> list[ItemFicha]:
    contexto = cliente.contexto_cualificacion or {}
    nombre = nombre_para_saludar(cliente)
    datos = []
    if nombre:
        sufijo = "" if cliente.nombre_preferido else " (de su perfil, sin confirmar)"
        datos.append(ItemFicha(etiqueta="Nombre preferido", valor=nombre + sufijo))
    datos.append(ItemFicha(etiqueta="Canal", valor=c.canal))
    if contexto.get("intencion"):
        datos.append(ItemFicha(etiqueta="Intención detectada", valor=str(contexto["intencion"])))
    return datos


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


def _ordenes_de_los_intereses(
    session: Session, cliente: Cliente, c: Conversacion, guardados: list[dict]
) -> list[Orden | None]:
    """La orden de cada joya de la ficha, o None si todavía no se crea."""
    propias = session.scalars(
        select(Orden).where(Orden.cliente_id == cliente.id).order_by(Orden.id)
    ).all()
    por_id = {o.id: o for o in propias}
    encontradas = [por_id.get(i.get("orden_id")) for i in guardados]
    # Órdenes creadas antes de que la ficha guardara la orden: se reconocen por la descripción
    # que arma el panel ("Joya: Aretes; …. Origen: conversación #15 por whatsapp.").
    usadas = {o.id for o in encontradas if o}
    origen = f"conversación #{c.id} por".casefold()
    for n, interes in enumerate(guardados):
        if encontradas[n] or intereses.con_orden(interes) or not interes.get("categoria"):
            continue
        joya = f"joya: {interes['categoria']}".casefold()
        for o in propias:
            texto = o.descripcion.casefold()
            if o.id not in usadas and origen in texto and joya in texto:
                encontradas[n] = o
                usadas.add(o.id)
                break
    return encontradas


def _intereses_out(session: Session, cliente: Cliente, c: Conversacion) -> list[InteresOut]:
    guardados = _intereses_de(cliente)
    actual = intereses.indice_activo(cliente.contexto_cualificacion)
    if actual is None and guardados:
        actual = len(guardados) - 1
    ordenes = _ordenes_de_los_intereses(session, cliente, c, guardados)
    return [
        InteresOut(
            numero=n + 1,
            activo=n == actual,
            titulo=intereses.titulo(interes),
            datos=_items(interes),
            descripcion_de_orden=_descripcion_de_orden(c, _items(interes)),
            orden=codigo_de_orden(orden.id) if orden else None,
            etapa_de_la_orden=orden.etapa_actual if orden else None,
        )
        for n, (interes, orden) in enumerate(zip(guardados, ordenes))
    ]


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
        datos_del_cliente=_datos_del_cliente(cliente, c),
        intereses=_intereses_out(session, cliente, c),
        motivo_escalamiento=motivo if c.estado == "escalada" and motivo else None,
        historial=[
            MensajeOut(
                id=m.id,
                autor=_autor(m),
                origen=m.origen,
                usuario=_nombre_de_usuario(session, m.usuario_id),
                contenido=m.contenido,
                creado_en=m.creado_en,
            )
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
    usuario: Usuario = Depends(puede_atender),
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
            usuario_id=usuario.id,
        )
    )
    if conversacion.estado == "activa":
        _cambiar_estado(session, conversacion, "escalada")
    conversacion.actualizado_en = func.now()
    session.commit()
    return _detalle(session, conversacion)
