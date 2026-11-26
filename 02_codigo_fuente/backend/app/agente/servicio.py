"""Atiende un mensaje entrante: guarda la conversación y arma la respuesta."""
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agente import contexto as ctx
from app.agente import escalamiento, estado_ordenes, intereses, menu, proteccion, seguridad
from app.agente.intenciones import clasificar
from app.agente.llm import ProveedorLLM
from app import asignacion
from app.bitacora import sin_claves
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


# Cómo se nombra cada ocasión dentro de una frase («es para un aniversario»).
FRASE_DE_OCASION = {
    "aniversario": "un aniversario",
    "cumpleaños": "un cumpleaños",
    "boda": "una boda",
    "compromiso": "un compromiso",
    "graduación": "una graduación",
    "bautizo": "un bautizo",
    "primera comunión": "una primera comunión",
    "día de la madre": "el Día de la Madre",
    "quince años": "unos quince años",
    "regalo": "un regalo",
}


def _seguir_con_lo_anotado(coma: str, contexto: dict) -> str:
    """JOY-94: sin modelo, un mensaje con un dato (ocasión o presupuesto) no recibe «no entendí»:
    se confirma lo anotado y se hace la siguiente pregunta que falta."""
    actual = intereses.activo(contexto) or contexto
    ocasion, presupuesto = actual.get("ocasion"), actual.get("presupuesto")
    frase = FRASE_DE_OCASION.get(ocasion, ocasion)
    if ocasion and presupuesto:
        anotado = f"es para {frase}, con un presupuesto de {presupuesto}"
    elif ocasion:
        anotado = f"es para {frase}"
    else:
        anotado = f"tu presupuesto es de {presupuesto}"
    if not actual.get("categoria"):
        siguiente = (
            "¿Qué tipo de joya tienes en mente? Tenemos anillos, argollas, aretes, cadenas, "
            "pulseras y dijes."
        )
    elif not actual.get("material"):
        siguiente = "¿La prefieres en oro o en plata?"
    else:
        descripcion = _describir(actual)
        siguiente = (
            f"Aquí puedes ver las opciones de {descripcion} y cotizar al instante: "
            f"{enlace_catalogo(actual)}"
        )
    return f"Anotado{coma}: {anotado}. {siguiente}"


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
    if intencion == "seguimiento":
        return _seguir_con_lo_anotado(coma, contexto), False
    if intencion == "catalogo":
        return (
            f"Con gusto{coma}. Aquí puedes ver el catálogo y filtrar por categoría, "
            f"material y precio: {enlace}",
            False,
        )
    if intencion == "estado_pedido":
        return (
            "No encuentro un pedido registrado a tu nombre. Te comunico con un asesor "
            "para que lo revise contigo; en breve te atenderá una persona.",
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


# Qué quiso el cliente, dicho como lo lee el asesor en la ficha. La primera que coincida gana:
# pedir una persona pesa más que haber mirado el catálogo en el mismo mensaje.
INTENCIONES_DE_LA_FICHA = (
    (("asesor", "derivar_a_asesor"), "Hablar con un asesor"),
    (("estado_pedido", "consultar_orden"), "Consultar el estado de su pedido"),
    (("cotizar",), "Cotizar una joya"),
    (("catalogo", "consultar_catalogo", "mostrar_opciones", "menu"), "Ver el catálogo o cotizar"),
    (("informacion_joyeria",), "Pregunta sobre la joyería"),
)


def _anotar_intencion(cliente: Cliente, detectadas: list[str]) -> None:
    """Guarda la última intención reconocible; un saludo o una charla no borran la anterior."""
    for claves, etiqueta in INTENCIONES_DE_LA_FICHA:
        if any(d in claves for d in detectadas):
            cliente.contexto_cualificacion = {
                **(cliente.contexto_cualificacion or {}),
                "intencion": etiqueta,
            }
            return


def _recordar(cliente: Cliente, datos: ctx.Datos) -> None:
    if datos.nombre:
        cliente.nombre_preferido = datos.nombre
    if datos.talla:
        cliente.talla = datos.talla
    if datos.contexto or datos.talla:
        # Cada joya que menciona es un interés aparte (JOY-80). Se reasigna un dict nuevo para
        # que SQLAlchemy detecte el cambio en el JSON.
        cliente.contexto_cualificacion = intereses.anotar(
            cliente.contexto_cualificacion, talla=datos.talla, **datos.contexto
        )


MOTIVO_POR_INTENCION = {
    "asesor": "El cliente pidió hablar con un asesor",
    "estado_pedido": "Pregunta por un pedido y no hay ninguna orden a su nombre",
}


def _escalar_por_motivo(
    session: Session,
    conversacion: Conversacion,
    cliente: Cliente,
    creado: bool,
    escalado: "escalamiento.Escalamiento",
) -> RespuestaAgente:
    """Escalamiento automático: responde, deja el motivo en la ficha y asigna un asesor."""
    cliente.contexto_cualificacion = {
        **escalamiento.entendido(cliente.contexto_cualificacion or {}),
        "motivo_escalamiento": escalado.motivo,
    }
    _anotar_intencion(cliente, ["asesor"])
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="saliente",
            contenido=escalado.respuesta,
            origen="escalamiento",
        )
    )
    conversacion.estado = "escalada"
    asignacion.asignar_al_escalar(session, conversacion)
    session.add(
        TransicionConversacion(
            conversacion_id=conversacion.id, estado_anterior="activa", estado_nuevo="escalada"
        )
    )
    session.commit()
    return RespuestaAgente(
        escalado.respuesta, "asesor", conversacion.id, cliente.id, escalada=True, cliente_nuevo=creado
    )


def _respuesta_fija(
    session: Session,
    conversacion: Conversacion,
    cliente: Cliente,
    creado: bool,
    texto: str,
    intencion: str,
) -> RespuestaAgente:
    """Respuesta de la seguridad del agente: se guarda como del agente con origen «guardrail»."""
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="saliente",
            contenido=texto,
            origen="guardrail",
        )
    )
    session.commit()
    return RespuestaAgente(texto, intencion, conversacion.id, cliente.id, cliente_nuevo=creado)


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

    # Seguridad del agente II (JOY-74): antes de cualquier modelo.
    session.flush()  # para conocer el id del mensaje y anotarlo si se bloquea
    redis_cliente = getattr(cache, "redis", None)
    if redis_cliente is not None:
        revision = proteccion.LimiteDeMensajes(redis_cliente).revisar(canal, id_canal)
        if not revision.permitido:
            if not revision.avisar:
                # Ya se le avisó en esta ventana: se guarda su mensaje y no se responde.
                session.commit()
                return RespuestaAgente(
                    None, "limite_de_mensajes", conversacion.id, cliente.id, cliente_nuevo=creado
                )
            proteccion.registrar(
                session, canal, "limite_de_mensajes", cliente.id, entrante.id
            )
            return _respuesta_fija(
                session, conversacion, cliente, creado,
                proteccion.AVISO_LIMITE, "limite_de_mensajes",
            )
    regla = None if accion else seguridad.regla_de_ataque(texto)
    if regla:
        # Guardrail de entrada (RNF-01): ni el modelo ni el clasificador ven el mensaje.
        proteccion.registrar(
            session, canal, "instrucciones", cliente.id, entrante.id, regla=regla
        )
        return _respuesta_fija(
            session, conversacion, cliente, creado,
            seguridad.respuesta_para(regla), "guardrail_entrada",
        )

    # Escalamiento automático (JOY-85): molestia, pedido sin herramienta o cotización fuera de
    # rango pasan a un asesor sin llamar al modelo.
    automatico = None if accion else escalamiento.antes_del_modelo(texto)
    if automatico:
        return _escalar_por_motivo(session, conversacion, cliente, creado, automatico)

    detectadas: list[str] = []
    if accion:
        # El cliente tocó un botón o una opción de una lista: no hay texto que interpretar.
        elegido = menu.interes_de_accion(session, accion)
        if elegido:
            cliente.contexto_cualificacion = intereses.anotar(
                cliente.contexto_cualificacion, **elegido
            )
        mensajes, escalar = menu.responder_accion(session, accion, url_web(), url_media())
        intencion = "menu"
        origen = "menu"
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
            except Exception as error:
                logger.error(
                    "El agente LangChain falló (%s: %s); se responde con el motor de reglas",
                    type(error).__name__,
                    sin_claves(str(error))[:300],
                    exc_info=True,
                )
        if resultado_lc is not None and resultado_lc.regla_de_salida:
            proteccion.registrar(
                session,
                canal,
                "respuesta_corregida",
                cliente.id,
                entrante.id,
                regla=resultado_lc.regla_de_salida,
            )
        if resultado_lc is not None:
            intencion = resultado_lc.herramientas[0] if resultado_lc.herramientas else "conversacion"
            detectadas = list(resultado_lc.herramientas)
            respuesta, escalar = resultado_lc.texto, resultado_lc.escalar
            mensajes = resultado_lc.mensajes
            origen = resultado_lc.origen
        else:
            origen = "reglas"
            intencion = clasificar(texto, proveedor)
            # Sin modelo nadie anota la ocasión ni el presupuesto: lo hace el motor de reglas.
            de_compra = ctx.ocasion_y_presupuesto(texto)
            if de_compra:
                cliente.contexto_cualificacion = intereses.anotar(
                    cliente.contexto_cualificacion, **de_compra
                )
            if intencion == "otro" and (
                datos.contexto.get("categoria") or datos.contexto.get("material")
            ):
                # Mencionó una joya o un material sin pedir nada concreto: le mostramos el catálogo.
                intencion = "catalogo"
            elif intencion == "otro" and de_compra:
                # Dio un dato (ocasión o presupuesto): se anota y se sigue, no «no entendí».
                intencion = "seguimiento"
            respuesta, escalar = redactar(
                intencion, cliente.nombre_preferido, cliente.contexto_cualificacion or {}
            )
            if intencion == "estado_pedido":
                # Sin modelo también se responde con el estado real; solo pasa a un asesor si
                # no hay ninguna orden a su nombre (JOY-21).
                estado = estado_ordenes.para_el_cliente(
                    session, cliente.id, cliente.nombre_preferido
                )
                if estado:
                    respuesta, escalar = estado, False
            contexto = cliente.contexto_cualificacion or {}
            if intencion == "otro":
                # Segundo mensaje seguido que no entiende: pasa a un asesor (JOY-85).
                contexto, no_entiende = escalamiento.no_entendido(contexto)
                if no_entiende:
                    intencion, respuesta, escalar = "asesor", no_entiende.respuesta, True
                    contexto = {**contexto, "motivo_escalamiento": no_entiende.motivo}
            else:
                contexto = escalamiento.entendido(contexto)
            cliente.contexto_cualificacion = contexto
            mensajes = menu.enriquecer(
                session,
                intencion,
                respuesta,
                cliente.nombre_preferido,
                cliente.contexto_cualificacion or {},
                url_web(),
                url_media(),
            )
    _anotar_intencion(cliente, detectadas or [intencion])
    # En el panel se guarda lo mismo que recibe el cliente (lista, botones y enlace incluidos).
    enviado = "\n".join(m.plano() for m in mensajes) if mensajes else respuesta
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="saliente",
            contenido=enviado,
            origen=origen,
        )
    )
    if escalar:
        contexto = dict(cliente.contexto_cualificacion or {})
        if not contexto.get("motivo_escalamiento"):
            # El motor de reglas no anota motivo: se deja uno según lo que pasó (JOY-85).
            contexto["motivo_escalamiento"] = MOTIVO_POR_INTENCION.get(
                intencion, "El agente pasó la conversación a un asesor"
            )
            cliente.contexto_cualificacion = contexto
        conversacion.estado = "escalada"
        asignacion.asignar_al_escalar(session, conversacion)  # JOY-84: a un asesor o a la cola
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
