"""Atiende un mensaje entrante: guarda la conversación y arma la respuesta."""
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agente import contexto as ctx
from app.agente import menu
from app.agente.intenciones import clasificar
from app.agente.llm import ProveedorLLM
from app.cache import CacheIdentidad
from app.clientes import identificar_cliente
from app.mensajes import Saliente
from app.models import Cliente, Conversacion, Mensaje, TransicionConversacion

logger = logging.getLogger("joyeria.agente")


@dataclass
class RespuestaAgente:
    texto: str | None  # None = no se responde (la conversación la lleva un asesor)
    intencion: str | None
    conversacion_id: int
    cliente_id: int
    escalada: bool = False
    duplicado: bool = False
    cliente_nuevo: bool = False
    # Versión con botones, listas o fotos; `texto` es siempre la versión solo texto.
    mensajes: list[Saliente] | None = None


def url_web() -> str:
    return os.getenv("WEB_URL", "http://localhost:5173").rstrip("/")


def url_media() -> str:
    """Base pública de las fotos. WhatsApp pide una URL accesible desde internet."""
    return os.getenv("MEDIA_URL", "").strip().rstrip("/") or url_web()


def enlace_catalogo(contexto: dict) -> str:
    params = {k: contexto[k] for k in ("categoria", "material") if contexto.get(k)}
    return url_web() + (f"/?{urlencode(params)}" if params else "")


def _describir(contexto: dict) -> str | None:
    if not contexto.get("categoria"):
        return None
    texto = contexto["categoria"].lower()
    if contexto.get("material"):
        texto += f" de {contexto['material']}"
    return texto


def redactar(intencion: str, nombre: str | None, contexto: dict) -> tuple[str, bool]:
    """Devuelve (texto de respuesta, si hay que pasar la conversación a un asesor)."""
    coma = f", {nombre}" if nombre else ""
    enlace = enlace_catalogo(contexto)
    descripcion = _describir(contexto)
    if intencion == "saludo":
        if descripcion:
            return (
                f"¡Hola de nuevo{coma}! La última vez te interesaban {descripcion}. "
                "¿Quieres retomar eso o ver algo distinto?",
                False,
            )
        return (
            f"¡Hola{coma}! Soy el asistente virtual de Joyería Xavier. Puedo ayudarte a "
            "cotizar una joya, mostrarte el catálogo o comunicarte con un asesor. "
            "¿Qué te gustaría hacer?",
            False,
        )
    if intencion == "cotizar":
        if descripcion:
            return (
                f"Claro{coma}. Para {descripcion} puedes configurar tu joya y ver el "
                f"precio referencial al instante aquí: {enlace}",
                False,
            )
        return (
            f"Claro{coma}. Puedes configurar la joya y ver el precio referencial al "
            f"instante aquí: {enlace}\nSi me cuentas qué tipo de joya buscas (anillo, "
            "cadena, pulsera…), te llevo directo a esa sección.",
            False,
        )
    if intencion == "catalogo":
        return (
            f"Con gusto{coma}. Aquí puedes ver el catálogo y filtrar por categoría, "
            f"material y precio: {enlace}",
            False,
        )
    if intencion == "estado_pedido":
        return (
            "Por ahora no puedo consultar el estado de un pedido desde aquí. Te "
            "comunico con un asesor para que lo revise contigo; en breve te atenderá "
            "una persona.",
            True,
        )
    if intencion == "asesor":
        return (
            "Claro, te comunico con un asesor. En breve te atenderá una persona.",
            True,
        )
    if intencion == "despedida":
        return (
            f"¡Gracias a ti{coma}! Quedo atento por si necesitas algo más. "
            "¡Que tengas un excelente día!",
            False,
        )
    return (
        "No estoy seguro de haber entendido. Puedo ayudarte a cotizar una joya, "
        "mostrarte el catálogo o comunicarte con un asesor. ¿Qué prefieres?",
        False,
    )


def _conversacion_abierta(session: Session, cliente: Cliente, canal: str) -> Conversacion:
    conversacion = session.scalar(
        select(Conversacion)
        .where(
            Conversacion.cliente_id == cliente.id,
            Conversacion.canal == canal,
            Conversacion.estado.in_(("activa", "escalada")),
        )
        .order_by(Conversacion.id.desc())
    )
    if conversacion is None:
        conversacion = Conversacion(cliente_id=cliente.id, canal=canal, estado="activa")
        session.add(conversacion)
        session.flush()
        session.add(
            TransicionConversacion(
                conversacion_id=conversacion.id, estado_anterior=None, estado_nuevo="activa"
            )
        )
    return conversacion


def _recordar(cliente: Cliente, datos: ctx.Datos) -> None:
    if datos.nombre:
        cliente.nombre_preferido = datos.nombre
    if datos.talla:
        cliente.talla = datos.talla
    if datos.contexto:
        # Se reasigna un dict nuevo para que SQLAlchemy detecte el cambio en el JSON.
        cliente.contexto_cualificacion = {
            **(cliente.contexto_cualificacion or {}),
            **datos.contexto,
        }


def atender_mensaje(
    session: Session,
    cache: CacheIdentidad,
    canal: str,
    id_canal: str,
    texto: str,
    nombre: str | None = None,
    id_externo: str | None = None,
    proveedor: ProveedorLLM | None = None,
    accion: str | None = None,
    modelo=None,
) -> RespuestaAgente:
    """`modelo` es el modelo de chat de LangChain; si falta o falla, responde el motor de reglas."""
    if id_externo:
        previo = session.scalar(select(Mensaje).where(Mensaje.id_externo == id_externo))
        if previo is not None:
            conversacion = session.get(Conversacion, previo.conversacion_id)
            return RespuestaAgente(
                None, None, conversacion.id, conversacion.cliente_id, duplicado=True
            )

    cliente_id, creado = identificar_cliente(session, cache, canal, id_canal, nombre)
    cliente = session.get(Cliente, cliente_id)
    conversacion = _conversacion_abierta(session, cliente, canal)

    entrante = Mensaje(
        conversacion_id=conversacion.id,
        direccion="entrante",
        contenido=texto,
        id_externo=id_externo,
    )
    session.add(entrante)
    datos = ctx.extraer(texto)
    _recordar(cliente, datos)
    conversacion.actualizado_en = func.now()

    if conversacion.estado == "escalada":
        session.commit()
        return RespuestaAgente(
            None, None, conversacion.id, cliente.id, escalada=True, cliente_nuevo=creado
        )

    if accion:
        # El cliente tocó un botón o una opción de una lista: no hay texto que interpretar.
        categoria = menu.categoria_de_accion(accion)
        if categoria:
            cliente.contexto_cualificacion = {
                **(cliente.contexto_cualificacion or {}),
                "categoria": categoria,
            }
        mensajes, escalar = menu.responder_accion(session, accion, url_web(), url_media())
        intencion = "menu"
        respuesta = "\n".join(m.plano() for m in mensajes)
    else:
        resultado_lc = None
        if modelo is not None:
            try:
                from app.agente import lc_agente

                session.flush()  # para conocer el id del mensaje y no repetirlo en el historial
                resultado_lc = lc_agente.responder(
                    session, modelo, cliente, conversacion.id, texto, entrante.id
                )
            except Exception:
                logger.exception("El agente LangChain falló; se responde con el motor de reglas")
        if resultado_lc is not None:
            intencion = resultado_lc.herramientas[0] if resultado_lc.herramientas else "conversacion"
            respuesta, escalar = resultado_lc.texto, resultado_lc.escalar
            mensajes = resultado_lc.mensajes
        else:
            intencion = clasificar(texto, proveedor)
            if intencion == "otro" and (
                datos.contexto.get("categoria") or datos.contexto.get("material")
            ):
                # Mencionó una joya o un material sin pedir nada concreto: le mostramos el catálogo.
                intencion = "catalogo"
            respuesta, escalar = redactar(
                intencion, cliente.nombre_preferido, cliente.contexto_cualificacion or {}
            )
            mensajes = menu.enriquecer(
                session,
                intencion,
                respuesta,
                cliente.nombre_preferido,
                cliente.contexto_cualificacion or {},
                url_web(),
            )
    session.add(
        Mensaje(conversacion_id=conversacion.id, direccion="saliente", contenido=respuesta)
    )
    if escalar:
        conversacion.estado = "escalada"
        session.add(
            TransicionConversacion(
                conversacion_id=conversacion.id,
                estado_anterior="activa",
                estado_nuevo="escalada",
            )
        )
    session.commit()
    return RespuestaAgente(
        respuesta,
        intencion,
        conversacion.id,
        cliente.id,
        escalada=escalar,
        cliente_nuevo=creado,
        mensajes=mensajes,
    )
