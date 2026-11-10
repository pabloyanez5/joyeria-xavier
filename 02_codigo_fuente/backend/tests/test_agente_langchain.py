import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

pytest.importorskip("langchain_core")

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from app.agente import lc_agente  # noqa: E402
from app.agente.rutas import get_modelo_chat, get_proveedor  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from app.cache import get_cache  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.meta_envio import Enviador  # noqa: E402
from app.models import Cliente, Orden  # noqa: E402
from app.seed import cargar  # noqa: E402
from app.webhook import get_enviador  # noqa: E402

from tests.test_webhook import _payload_texto  # noqa: E402

WEB = "http://sitio.test"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("WEB_URL", WEB)


@pytest.fixture
def catalogo(session):
    cargar(session)


class ModeloGuion(BaseChatModel):
    """Modelo de lenguaje de mentira: responde lo que se le indique, en orden."""

    respuestas: list = []
    recibidos: list = []
    falla: bool = False

    @property
    def _llm_type(self) -> str:
        return "guion"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.falla:
            raise RuntimeError("sin servicio")
        self.recibidos.append(list(messages))
        ia = self.respuestas[len(self.recibidos) - 1]
        return ChatResult(generations=[ChatGeneration(message=ia)])


def modelo(*respuestas, falla=False):
    return ModeloGuion(respuestas=list(respuestas), recibidos=[], falla=falla)


def llamada(herramienta, /, **args):
    return AIMessage(
        content="", tool_calls=[{"name": herramienta, "args": args, "id": f"id-{herramienta}"}]
    )


def _enviar(session, cache, texto, m=None, id_canal="593999"):
    return atender_mensaje(session, cache, "whatsapp", id_canal, texto, proveedor=None, modelo=m)


def _cliente(session):
    return session.scalar(select(Cliente))


# --- el modelo conversa en lenguaje natural ---

def test_responde_con_el_texto_que_redacta_el_modelo(session, cache, catalogo):
    m = modelo(AIMessage("¡Hola! Cuéntame, ¿qué joya buscas hoy?"))
    r = _enviar(session, cache, "buenas tardes, quisiera ver algo bonito", m)
    assert r.texto == "¡Hola! Cuéntame, ¿qué joya buscas hoy?"
    assert r.intencion == "conversacion"
    assert r.mensajes is None
    enviados = m.recibidos[0]
    assert isinstance(enviados[0], SystemMessage) and "Joyería Xavier" in enviados[0].content
    assert isinstance(enviados[-1], HumanMessage)
    assert enviados[-1].content == "buenas tardes, quisiera ver algo bonito"


def test_el_modelo_recibe_el_historial_sin_repetir_el_mensaje_actual(session, cache, catalogo):
    _enviar(session, cache, "hola", modelo(AIMessage("¡Hola! ¿Qué buscas?")))
    m = modelo(AIMessage("Los anillos de oro son preciosos."))
    _enviar(session, cache, "busco un anillo de oro", m)
    enviados = m.recibidos[0][1:]  # sin el mensaje de sistema
    assert [type(x).__name__ for x in enviados] == ["HumanMessage", "AIMessage", "HumanMessage"]
    assert enviados[0].content == "hola" and enviados[1].content == "¡Hola! ¿Qué buscas?"
    assert enviados[2].content == "busco un anillo de oro"


# --- herramienta 1: cualificación progresiva ---

def test_guarda_lo_que_va_contando_el_cliente(session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", nombre="Luis", categoria="anillos", material="Oro",
                ocasion="aniversario"),
        AIMessage("Encantado, Luis. ¿Qué presupuesto tienes en mente?"),
    )
    r = _enviar(session, cache, "soy Luis, busco un anillo de oro para mi aniversario", m)
    cliente = _cliente(session)
    assert cliente.nombre_preferido == "Luis"
    assert cliente.contexto_cualificacion["categoria"] == "Anillos"
    assert cliente.contexto_cualificacion["material"] == "oro"
    assert cliente.contexto_cualificacion["ocasion"] == "aniversario"
    assert r.intencion == "guardar_preferencias"
    assert "presupuesto" in r.texto


# --- herramienta 2: redirección a la web ---

def test_el_catalogo_llega_al_modelo_con_precios_y_enlace_a_la_web(session, cache, catalogo):
    m = modelo(
        llamada("consultar_catalogo", categoria="Anillos"),
        AIMessage("Tenemos tres anillos; puedes cotizarlos en la web."),
    )
    r = _enviar(session, cache, "quiero cotizar un anillo", m)
    resultado = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert "Anillo solitario clásico" in resultado and "desde $84.40" in resultado
    assert f"{WEB}/?categoria=Anillos" in resultado
    assert r.intencion == "consultar_catalogo"


def test_catalogo_con_categoria_inexistente_lo_dice(session, cache, catalogo):
    m = modelo(llamada("consultar_catalogo", categoria="Relojes"), AIMessage("No tenemos relojes."))
    _enviar(session, cache, "relojes?", m)
    resultado = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert "No hay una categoría" in resultado and "Anillos" in resultado


# --- herramienta 3: estado de la orden ---

def test_consulta_la_orden_del_cliente(session, cache, catalogo):
    _enviar(session, cache, "hola")  # crea al cliente
    cliente = _cliente(session)
    session.add(Orden(cliente_id=cliente.id, descripcion="Argollas en oro 18k",
                      etapa_actual="en_fundicion"))
    session.commit()
    m = modelo(llamada("consultar_orden"), AIMessage("Tu orden está en fundición."))
    r = _enviar(session, cache, "cómo va mi pedido?", m)
    resultado = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert "OP-" in resultado and "Argollas en oro 18k" in resultado and "en fundicion" in resultado
    assert r.texto == "Tu orden está en fundición." and not r.escalada


def test_sin_ordenes_el_modelo_lo_sabe(session, cache, catalogo):
    m = modelo(llamada("consultar_orden"), AIMessage("No encuentro pedidos a tu nombre."))
    _enviar(session, cache, "mi pedido?", m)
    resultado = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert "no tiene órdenes" in resultado


def test_preguntas_frecuentes_sin_inventar(session, cache, catalogo):
    m = modelo(llamada("informacion_joyeria", tema="cotizacion"), AIMessage("Se calcula por peso."))
    _enviar(session, cache, "cómo calculan los precios?", m)
    resultado = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert "peso de la pieza" in resultado and "mano de obra" in resultado and "referencial" in resultado


# --- complementos: opciones tocables y derivación ---

def test_el_modelo_puede_mostrar_una_lista_tocable(session, cache, catalogo):
    m = modelo(
        llamada("mostrar_opciones", categoria="Cadenas"),
        AIMessage("Mira estas cadenas, elige la que más te guste."),
    )
    r = _enviar(session, cache, "qué cadenas tienen?", m)
    assert r.texto == "Mira estas cadenas, elige la que más te guste."
    lista = r.mensajes[0]
    assert lista.tipo == "lista" and lista.texto == r.texto
    assert [f.titulo for f in lista.filas] == ["Cadena cubana", "Cadena veneciana"]


def test_el_modelo_puede_derivar_a_un_asesor_y_luego_calla(session, cache, catalogo):
    m = modelo(
        llamada("derivar_a_asesor", motivo="cliente molesto"),
        AIMessage("Lamento lo ocurrido; te paso con un asesor ahora mismo."),
    )
    r = _enviar(session, cache, "esto es un desastre, quiero hablar con alguien", m)
    assert r.escalada and "asesor" in r.texto
    callado = _enviar(session, cache, "hola", modelo(AIMessage("no debería hablar")))
    assert callado.texto is None


# --- el modelo no puede inventar enlaces ---

def test_un_enlace_inventado_se_cambia_por_el_de_la_herramienta(session, cache, catalogo):
    m = modelo(
        llamada("consultar_catalogo", categoria="Argollas"),
        AIMessage("Mira nuestras argollas: https://joyeriaxavier.com/catalogo/argollas. ¿Algo más?"),
    )
    r = _enviar(session, cache, "argollas", m)
    assert "joyeriaxavier.com" not in r.texto
    assert f"{WEB}/?categoria=Argollas. ¿Algo más?" in r.texto


def test_un_enlace_inventado_sin_herramienta_apunta_a_la_web(session, cache, catalogo):
    m = modelo(AIMessage("Visita joyeriaxavier.com/catalogo o www.otra.com, gracias."))
    r = _enviar(session, cache, "dónde las veo?", m)
    assert r.texto == f"Visita {WEB} o {WEB}, gracias."


def test_el_enlace_correcto_no_se_toca():
    texto = f"Entra a {WEB}/?categoria=Anillos y cotiza."
    assert lc_agente.sanear_enlaces(texto, [f"{WEB}/?categoria=Anillos"]) == texto


def test_los_decimales_y_las_frases_no_se_confunden_con_enlaces():
    texto = "El anillo cuesta $84.40 aprox. y pesa 4.5 gramos. Dime cuál te gusta."
    assert lc_agente.sanear_enlaces(texto, []) == texto


# --- robustez ---

def test_si_el_modelo_falla_responde_el_motor_de_reglas(session, cache, catalogo):
    r = _enviar(session, cache, "hola", modelo(falla=True))
    assert r.intencion == "saludo" and "asistente virtual" in r.texto


def test_si_el_modelo_no_da_texto_responde_el_motor_de_reglas(session, cache, catalogo):
    r = _enviar(session, cache, "hola", modelo(AIMessage("")))
    assert r.intencion == "saludo"


def test_una_herramienta_inexistente_no_tumba_la_respuesta(session, cache, catalogo):
    m = modelo(llamada("hackear"), AIMessage("Listo."))
    r = _enviar(session, cache, "hola", m)
    assert r.texto == "Listo."
    assert "no existe" in [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content


def test_el_modelo_no_puede_quedarse_pidiendo_herramientas_para_siempre(session, cache, catalogo):
    bucle = [llamada("consultar_orden")] * 10
    r = _enviar(session, cache, "hola", modelo(*bucle))
    assert r.intencion == "saludo"  # se rinde y responde el motor de reglas


def test_los_mensajes_del_agente_quedan_guardados(session, cache, catalogo):
    from app.models import Mensaje

    _enviar(session, cache, "hola", modelo(AIMessage("¡Hola! ¿En qué te ayudo?")))
    guardados = [(m.direccion, m.contenido) for m in session.scalars(select(Mensaje).order_by(Mensaje.id))]
    assert guardados == [("entrante", "hola"), ("saliente", "¡Hola! ¿En qué te ayudo?")]


# --- configuración del modelo ---

def test_sin_clave_no_hay_modelo(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert lc_agente.crear_modelo_desde_entorno() is None


def test_con_clave_se_crea_el_modelo_de_gemini_de_langchain(monkeypatch):
    pytest.importorskip("langchain_google_genai")
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    creado = lc_agente.crear_modelo_desde_entorno()
    assert type(creado).__name__ == "ChatGoogleGenerativeAI"
    assert creado.model.endswith("gemini-2.5-flash-lite")


def test_el_plazo_de_espera_nunca_baja_del_minimo_de_gemini(monkeypatch):
    monkeypatch.delenv("GEMINI_TIMEOUT", raising=False)
    assert lc_agente._segundos_de_espera() == 15
    monkeypatch.setenv("GEMINI_TIMEOUT", "3")
    assert lc_agente._segundos_de_espera() == 10
    monkeypatch.setenv("GEMINI_TIMEOUT", "abc")
    assert lc_agente._segundos_de_espera() == 15


# --- de punta a punta por el webhook ---

class EnviadorRegistra(Enviador):
    def __init__(self):
        self.salientes = []

    def enviar(self, canal, destinatario, texto):
        raise AssertionError("debía usar enviar_saliente")

    def enviar_saliente(self, canal, destinatario, saliente):
        self.salientes.append(saliente)
        return True


def test_el_webhook_usa_el_agente_langchain_y_envia_su_respuesta(session, cache, catalogo):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_proveedor] = lambda: None
    app.dependency_overrides[get_modelo_chat] = lambda: modelo(AIMessage("¡Hola! ¿Qué joya buscas?"))
    falso = EnviadorRegistra()
    app.dependency_overrides[get_enviador] = lambda: falso
    try:
        r = TestClient(app).post("/webhook/meta", json=_payload_texto("hola", wamid="wamid.lc"))
    finally:
        app.dependency_overrides.clear()
    assert r.json()["enviadas"] == 1
    assert falso.salientes[0].texto == "¡Hola! ¿Qué joya buscas?"
