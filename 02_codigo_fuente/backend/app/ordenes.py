"""Órdenes de producción digitales, pedidos y cola del taller (RF-03).

Flujo de una orden:

    por_verificar -> en_cola -> en_produccion -> terminada -> entregada

- El asesor crea la orden con los datos completos (JOY-79). Si el cliente encarga varias
  joyas, se crea una orden por joya y todas quedan unidas en un mismo pedido.
- La orden nace "por verificar": pasa a la cola del taller recién cuando el asesor registra
  el abono (JOY-22). Así al taller solo llegan pedidos reales.
- El taller confirma el recibo y avanza las etapas; el cliente recibe un aviso en cada una.
- El asesor puede corregir los datos de una orden, devolverla una etapa o cancelarla, siempre
  con un motivo que queda en el historial con su nombre (JOY-23). Nada se borra.
"""
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.acceso import requiere
from app.agente import intereses
from app.db import get_session
from app.meta_envio import Enviador, ErrorMeta
from app.models import (
    Cliente, Conversacion, HistorialEtapa, Mensaje, Orden, Pedido, Producto, Usuario,
)
from app.webhook import get_enviador

router = APIRouter(prefix="/ordenes", tags=["ordenes"])

ETAPAS = ("por_verificar", "en_cola", "en_produccion", "terminada", "entregada")
ETAPA_INICIAL = ETAPAS[0]
ETAPA_DE_COLA = "en_cola"
# La cancelación no es una etapa del proceso: la orden sale del flujo, pero no se borra.
CANCELADA = "cancelada"
ETAPAS_CON_CANCELADA = (*ETAPAS, CANCELADA)
# Hasta dónde se puede corregir una orden: terminada ya está hecha, entregada ya se fue.
SE_PUEDE_MODIFICAR = ("por_verificar", "en_cola", "en_produccion")
# Retroceso autorizado (corrige un avance por error): solo una etapa y dentro del taller.
RETROCESOS = {"en_produccion": "en_cola", "terminada": "en_produccion"}
MAX_JOYAS_POR_PEDIDO = 8
# Quién puede hacer qué (el rol admin pasa siempre). Dirección solo ve los indicadores.
puede_crear = requiere("asesor")
puede_ver = requiere("asesor", "taller")
puede_avanzar = requiere("taller")

# Aviso que recibe el cliente por su canal cuando la orden entra a cada etapa.
AVISOS_AL_CLIENTE = {
    "en_cola": (
        "Registramos tu abono. Tu orden {codigo} ya está confirmada y entró a la cola de "
        "nuestro taller."
    ),
    "en_produccion": "¡Buenas noticias! Tu orden {codigo} ya está en producción en nuestro taller.",
    "terminada": (
        "Tu orden {codigo} ya está terminada. Un asesor se pondrá en contacto contigo "
        "para coordinar la entrega."
    ),
    "entregada": (
        "Registramos la entrega de tu orden {codigo}. ¡Gracias por confiar en Joyería Xavier!"
    ),
    CANCELADA: (
        "Tu orden {codigo} fue cancelada. Si tienes alguna duda, escribe «asesor» y te "
        "atenderá una persona."
    ),
}

_TELEFONO = re.compile(r"^\+?\d{7,15}$")
Dinero = Decimal


def codigo_de_orden(orden_id: int) -> str:
    return f"OP-{orden_id:06d}"


def codigo_de_pedido(pedido_id: int | None) -> str | None:
    return f"PD-{pedido_id:06d}" if pedido_id else None


def _registrar_acuse(orden: Orden, usuario: Usuario) -> None:
    orden.acuse_pendiente = False
    orden.acuse_usuario_id = usuario.id
    orden.acuse_en = datetime.now(timezone.utc)


def _no_cancelada(orden: Orden) -> None:
    if orden.etapa_actual == CANCELADA:
        raise HTTPException(409, "La orden está cancelada")


def siguiente_etapa(etapa: str) -> str | None:
    """La etapa a la que el taller puede avanzar. De "por verificar" solo sale el asesor."""
    if etapa == ETAPA_INICIAL:
        return None
    try:
        posicion = ETAPAS.index(etapa)
    except ValueError:
        return None
    return ETAPAS[posicion + 1] if posicion + 1 < len(ETAPAS) else None


# --- datos de entrada ---

def _foto(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if not valor.lower().startswith(("https://", "http://")):
        raise ValueError("La foto de referencia debe ser un enlace que empiece con https://")
    return valor


class JoyaIn(BaseModel):
    """Lo que hay que saber de una joya para mandarla a producir."""

    producto_id: int | None = None
    descripcion: str = Field(max_length=1000)
    peso_gramos: Decimal = Field(gt=0, le=5000, max_digits=8, decimal_places=2)
    fecha_entrega_taller: date
    fecha_entrega_cliente: date
    total: Dinero = Field(gt=0, max_digits=10, decimal_places=2)
    abono: Dinero = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    foto_referencia_url: str | None = Field(None, max_length=500)
    # Número de la joya en la ficha del cliente de la que sale esta orden (se marca como pedida).
    interes: int | None = Field(None, ge=1, le=intereses.MAXIMO)

    @field_validator("descripcion")
    @classmethod
    def descripcion_con_contenido(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("La descripción debe tener al menos 3 caracteres")
        return valor

    @field_validator("foto_referencia_url")
    @classmethod
    def foto_con_direccion_web(cls, valor: str | None) -> str | None:
        return _foto(valor)

    @model_validator(mode="after")
    def fechas_y_abono_coherentes(self):
        if self.fecha_entrega_cliente < self.fecha_entrega_taller:
            raise ValueError("La entrega al cliente no puede ser antes que la entrega al taller")
        if self.abono > self.total:
            raise ValueError("El abono no puede ser mayor que el total")
        return self


class ContactoIn(BaseModel):
    """Datos del cliente que el asesor confirma antes de crear la orden."""

    cliente_id: int
    nombre_completo: str = Field(max_length=150)
    telefono: str = Field(max_length=30)

    @field_validator("nombre_completo")
    @classmethod
    def nombre_con_contenido(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if len(valor) < 3:
            raise ValueError("Escribe el nombre completo del cliente")
        return valor

    @field_validator("telefono")
    @classmethod
    def telefono_valido(cls, valor: str) -> str:
        limpio = re.sub(r"[\s().-]", "", valor)
        if not _TELEFONO.match(limpio):
            raise ValueError("El teléfono debe tener entre 7 y 15 dígitos")
        return limpio


class OrdenIn(ContactoIn, JoyaIn):
    pass


class PedidoIn(ContactoIn):
    joyas: list[JoyaIn] = Field(min_length=1, max_length=MAX_JOYAS_POR_PEDIDO)


class MotivoIn(BaseModel):
    motivo: str = Field(max_length=500)

    @field_validator("motivo")
    @classmethod
    def motivo_claro(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if len(valor) < 5:
            raise ValueError("Escribe el motivo (al menos 5 caracteres)")
        return valor


class CancelacionIn(MotivoIn):
    avisar_al_cliente: bool = True


class ModificacionIn(MotivoIn):
    """Solo los datos que cambian; lo que no se envía queda como estaba."""

    descripcion: str | None = Field(None, max_length=1000)
    peso_gramos: Decimal | None = Field(None, gt=0, le=5000, max_digits=8, decimal_places=2)
    fecha_entrega_taller: date | None = None
    fecha_entrega_cliente: date | None = None
    total: Dinero | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    foto_referencia_url: str | None = Field(None, max_length=500)

    @field_validator("descripcion")
    @classmethod
    def descripcion_con_contenido(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("La descripción debe tener al menos 3 caracteres")
        return valor

    @field_validator("foto_referencia_url")
    @classmethod
    def foto_con_direccion_web(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return _foto(valor) or ""  # "" = quitar la foto


class VerificacionIn(BaseModel):
    abono: Dinero = Field(gt=0, max_digits=10, decimal_places=2)
    avisar_al_cliente: bool = True


class CambioEtapaIn(BaseModel):
    etapa: str
    avisar_al_cliente: bool = True


# --- datos de salida ---

class OrdenOut(BaseModel):
    id: int
    codigo: str
    pedido_id: int | None = None
    pedido: str | None = None  # código del pedido que agrupa varias órdenes
    cliente_id: int
    cliente: str | None
    producto_id: int | None
    producto: str | None
    descripcion: str
    etapa_actual: str
    peso_gramos: Decimal | None = None
    fecha_entrega_taller: date | None = None
    fecha_entrega_cliente: date | None = None
    total: Dinero | None = None
    abono: Dinero | None = None
    saldo: Dinero | None = None
    foto_referencia_url: str | None = None
    verificada_por: str | None = None  # asesor que registró el abono
    verificada_en: datetime | None = None
    acuse_pendiente: bool
    acuse_por: str | None = None  # usuario del taller que confirmó el recibo
    acuse_en: datetime | None = None
    publicada_en: datetime | None
    creado_en: datetime | None
    siguiente_etapa: str | None = None
    etapa_anterior: str | None = None  # a dónde la puede devolver el asesor (JOY-23)
    ultimo_cambio: str | None = None  # la última modificación, retroceso o cancelación


class PedidoOut(BaseModel):
    id: int
    codigo: str
    cliente_id: int
    total: Dinero
    abono: Dinero
    saldo: Dinero
    ordenes: list[OrdenOut]


class CambioEtapaOut(OrdenOut):
    aviso_al_cliente: str  # enviado | no_enviado | omitido
    detalle_aviso: str | None = None


class EtapaRegistrada(BaseModel):
    etapa: str
    tipo: str = "etapa"  # etapa | modificacion | retroceso | cancelacion
    nota: str | None = None
    usuario: str | None
    creado_en: datetime | None


def nombre_de(cliente: Cliente | None) -> str | None:
    if cliente is None:
        return None
    return (
        cliente.nombre_preferido
        or cliente.nombre_completo
        or cliente.nombre_perfil
        or f"Cliente {cliente.id}"
    )


def _nombre_de_usuario(session: Session, usuario_id: int | None) -> str | None:
    usuario = session.get(Usuario, usuario_id) if usuario_id else None
    return usuario.nombre if usuario else None


def armar_salida(session: Session, orden: Orden) -> OrdenOut:
    producto = session.get(Producto, orden.producto_id) if orden.producto_id else None
    saldo = None
    if orden.total is not None:
        saldo = orden.total - (orden.abono or Decimal("0"))
    return OrdenOut(
        id=orden.id,
        codigo=codigo_de_orden(orden.id),
        pedido_id=orden.pedido_id,
        pedido=codigo_de_pedido(orden.pedido_id),
        cliente_id=orden.cliente_id,
        cliente=nombre_de(session.get(Cliente, orden.cliente_id)),
        producto_id=orden.producto_id,
        producto=producto.nombre if producto else None,
        descripcion=orden.descripcion,
        etapa_actual=orden.etapa_actual,
        peso_gramos=orden.peso_gramos,
        fecha_entrega_taller=orden.fecha_entrega_taller,
        fecha_entrega_cliente=orden.fecha_entrega_cliente,
        total=orden.total,
        abono=orden.abono,
        saldo=saldo,
        foto_referencia_url=orden.foto_referencia_url,
        verificada_por=_nombre_de_usuario(session, orden.verificada_usuario_id),
        verificada_en=orden.verificada_en,
        acuse_pendiente=orden.acuse_pendiente,
        acuse_por=_nombre_de_usuario(session, orden.acuse_usuario_id),
        acuse_en=orden.acuse_en,
        publicada_en=orden.publicada_en,
        creado_en=orden.creado_en,
        siguiente_etapa=siguiente_etapa(orden.etapa_actual),
        etapa_anterior=RETROCESOS.get(orden.etapa_actual),
        ultimo_cambio=_ultimo_cambio(session, orden),
    )


_TIPO_DE_CAMBIO = {
    "modificacion": "Modificada",
    "retroceso": "Devuelta",
    "cancelacion": "Cancelada",
}


def _ultimo_cambio(session: Session, orden: Orden) -> str | None:
    registro = session.scalar(
        select(HistorialEtapa)
        .where(HistorialEtapa.orden_id == orden.id, HistorialEtapa.tipo != "etapa")
        .order_by(HistorialEtapa.id.desc())
    )
    if registro is None:
        return None
    quien = _nombre_de_usuario(session, registro.usuario_id)
    return f"{_TIPO_DE_CAMBIO.get(registro.tipo, registro.tipo)}" + (
        f" por {quien}" if quien else ""
    ) + f": {registro.nota}"


# --- crear ---

def _cliente_con_contacto(session: Session, datos: ContactoIn) -> Cliente:
    cliente = session.get(Cliente, datos.cliente_id)
    if cliente is None:
        raise HTTPException(404, "El cliente no existe")
    cliente.nombre_completo = datos.nombre_completo
    cliente.telefono = datos.telefono
    return cliente


def _nueva_orden(
    session: Session, cliente: Cliente, joya: JoyaIn, usuario: Usuario, pedido: Pedido | None
) -> Orden:
    if joya.producto_id is not None:
        producto = session.get(Producto, joya.producto_id)
        if producto is None or not producto.activo:
            raise HTTPException(404, "El producto no existe")
    orden = Orden(
        cliente_id=cliente.id,
        producto_id=joya.producto_id,
        pedido_id=pedido.id if pedido else None,
        descripcion=joya.descripcion,
        etapa_actual=ETAPA_INICIAL,
        peso_gramos=joya.peso_gramos,
        fecha_entrega_taller=joya.fecha_entrega_taller,
        fecha_entrega_cliente=joya.fecha_entrega_cliente,
        total=joya.total,
        abono=joya.abono,
        foto_referencia_url=joya.foto_referencia_url,
        acuse_pendiente=True,
    )
    session.add(orden)
    session.flush()  # asigna el ID único
    session.add(HistorialEtapa(orden_id=orden.id, etapa=ETAPA_INICIAL, usuario_id=usuario.id))
    return orden


def _marcar_en_la_ficha(cliente: Cliente, creadas: list[tuple[JoyaIn, Orden]]) -> None:
    """Las joyas de la ficha que ya tienen orden dejan de ofrecerse para crear otra."""
    pedidas = {joya.interes: orden.id for joya, orden in creadas if joya.interes}
    if pedidas:
        # Se reasigna un dict nuevo para que SQLAlchemy detecte el cambio en el JSON.
        cliente.contexto_cualificacion = intereses.marcar_pedidas(
            cliente.contexto_cualificacion, pedidas
        )


@router.post("", response_model=OrdenOut, status_code=201)
def crear_orden(
    datos: OrdenIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea la orden de una joya. Queda por verificar hasta que se registre el abono."""
    cliente = _cliente_con_contacto(session, datos)
    orden = _nueva_orden(session, cliente, datos, usuario, None)
    _marcar_en_la_ficha(cliente, [(datos, orden)])
    session.commit()
    session.refresh(orden)
    return armar_salida(session, orden)


@router.post("/pedido", response_model=PedidoOut, status_code=201)
def crear_pedido(
    datos: PedidoIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(puede_crear),
):
    """Crea una orden por cada joya y las une en un pedido. O se crean todas o ninguna."""
    cliente = _cliente_con_contacto(session, datos)
    pedido = Pedido(cliente_id=cliente.id, usuario_id=usuario.id)
    session.add(pedido)
    session.flush()
    ordenes = [_nueva_orden(session, cliente, joya, usuario, pedido) for joya in datos.joyas]
    _marcar_en_la_ficha(cliente, list(zip(datos.joyas, ordenes)))
    session.commit()
    return _pedido_out(session, pedido, ordenes)


def _pedido_out(session: Session, pedido: Pedido, ordenes: list[Orden]) -> PedidoOut:
    total = sum((o.total or Decimal("0") for o in ordenes), Decimal("0"))
    abono = sum((o.abono or Decimal("0") for o in ordenes), Decimal("0"))
    return PedidoOut(
        id=pedido.id,
        codigo=codigo_de_pedido(pedido.id),
        cliente_id=pedido.cliente_id,
        total=total,
        abono=abono,
        saldo=total - abono,
        ordenes=[armar_salida(session, o) for o in ordenes],
    )


# --- consultar ---

_CODIGO = re.compile(r"^(?:(OP|PD)-?)?0*(\d{1,9})$", re.IGNORECASE)


def _filtro_de_texto(consulta, texto: str):
    """Busca por código de orden (OP-000012 o 12), de pedido (PD-000003), cliente o detalle."""
    texto = " ".join(texto.split())
    codigo = _CODIGO.match(texto)
    if codigo:
        prefijo, numero = (codigo.group(1) or "").upper(), int(codigo.group(2))
        return consulta.where(Orden.pedido_id == numero if prefijo == "PD" else Orden.id == numero)
    patron = f"%{texto.lower()}%"
    return consulta.join(Cliente, Cliente.id == Orden.cliente_id).where(
        or_(
            func.lower(Orden.descripcion).like(patron),
            func.lower(Cliente.nombre_completo).like(patron),
            func.lower(Cliente.nombre_preferido).like(patron),
            func.lower(Cliente.nombre_perfil).like(patron),
        )
    )


@router.get("", response_model=list[OrdenOut], dependencies=[Depends(puede_ver)])
def listar_ordenes(
    etapa: str | None = Query(None, description=", ".join(ETAPAS_CON_CANCELADA)),
    q: str | None = Query(None, max_length=100, description="Código, cliente o detalle"),
    desde: date | None = Query(None, description="Creadas desde esta fecha (AAAA-MM-DD)"),
    hasta: date | None = Query(None, description="Creadas hasta esta fecha, inclusive"),
    limite: int = Query(300, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """Órdenes más recientes primero, con filtros que se combinan (JOY-83)."""
    if etapa is not None and etapa not in ETAPAS_CON_CANCELADA:
        raise HTTPException(
            422, f"La etapa debe ser una de: {', '.join(ETAPAS_CON_CANCELADA)}"
        )
    if desde and hasta and hasta < desde:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial")
    consulta = select(Orden)
    if etapa:
        consulta = consulta.where(Orden.etapa_actual == etapa)
    if q and q.strip():
        consulta = _filtro_de_texto(consulta, q)
    if desde:
        consulta = consulta.where(Orden.creado_en >= datetime.combine(desde, time.min, timezone.utc))
    if hasta:
        fin = datetime.combine(hasta + timedelta(days=1), time.min, timezone.utc)
        consulta = consulta.where(Orden.creado_en < fin)
    ordenes = session.scalars(consulta.order_by(Orden.id.desc()).limit(limite)).all()
    return [armar_salida(session, o) for o in ordenes]


@router.get("/cola", response_model=list[OrdenOut], dependencies=[Depends(puede_ver)])
def cola_del_taller(session: Session = Depends(get_session)):
    """Órdenes ya verificadas que esperan al taller, las más antiguas primero."""
    ordenes = session.scalars(
        select(Orden)
        .where(Orden.etapa_actual == ETAPA_DE_COLA)
        .order_by(Orden.publicada_en, Orden.id)
    ).all()
    return [armar_salida(session, o) for o in ordenes]


@router.get("/pedido/{pedido_id}", response_model=PedidoOut, dependencies=[Depends(puede_ver)])
def detalle_pedido(pedido_id: int, session: Session = Depends(get_session)):
    pedido = session.get(Pedido, pedido_id)
    if pedido is None:
        raise HTTPException(404, "El pedido no existe")
    ordenes = session.scalars(
        select(Orden).where(Orden.pedido_id == pedido_id).order_by(Orden.id)
    ).all()
    return _pedido_out(session, pedido, list(ordenes))


@router.get("/{orden_id}", response_model=OrdenOut, dependencies=[Depends(puede_ver)])
def detalle_orden(orden_id: int, session: Session = Depends(get_session)):
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    return armar_salida(session, orden)


@router.get(
    "/{orden_id}/historial",
    response_model=list[EtapaRegistrada],
    dependencies=[Depends(puede_ver)],
)
def historial_de_etapas(orden_id: int, session: Session = Depends(get_session)):
    """Trazabilidad: cada etapa por la que pasó la orden, con quién la registró y cuándo."""
    if session.get(Orden, orden_id) is None:
        raise HTTPException(404, "La orden no existe")
    registros = session.scalars(
        select(HistorialEtapa).where(HistorialEtapa.orden_id == orden_id).order_by(HistorialEtapa.id)
    ).all()
    return [
        EtapaRegistrada(
            etapa=r.etapa,
            tipo=r.tipo or "etapa",
            nota=r.nota,
            usuario=_nombre_de_usuario(session, r.usuario_id),
            creado_en=r.creado_en,
        )
        for r in registros
    ]


# --- avanzar ---

def _avisar_al_cliente(
    session: Session, orden: Orden, enviador: Enviador | None
) -> tuple[str, str | None]:
    """Manda el aviso de la nueva etapa; si falla, la orden igual queda avanzada."""
    if enviador is None:
        return "omitido", "El envío de mensajes no está configurado"
    cliente = session.get(Cliente, orden.cliente_id)
    texto = AVISOS_AL_CLIENTE[orden.etapa_actual].format(codigo=codigo_de_orden(orden.id))
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


def _con_aviso(
    session: Session, orden: Orden, enviador: Enviador | None, avisar: bool, motivo_sin_aviso: str
) -> CambioEtapaOut:
    aviso, detalle = "omitido", motivo_sin_aviso
    if avisar:
        aviso, detalle = _avisar_al_cliente(session, orden, enviador)
    return CambioEtapaOut(
        **armar_salida(session, orden).model_dump(), aviso_al_cliente=aviso, detalle_aviso=detalle
    )


@router.post("/{orden_id}/verificar", response_model=CambioEtapaOut)
def verificar_abono(
    orden_id: int,
    datos: VerificacionIn,
    session: Session = Depends(get_session),
    enviador: Enviador | None = Depends(get_enviador),
    usuario: Usuario = Depends(puede_crear),
):
    """El asesor registra el abono recibido; recién entonces la orden entra a la cola del taller.

    El abono es un dato de referencia: el sistema no cobra ni emite comprobantes."""
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    _no_cancelada(orden)
    if orden.etapa_actual != ETAPA_INICIAL:
        raise HTTPException(409, "La orden ya fue verificada")
    if orden.total is not None and datos.abono > orden.total:
        raise HTTPException(422, "El abono no puede ser mayor que el total")

    ahora = datetime.now(timezone.utc)
    orden.abono = datos.abono
    orden.verificada_usuario_id = usuario.id
    orden.verificada_en = ahora
    orden.etapa_actual = ETAPA_DE_COLA
    orden.publicada_en = ahora
    orden.acuse_pendiente = True
    session.add(HistorialEtapa(orden_id=orden.id, etapa=ETAPA_DE_COLA, usuario_id=usuario.id))
    session.commit()
    session.refresh(orden)
    return _con_aviso(
        session, orden, enviador, datos.avisar_al_cliente, "El asesor decidió no avisar al cliente"
    )


@router.post("/{orden_id}/acuse", response_model=OrdenOut)
def confirmar_acuse(
    orden_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(puede_avanzar),
):
    """El taller confirma que recibió la orden; queda registrado quién y cuándo."""
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    _no_cancelada(orden)
    if orden.etapa_actual == ETAPA_INICIAL:
        raise HTTPException(409, "La orden todavía espera la verificación del abono")
    if orden.acuse_pendiente:
        _registrar_acuse(orden, usuario)
        session.commit()
        session.refresh(orden)
    return armar_salida(session, orden)


@router.post("/{orden_id}/etapa", response_model=CambioEtapaOut)
def cambiar_etapa(
    orden_id: int,
    datos: CambioEtapaIn,
    session: Session = Depends(get_session),
    enviador: Enviador | None = Depends(get_enviador),
    usuario: Usuario = Depends(puede_avanzar),
):
    """El taller avanza la orden a la etapa siguiente y el cliente recibe el aviso por su canal.

    Solo se avanza de una etapa a la siguiente para que el historial sea fiel al proceso.
    Salir de la cola cuenta como acuse de recibo del taller."""
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    if datos.etapa not in ETAPAS:
        raise HTTPException(422, f"La etapa debe ser una de: {', '.join(ETAPAS)}")
    _no_cancelada(orden)
    if orden.etapa_actual == ETAPA_INICIAL:
        raise HTTPException(409, "La orden todavía espera la verificación del abono")
    esperada = siguiente_etapa(orden.etapa_actual)
    if esperada is None:
        raise HTTPException(409, "La orden ya fue entregada")
    if datos.etapa != esperada:
        raise HTTPException(
            409, f"La orden está en {orden.etapa_actual}; la etapa siguiente es {esperada}"
        )

    orden.etapa_actual = datos.etapa
    if orden.acuse_pendiente:
        _registrar_acuse(orden, usuario)
    session.add(HistorialEtapa(orden_id=orden.id, etapa=datos.etapa, usuario_id=usuario.id))
    session.commit()
    session.refresh(orden)
    return _con_aviso(
        session, orden, enviador, datos.avisar_al_cliente, "El taller decidió no avisar al cliente"
    )


# --- corregir, devolver y cancelar (JOY-23) ---

def _orden_o_404(session: Session, orden_id: int) -> Orden:
    orden = session.get(Orden, orden_id)
    if orden is None:
        raise HTTPException(404, "La orden no existe")
    return orden


def _dinero_texto(valor) -> str:
    return "—" if valor is None else f"${Decimal(valor):,.2f}"


def _fecha_texto(valor) -> str:
    return "—" if valor is None else f"{valor:%d/%m/%Y}"


# (campo, cómo se llama para el asesor, cómo se muestra el valor)
_CAMPOS_MODIFICABLES = (
    ("descripcion", "Descripción", lambda v: v or "—"),
    ("peso_gramos", "Peso", lambda v: "—" if v is None else f"{Decimal(v).normalize():f} g"),
    ("fecha_entrega_taller", "Entrega al taller", _fecha_texto),
    ("fecha_entrega_cliente", "Entrega al cliente", _fecha_texto),
    ("total", "Total", _dinero_texto),
    ("foto_referencia_url", "Foto de referencia", lambda v: v or "sin foto"),
)


@router.patch("/{orden_id}", response_model=OrdenOut)
def modificar_orden(
    orden_id: int,
    datos: ModificacionIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(puede_crear),
):
    """El asesor corrige los datos de la orden mientras no esté terminada.

    Cada cambio queda en el historial con el valor anterior, el nuevo, el motivo y quién lo hizo.
    Si el taller ya la había recibido, vuelve a quedar con acuse pendiente para que vea el cambio."""
    orden = _orden_o_404(session, orden_id)
    _no_cancelada(orden)
    if orden.etapa_actual not in SE_PUEDE_MODIFICAR:
        raise HTTPException(409, "Una orden terminada o entregada ya no se puede modificar")

    nuevos = datos.model_dump(exclude_unset=True, exclude={"motivo"})
    if "foto_referencia_url" in nuevos:
        nuevos["foto_referencia_url"] = nuevos["foto_referencia_url"] or None
    cambios = []
    for campo, etiqueta, mostrar in _CAMPOS_MODIFICABLES:
        if campo not in nuevos or nuevos[campo] is None and campo != "foto_referencia_url":
            continue
        antes, despues = getattr(orden, campo), nuevos[campo]
        if antes == despues:
            continue
        cambios.append((campo, despues, f"{etiqueta}: {mostrar(antes)} → {mostrar(despues)}"))
    if not cambios:
        raise HTTPException(422, "No hay ningún dato distinto para guardar")

    taller = {c: v for c, v, _ in cambios}
    entrega_taller = taller.get("fecha_entrega_taller", orden.fecha_entrega_taller)
    entrega_cliente = taller.get("fecha_entrega_cliente", orden.fecha_entrega_cliente)
    if entrega_taller and entrega_cliente and entrega_cliente < entrega_taller:
        raise HTTPException(422, "La entrega al cliente no puede ser antes que la entrega al taller")
    total = taller.get("total", orden.total)
    if total is not None and orden.abono and orden.abono > total:
        raise HTTPException(422, "El total no puede quedar por debajo del abono ya registrado")

    for campo, valor, _ in cambios:
        setattr(orden, campo, valor)
    if orden.etapa_actual != ETAPA_INICIAL and not orden.acuse_pendiente:
        # El taller trabaja con lo que recibió: tiene que confirmar que vio la corrección.
        orden.acuse_pendiente = True
        orden.acuse_usuario_id = None
        orden.acuse_en = None
    detalle = "; ".join(texto for _, _, texto in cambios)
    session.add(
        HistorialEtapa(
            orden_id=orden.id,
            etapa=orden.etapa_actual,
            usuario_id=usuario.id,
            tipo="modificacion",
            nota=f"{detalle}. Motivo: {datos.motivo}"[:2000],
        )
    )
    session.commit()
    session.refresh(orden)
    return armar_salida(session, orden)


@router.post("/{orden_id}/retroceder", response_model=OrdenOut)
def retroceder_etapa(
    orden_id: int,
    datos: MotivoIn,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(puede_crear),
):
    """Retroceso autorizado: el asesor devuelve la orden una etapa (por ejemplo, si el taller la
    avanzó por error). Queda en el historial con el motivo; al cliente no se le avisa."""
    orden = _orden_o_404(session, orden_id)
    _no_cancelada(orden)
    anterior = RETROCESOS.get(orden.etapa_actual)
    if anterior is None:
        raise HTTPException(
            409, "Solo se puede devolver una orden en producción o terminada, una etapa a la vez"
        )
    orden.etapa_actual = anterior
    session.add(
        HistorialEtapa(
            orden_id=orden.id,
            etapa=anterior,
            usuario_id=usuario.id,
            tipo="retroceso",
            nota=datos.motivo,
        )
    )
    session.commit()
    session.refresh(orden)
    return armar_salida(session, orden)


@router.post("/{orden_id}/cancelar", response_model=CambioEtapaOut)
def cancelar_orden(
    orden_id: int,
    datos: CancelacionIn,
    session: Session = Depends(get_session),
    enviador: Enviador | None = Depends(get_enviador),
    usuario: Usuario = Depends(puede_crear),
):
    """El asesor cancela una orden que aún no se entrega. No se borra: sale del flujo del taller
    y conserva todo su historial. La joya vuelve a quedar disponible en la ficha del cliente."""
    orden = _orden_o_404(session, orden_id)
    _no_cancelada(orden)
    if orden.etapa_actual == "entregada":
        raise HTTPException(409, "Una orden entregada no se puede cancelar")
    orden.etapa_actual = CANCELADA
    orden.acuse_pendiente = False
    session.add(
        HistorialEtapa(
            orden_id=orden.id,
            etapa=CANCELADA,
            usuario_id=usuario.id,
            tipo="cancelacion",
            nota=datos.motivo,
        )
    )
    cliente = session.get(Cliente, orden.cliente_id)
    cliente.contexto_cualificacion = intereses.desmarcar(cliente.contexto_cualificacion, orden.id)
    session.commit()
    session.refresh(orden)
    return _con_aviso(
        session, orden, enviador, datos.avisar_al_cliente, "El asesor decidió no avisar al cliente"
    )
