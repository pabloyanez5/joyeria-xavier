"""Órdenes de producción digitales y cola del taller (JOY-17 / US-09)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.meta_envio import Enviador, ErrorMeta
from app.models import (
    Cliente, Conversacion, HistorialEtapa, Mensaje, Orden, Producto, Usuario,
)
from app.webhook import get_enviador

router = APIRouter(prefix="/ordenes", tags=["ordenes"])

ETAPAS = ("en_cola", "en_produccion", "terminada", "entregada")
ETAPA_INICIAL = ETAPAS[0]
ROLES_QUE_CREAN = ("asesor", "admin")
ROLES_QUE_AVANZAN = ("taller", "admin")

# Aviso que recibe el cliente por su canal cuando la orden entra a cada etapa.
AVISOS_AL_CLIENTE = {
    "en_produccion": "¡Buenas noticias! Tu orden {codigo} ya está en producción en nuestro taller.",
    "terminada": (
        "Tu orden {codigo} ya está terminada. Un asesor se pondrá en contacto contigo "
        "para coordinar la entrega."
    ),
    "entregada": (
        "Registramos la entrega de tu orden {codigo}. ¡Gracias por confiar en Joyería Xavier!"
    ),
}


def siguiente_etapa(etapa: str) -> str | None:
    try:
        posicion = ETAPAS.index(etapa)
    except ValueError:
        return None
    return ETAPAS[posicion + 1] if posicion + 1 < len(ETAPAS) else None


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
    siguiente_etapa: str | None = None


class CambioEtapaIn(BaseModel):
    etapa: str
    usuario_id: int | None = None  # quien la avanza (aún no hay inicio de sesión)
    avisar_al_cliente: bool = True


class CambioEtapaOut(OrdenOut):
    aviso_al_cliente: str  # enviado | no_enviado | omitido
    detalle_aviso: str | None = None


class EtapaRegistrada(BaseModel):
    etapa: str
    usuario: str | None
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
        siguiente_etapa=siguiente_etapa(orden.etapa_actual),
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


@router.get("", response_model=list[OrdenOut])
def listar_ordenes(
    etapa: str | None = Query(None, description="en_cola, en_produccion, terminada o entregada"),
    limite: int = Query(100, ge=1, le=300),
    session: Session = Depends(get_session),
):
    """Órdenes más recientes primero; el tablero del taller las agrupa por etapa."""
    if etapa is not None and etapa not in ETAPAS:
        raise HTTPException(422, f"La etapa debe ser una de: {', '.join(ETAPAS)}")
    consulta = select(Orden)
    if etapa:
        consulta = consulta.where(Orden.etapa_actual == etapa)
    ordenes = session.scalars(consulta.order_by(Orden.id.desc()).limit(limite)).all()
    return [armar_salida(session, o) for o in ordenes]


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


@router.get("/{orden_id}/historial", response_model=list[EtapaRegistrada])
def historial_de_etapas(orden_id: int, session: Session = Depends(get_session)):
    """Trazabilidad: cada etapa por la que pasó la orden, con quién la registró y cuándo."""
    if session.get(Orden, orden_id) is None:
        raise HTTPException(404, "La orden no existe")
    registros = session.scalars(
        select(HistorialEtapa).where(HistorialEtapa.orden_id == orden_id).order_by(HistorialEtapa.id)
    ).all()
    salida = []
    for r in registros:
        usuario = session.get(Usuario, r.usuario_id) if r.usuario_id else None
        salida.append(
            EtapaRegistrada(etapa=r.etapa, usuario=usuario.nombre if usuario else None, creado_en=r.creado_en)
        )
    return salida


def _avisar_al_cliente(
    session: Session, orden: Orden, enviador: Enviador | None
) -> tuple[str, str | None]:
    """Manda el aviso de la nueva etapa; si falla, la orden igual queda avanzada."""
    if enviador is None:
        return "omitido", "El envío de mensajes no está configurado"
    cliente = session.get(Cliente, orden.cliente_id)
    texto = AVISOS_AL_CLIENTE[orden.etapa_actual].format(codigo=f"OP-{orden.id:06d}")
    try:
        enviado = enviador.enviar(cliente.canal, cliente.id_canal, texto)
    except ErrorMeta as e:
        return "no_enviado", str(e)[:200]
    if not enviado:
        return "omitido", f"El envío por {cliente.canal} todavía no está disponible"
    abierta = session.scalar(
        select(Conversacion)
        .where(
            Conversacion.cliente_id == cliente.id,
            Conversacion.canal == cliente.canal,
            Conversacion.estado.in_(("activa", "escalada")),
        )
        .order_by(Conversacion.id.desc())
    )
    if abierta is not None:  # el aviso queda en el historial que ve el asesor
        session.add(
            Mensaje(conversacion_id=abierta.id, direccion="saliente", contenido=texto, autor="sistema")
        )
        session.commit()
    return "enviado", None


@router.post("/{orden_id}/etapa", response_model=CambioEtapaOut)
def cambiar_etapa(
    orden_id: int,
    datos: CambioEtapaIn,
    session: Session = Depends(get_session),
    enviador: Enviador | None = Depends(get_enviador),
):
    """El taller avanza la orden a la etapa siguiente y el cliente recibe el aviso por su canal.

    Solo se avanza de una etapa a la siguiente para que el historial sea fiel al proceso.
    Salir de la cola cuenta como acuse de recibo del taller."""
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    if datos.etapa not in ETAPAS:
        raise HTTPException(422, f"La etapa debe ser una de: {', '.join(ETAPAS)}")
    esperada = siguiente_etapa(orden.etapa_actual)
    if esperada is None:
        raise HTTPException(409, "La orden ya fue entregada")
    if datos.etapa != esperada:
        raise HTTPException(
            409, f"La orden está en {orden.etapa_actual}; la etapa siguiente es {esperada}"
        )
    if datos.usuario_id is not None:
        usuario = session.get(Usuario, datos.usuario_id)
        if usuario is None or not usuario.activo:
            raise HTTPException(404, "El usuario no existe")
        if usuario.rol not in ROLES_QUE_AVANZAN:
            raise HTTPException(422, "Solo el taller puede avanzar las etapas")

    orden.etapa_actual = datos.etapa
    orden.acuse_pendiente = False
    session.add(HistorialEtapa(orden_id=orden.id, etapa=datos.etapa, usuario_id=datos.usuario_id))
    session.commit()
    session.refresh(orden)

    aviso, detalle = "omitido", None
    if datos.avisar_al_cliente:
        aviso, detalle = _avisar_al_cliente(session, orden, enviador)
    else:
        detalle = "El taller decidió no avisar al cliente"
    return CambioEtapaOut(
        **armar_salida(session, orden).model_dump(), aviso_al_cliente=aviso, detalle_aviso=detalle
    )

