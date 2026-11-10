"""Agente conversacional con LangChain (JOY-57).

El modelo de lenguaje entiende el mensaje en lenguaje natural, decide qué herramienta
usar y redacta la respuesta. Las herramientas son las comprometidas en la propuesta:

1. Cualificación progresiva del cliente y preguntas frecuentes.
2. Redirección a la plataforma web (catálogo y cotizador) cuando quiere cotizar o ver joyas.
3. Consulta del estado de su orden activa.

Además puede derivar la conversación a un asesor y mostrar opciones tocables (lista de
categorías o de joyas) como complemento de la conversación, nunca en lugar de ella.
Si el modelo falla, el servicio vuelve al motor de reglas.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agente import menu
from app.catalogo import precios_vigentes
from app.contacto import armar_canales
from app.mensajes import Saliente
from app.models import Cliente, Mensaje, Orden, Producto

logger = logging.getLogger("joyeria.agente")

MAX_RONDAS = 4  # veces que el modelo puede pedir herramientas antes de dar su respuesta
MENSAJES_DE_HISTORIAL = 8

INSTRUCCIONES = """\
Eres el asistente virtual de Joyería Xavier, una joyería de Ecuador. Atiendes a clientes \
por WhatsApp, Instagram y Messenger.

Cómo debes responder:
- Siempre en español, con tono cálido y cercano, breve (máximo 3 o 4 líneas), sin listas largas.
- Entiende lo que el cliente quiere aunque lo escriba con otras palabras; no le pidas que use \
comandos ni palabras exactas.
- Haz una sola pregunta a la vez para conocer lo que busca (tipo de joya, material, ocasión, \
presupuesto, talla). Cuando el cliente te dé un dato, guárdalo con la herramienta de preferencias.
- Nunca inventes precios, existencias, plazos ni políticas. Para datos reales usa las herramientas.
- Cuando el cliente pregunte por precios, joyas, categorías o quiera cotizar, llama SIEMPRE primero \
a la herramienta del catálogo y menciona uno o dos precios "desde" reales que ella devuelva.
- Nunca escribas enlaces ni direcciones web por tu cuenta. El único enlace permitido es el que \
entrega la herramienta del catálogo, copiado tal cual.
- Los precios son referenciales: la cotización exacta se calcula en la plataforma web (peso de la \
pieza por el precio del material más la mano de obra) y un asesor confirma el valor final.
- Si quiere cotizar o ver joyas, usa la herramienta del catálogo y dirígelo a la web; si te \
conviene, muestra una lista tocable con las opciones.
- Si pregunta por su pedido, consulta su orden con la herramienta correspondiente.
- Si pide hablar con una persona, está molesto, o te pide algo que no puedes resolver con tus \
herramientas, derívalo a un asesor.
- No menciones que usas herramientas ni hables de tu funcionamiento interno.
"""


@dataclass
class ResultadoAgente:
    texto: str
    escalar: bool = False
    herramientas: list[str] = field(default_factory=list)
    mensajes: list[Saliente] | None = None


class _Estado:
    """Lo que las herramientas dejan anotado durante una respuesta."""

    def __init__(self) -> None:
        self.escalar = False
        self.lista: Saliente | None = None
        self.herramientas: list[str] = []


def _segundos_de_espera() -> float:
    """Gemini rechaza plazos menores a 10 s; por defecto 15 s (configurable con GEMINI_TIMEOUT)."""
    try:
        return max(10.0, float(os.getenv("GEMINI_TIMEOUT", "15")))
    except ValueError:
        return 15.0


def crear_modelo_desde_entorno() -> BaseChatModel | None:
    """Gemini a través de LangChain si hay GEMINI_API_KEY; si no, None (se usan reglas)."""
    clave = os.getenv("GEMINI_API_KEY", "").strip()
    if not clave:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    modelo = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    opciones = {}
    if "2.5" in modelo and "pro" not in modelo:
        opciones["thinking_budget"] = 0  # respuesta corta y rápida para un chat
    return ChatGoogleGenerativeAI(
        model=modelo,
        api_key=clave,
        temperature=0.3,
        max_tokens=600,
        request_timeout=_segundos_de_espera(),
        retries=1,
        **opciones,
    )


_ENLACE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|ec|net|org|io|co)\b(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)


def sanear_enlaces(texto: str, permitidos: list[str]) -> str:
    """El modelo no puede inventar enlaces: los que no sean de la web de la joyería se cambian
    por el enlace que entregó la herramienta (o por la web a secas)."""
    base = _url_web()
    validos = [u.rstrip("/") for u in permitidos] + [base]
    reemplazo = permitidos[0] if permitidos else base

    def cambiar(m: re.Match) -> str:
        url = m.group(0)
        final = ""
        while url and url[-1] in ".,;:!?)":  # la puntuación de la frase no es del enlace
            final = url[-1] + final
            url = url[:-1]
        if any(url.rstrip("/").startswith(v) for v in validos):
            return url + final
        return reemplazo + final

    return _ENLACE.sub(cambiar, texto)


def _enlaces_de(mensajes: list[BaseMessage]) -> list[str]:
    encontrados: list[str] = []
    for m in mensajes:
        if isinstance(m, ToolMessage):
            encontrados += re.findall(r"https?://[^\s<>\"']+", str(m.content))
    return [u.rstrip(".,;:!?)") for u in encontrados]


def _url_web() -> str:
    return os.getenv("WEB_URL", "http://localhost:5173").rstrip("/")


def _dinero(valor: Decimal) -> str:
    return f"${Decimal(valor):,.2f}"


def construir_herramientas(
    session: Session, cliente: Cliente, estado: _Estado
) -> list[StructuredTool]:
    """Las herramientas del agente, ligadas al cliente que está escribiendo."""

    def guardar_preferencias(
        nombre: str | None = None,
        categoria: str | None = None,
        material: str | None = None,
        talla: str | None = None,
        ocasion: str | None = None,
        presupuesto: str | None = None,
    ) -> str:
        """Guarda lo que el cliente va contando: su nombre, el tipo de joya (Anillos, Argollas,
        Cadenas, Pulseras, Aretes, Dijes), el material (oro o plata), su talla, la ocasión y su
        presupuesto. Úsala cada vez que el cliente te dé uno de estos datos."""
        guardado = {}
        if nombre:
            cliente.nombre_preferido = nombre.strip()[:100]
            guardado["nombre"] = cliente.nombre_preferido
        if talla:
            cliente.talla = talla.strip()[:20]
            guardado["talla"] = cliente.talla
        contexto = dict(cliente.contexto_cualificacion or {})
        if categoria:
            existente = menu._categoria_existente(session, categoria)
            contexto["categoria"] = existente or categoria.strip().capitalize()
            guardado["categoria"] = contexto["categoria"]
        if material:
            contexto["material"] = material.strip().lower()
            guardado["material"] = contexto["material"]
        if ocasion:
            contexto["ocasion"] = ocasion.strip()[:100]
            guardado["ocasion"] = contexto["ocasion"]
        if presupuesto:
            contexto["presupuesto"] = presupuesto.strip()[:50]
            guardado["presupuesto"] = contexto["presupuesto"]
        # Se reasigna un dict nuevo para que SQLAlchemy detecte el cambio en el JSON.
        cliente.contexto_cualificacion = contexto
        session.flush()
        return f"Datos guardados: {guardado}" if guardado else "No había datos para guardar."

    def consultar_catalogo(categoria: str | None = None, material: str | None = None) -> str:
        """Consulta las joyas disponibles con su precio inicial referencial y devuelve el
        enlace a la plataforma web donde el cliente puede ver el catálogo y cotizar en tiempo
        real. Úsala cuando el cliente quiera ver joyas, cotizar o saber precios."""
        consulta = select(Producto).where(Producto.activo.is_(True)).order_by(Producto.id)
        if categoria:
            nombre = menu._categoria_existente(session, categoria)
            if nombre is None:
                disponibles = ", ".join(menu._categorias(session))
                return f"No hay una categoría llamada '{categoria}'. Categorías disponibles: {disponibles}."
            consulta = consulta.where(Producto.categoria == nombre)
        productos = list(session.scalars(consulta))
        vigentes = precios_vigentes(session, productos)
        lineas = []
        for p in productos:
            precios = vigentes.get(p.id, [])
            if material:
                precios = [x for x in precios if x.material.lower() == material.lower()]
            if not precios:
                continue
            lineas.append(f"- {p.nombre} ({p.categoria}): desde {_dinero(min(x.precio for x in precios))}")
        params = {}
        if categoria:
            params["categoria"] = nombre
        if material:
            params["material"] = material.lower()
        enlace = _url_web() + (f"/?{urlencode(params)}" if params else "")
        if not lineas:
            return f"No hay joyas con esos filtros. Catálogo completo: {enlace}"
        return (
            "Joyas (precios referenciales en USD, calculados por peso y material más mano de obra):\n"
            + "\n".join(lineas[:10])
            + f"\nEnlace para ver el catálogo y cotizar en tiempo real: {enlace}"
        )

    def consultar_orden() -> str:
        """Consulta el estado de las órdenes de producción activas del cliente que escribe.
        Úsala cuando pregunte por su pedido, su encargo o cuándo estará listo."""
        ordenes = list(
            session.scalars(
                select(Orden)
                .where(Orden.cliente_id == cliente.id)
                .order_by(Orden.id.desc())
                .limit(3)
            )
        )
        if not ordenes:
            return "El cliente no tiene órdenes registradas."
        lineas = [
            f"- OP-{o.id:06d}: {o.descripcion} · etapa actual: {o.etapa_actual.replace('_', ' ')}"
            for o in ordenes
        ]
        return "Órdenes del cliente:\n" + "\n".join(lineas)

    def informacion_joyeria(tema: str) -> str:
        """Responde preguntas frecuentes. Temas: 'cotizacion' (cómo se calcula el precio),
        'contacto' (canales de contacto) o 'pedidos' (cómo funcionan las órdenes)."""
        tema = (tema or "").lower()
        if "contact" in tema or "whatsapp" in tema or "instagram" in tema:
            canales = armar_canales("Hola, quisiera más información.")
            return "Canales: " + ", ".join(f"{c.nombre} {c.enlace}" for c in canales)
        if "pedido" in tema or "orden" in tema or "encargo" in tema:
            return (
                "Los pedidos se registran como órdenes de producción en el taller; el cliente "
                "puede consultar la etapa de su orden por este chat. Los plazos y el valor final "
                "los confirma un asesor."
            )
        return (
            "El precio se calcula multiplicando el peso de la pieza por el precio del gramo del "
            "material (oro 18k, oro 14k o plata) y sumando la mano de obra. Es un valor "
            "referencial; un asesor confirma el precio final. Se puede cotizar en tiempo real "
            f"en la web: {_url_web()}"
        )

    def mostrar_opciones(categoria: str | None = None) -> str:
        """Muestra al cliente una lista tocable: sin categoría, las categorías de joyas; con
        una categoría, las joyas de ese tipo. Úsala como complemento cuando ayude a elegir."""
        if categoria:
            nombre = menu._categoria_existente(session, categoria)
            if nombre is None:
                return f"No hay una categoría llamada '{categoria}'."
            lista = menu.lista_de_productos(session, nombre, "")
        else:
            lista = menu.lista_de_categorias(session, "")
        if lista is None:
            return "No hay opciones para mostrar."
        estado.lista = lista
        return "Se mostrará una lista tocable al cliente junto con tu respuesta."

    def derivar_a_asesor(motivo: str) -> str:
        """Pasa la conversación a un asesor humano. Úsala si el cliente lo pide, si está
        molesto o si necesita algo que no puedes resolver."""
        estado.escalar = True
        return "La conversación se pasará a un asesor, que atenderá al cliente en breve."

    funciones = [
        guardar_preferencias,
        consultar_catalogo,
        consultar_orden,
        informacion_joyeria,
        mostrar_opciones,
        derivar_a_asesor,
    ]
    return [StructuredTool.from_function(f, name=f.__name__) for f in funciones]


def _a_texto(contenido) -> str:
    """El contenido de un mensaje del modelo puede ser texto o una lista de bloques."""
    if isinstance(contenido, str):
        return contenido
    partes = []
    for bloque in contenido or []:
        if isinstance(bloque, str):
            partes.append(bloque)
        elif isinstance(bloque, dict) and bloque.get("type") == "text":
            partes.append(bloque.get("text", ""))
    return "".join(partes)


def _historial(session: Session, conversacion_id: int, hasta_id: int | None) -> list[BaseMessage]:
    consulta = select(Mensaje).where(Mensaje.conversacion_id == conversacion_id)
    if hasta_id is not None:
        consulta = consulta.where(Mensaje.id < hasta_id)
    filas = list(session.scalars(consulta.order_by(Mensaje.id.desc()).limit(MENSAJES_DE_HISTORIAL)))
    mensajes: list[BaseMessage] = []
    for m in reversed(filas):
        mensajes.append(HumanMessage(m.contenido) if m.direccion == "entrante" else AIMessage(m.contenido))
    return mensajes


def responder(
    session: Session,
    modelo: BaseChatModel,
    cliente: Cliente,
    conversacion_id: int,
    texto: str,
    id_mensaje_actual: int | None = None,
) -> ResultadoAgente:
    """Deja que el modelo atienda el mensaje, usando las herramientas que necesite."""
    estado = _Estado()
    herramientas = construir_herramientas(session, cliente, estado)
    por_nombre = {h.name: h for h in herramientas}
    con_herramientas = modelo.bind_tools(herramientas)

    sistema = INSTRUCCIONES
    if cliente.nombre_preferido:
        sistema += f"\nEl cliente se llama {cliente.nombre_preferido}."
    mensajes: list[BaseMessage] = [
        SystemMessage(sistema),
        *_historial(session, conversacion_id, id_mensaje_actual),
        HumanMessage(texto),
    ]

    respuesta = ""
    for _ in range(MAX_RONDAS):
        ia = con_herramientas.invoke(mensajes)
        mensajes.append(ia)
        if not ia.tool_calls:
            respuesta = _a_texto(ia.content).strip()
            break
        for llamada in ia.tool_calls:
            estado.herramientas.append(llamada["name"])
            herramienta = por_nombre.get(llamada["name"])
            if herramienta is None:
                salida = f"La herramienta {llamada['name']} no existe."
            else:
                try:
                    salida = herramienta.invoke(llamada["args"])
                except Exception as e:  # una herramienta que falla no debe tumbar la respuesta
                    logger.exception("Falló la herramienta %s", llamada["name"])
                    salida = f"No se pudo completar la consulta ({type(e).__name__})."
            mensajes.append(ToolMessage(content=str(salida), tool_call_id=llamada["id"]))

    if not respuesta:
        raise ValueError("El modelo no produjo una respuesta de texto")
    respuesta = sanear_enlaces(respuesta, _enlaces_de(mensajes))

    salientes = None
    if estado.lista is not None:
        estado.lista.texto = respuesta[:1024]
        salientes = [estado.lista]
    return ResultadoAgente(
        texto=respuesta,
        escalar=estado.escalar,
        herramientas=estado.herramientas,
        mensajes=salientes,
    )
