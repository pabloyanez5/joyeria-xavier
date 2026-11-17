"""JOY-80 y JOY-81: ficha con varias joyas y cualificación completa del cliente."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402

from app.agente import intereses  # noqa: E402
from app.agente.servicio import atender_mensaje  # noqa: E402
from app.clientes import nombre_para_saludar, primer_nombre  # noqa: E402
from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cliente, Producto  # noqa: E402
from app.seed import cargar  # noqa: E402
from app.webhook import get_enviador  # noqa: E402
from tests.test_agente_langchain import llamada, modelo  # noqa: E402


@pytest.fixture
def catalogo(session):
    cargar(session)


def _enviar(session, cache, texto, m=None, nombre=None, accion=None):
    return atender_mensaje(
        session, cache, "whatsapp", "593999", texto, nombre=nombre, proveedor=None, modelo=m,
        accion=accion,
    )


def _cliente(session) -> Cliente:
    return session.scalar(select(Cliente))


def _sistema(m, turno=0) -> str:
    return m.recibidos[turno][0].content


# --- el contexto con varias joyas ---

def test_cada_joya_guarda_sus_propios_datos():
    c = intereses.anotar(None, categoria="Aretes", material="oro", presupuesto="400 dólares")
    c = intereses.anotar(c, categoria="Cadenas", presupuesto="800 dólares")
    assert intereses.lista(c) == [
        {"categoria": "Aretes", "material": "oro", "presupuesto": "400 dólares"},
        {"categoria": "Cadenas", "presupuesto": "800 dólares"},
    ]
    assert c["activo"] == 1


def test_al_volver_a_una_joya_se_retoman_sus_datos():
    c = intereses.anotar(None, categoria="Aretes", presupuesto="400 dólares")
    c = intereses.anotar(c, categoria="Cadenas", presupuesto="800 dólares")
    c = intereses.anotar(c, categoria="aretes")  # escrito distinto: es la misma joya
    assert c["activo"] == 0 and len(intereses.lista(c)) == 2
    assert intereses.activo(c) == {"categoria": "Aretes", "presupuesto": "400 dólares"}


def test_un_dato_sin_categoria_es_de_la_joya_de_la_que_se_habla():
    c = intereses.anotar(None, categoria="Aretes")
    c = intereses.anotar(c, categoria="Cadenas")
    c = intereses.anotar(c, talla="50 cm")
    assert "talla" not in intereses.lista(c)[0]
    assert intereses.lista(c)[1]["talla"] == "50 cm"


def test_la_copia_del_interes_activo_no_arrastra_datos_de_otra_joya():
    c = intereses.anotar(None, categoria="Aretes", material="oro", presupuesto="400 dólares")
    c = intereses.anotar(c, categoria="Cadenas")
    assert c["categoria"] == "Cadenas"
    assert "material" not in c and "presupuesto" not in c  # antes se quedaban los de los aretes


def test_una_ficha_antigua_se_lee_como_una_sola_joya_y_no_pierde_lo_demas():
    antigua = {"categoria": "Anillos", "material": "plata", "motivo_escalamiento": "lo pidió"}
    assert intereses.lista(antigua) == [{"categoria": "Anillos", "material": "plata"}]
    nueva = intereses.anotar(antigua, presupuesto="300 dólares")
    assert intereses.lista(nueva) == [
        {"categoria": "Anillos", "material": "plata", "presupuesto": "300 dólares"}
    ]
    assert nueva["motivo_escalamiento"] == "lo pidió"


def test_el_material_dicho_antes_que_la_joya_queda_en_la_misma_joya():
    c = intereses.anotar(None, material="oro")
    c = intereses.anotar(c, categoria="Anillos")
    assert intereses.lista(c) == [{"material": "oro", "categoria": "Anillos"}]


def test_se_puede_pedir_una_segunda_joya_de_la_misma_categoria():
    c = intereses.anotar(None, categoria="Anillos", material="oro")
    c = intereses.anotar(c, otra_joya=True, categoria="Anillos", material="plata")
    assert [i["material"] for i in intereses.lista(c)] == ["oro", "plata"]


def test_hay_un_tope_de_joyas_por_cliente():
    c = None
    for n in range(intereses.MAXIMO + 3):
        c = intereses.anotar(c, categoria=f"Joya {n}")
    assert len(intereses.lista(c)) == intereses.MAXIMO


def test_sin_datos_no_cambia_nada():
    assert intereses.anotar({"x": 1}, material="  ", talla=None) == {"x": 1}
    assert intereses.resumen(None) == "Todavía no hay joyas anotadas."


# --- el caso que observó el jurado: aretes de 400 y una cadena de 800 ---

def test_dos_joyas_en_la_misma_conversacion_no_mezclan_el_presupuesto(session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", categoria="Aretes", material="oro", presupuesto="400 dólares"),
        AIMessage("Anotado. ¿Para qué ocasión son los aretes?"),
        llamada("guardar_preferencias", categoria="Cadenas", presupuesto="800 dólares"),
        AIMessage("Listo, también la cadena. ¿De qué material la prefieres?"),
        AIMessage("Claro, volvamos a los aretes de oro."),
    )
    _enviar(session, cache, "quiero unos aretes de oro, mi presupuesto es de 400 dólares", m)
    _enviar(session, cache, "también quiero una cadena, con presupuesto de 800", m)
    contexto = _cliente(session).contexto_cualificacion
    assert intereses.lista(contexto) == [
        {"categoria": "Aretes", "material": "oro", "presupuesto": "400 dólares"},
        {"categoria": "Cadenas", "presupuesto": "800 dólares"},
    ]
    _enviar(session, cache, "mejor volvamos a los aretes", m)
    contexto = _cliente(session).contexto_cualificacion
    assert intereses.activo(contexto)["presupuesto"] == "400 dólares"
    assert len(intereses.lista(contexto)) == 2


def test_el_modelo_recibe_lo_que_ya_sabe_de_cada_joya(session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", categoria="Aretes", presupuesto="400 dólares"),
        AIMessage("Anotado."),
        AIMessage("Claro."),
    )
    _enviar(session, cache, "quiero unos aretes, tengo 400 dólares", m)
    _enviar(session, cache, "y también una cadena", m)
    memoria = _sistema(m, turno=2)
    assert "Lo que ya sabes de las joyas" in memoria
    assert "1. Joya: Aretes; Presupuesto: 400 dólares" in memoria
    assert "2. Joya: Cadenas (de esta se está hablando)" in memoria


def test_la_herramienta_devuelve_la_lista_de_joyas_al_modelo(session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", categoria="Anillos", talla="7", ocasion="aniversario"),
        AIMessage("Perfecto."),
    )
    _enviar(session, cache, "un anillo talla 7 para mi aniversario", m)
    salida = m.recibidos[1][-1].content  # lo que la herramienta le contestó al modelo
    assert "Joyas que le interesan al cliente" in salida
    assert "Talla: 7" in salida and "Ocasión: aniversario" in salida
    assert _cliente(session).talla == "7"


def test_tocar_una_joya_del_menu_anota_su_modelo(session, cache, catalogo):
    producto = session.scalar(select(Producto).where(Producto.categoria == "Anillos"))
    _enviar(session, cache, "", accion=f"prod:{producto.id}")
    assert intereses.activo(_cliente(session).contexto_cualificacion) == {
        "categoria": "Anillos", "modelo": producto.nombre,
    }


# --- cualificación: cómo prefiere que lo llamen (JOY-81) ---

def test_el_primer_nombre_sale_del_perfil_sin_adornos():
    assert primer_nombre("Pablo 🎸") == "Pablo"
    assert primer_nombre("maría fernanda") == "María"
    assert primer_nombre("🎸🎸") is None and primer_nombre(None) is None
    assert nombre_para_saludar(Cliente(nombre_perfil="Pablo 🎸", nombre_preferido="Pablito")) == "Pablito"


def test_pregunta_una_sola_vez_si_puede_llamarlo_por_el_nombre_del_perfil(session, cache):
    m = modelo(
        AIMessage("¡Hola! ¿Te puedo llamar {nombre} o prefieres otro nombre?"),
        AIMessage("¡Genial, {nombre}! ¿Qué joya buscas?"),
    )
    r = _enviar(session, cache, "hola", m, nombre="Pablo 🎸")
    assert "pregúntale si puedes llamarlo {nombre}" in _sistema(m, 0)
    assert "Pablo" not in _sistema(m, 0)  # el nombre real no viaja al modelo (RNF-09)
    assert r.texto == "¡Hola! ¿Te puedo llamar Pablo o prefieres otro nombre?"
    r = _enviar(session, cache, "sí, está bien", m)
    assert "pregúntale" not in _sistema(m, 1)
    assert r.texto == "¡Genial, Pablo! ¿Qué joya buscas?"


def test_sin_nombre_de_perfil_pregunta_como_prefiere_que_lo_llamen(session, cache):
    m = modelo(AIMessage("¡Hola! ¿Cómo prefieres que te llame?"))
    _enviar(session, cache, "hola", m)
    assert "pregúntale cómo prefiere que lo llames" in _sistema(m, 0)
    assert "{nombre}" not in _sistema(m, 0)


def test_si_acepta_el_nombre_del_perfil_queda_como_preferido(session, cache):
    m = modelo(
        AIMessage("¿Te puedo llamar {nombre}?"),
        llamada("guardar_preferencias", acepta_el_nombre=True),
        AIMessage("Perfecto, {nombre}."),
    )
    _enviar(session, cache, "hola", m, nombre="Pablo 🎸")
    r = _enviar(session, cache, "sí", m)
    cliente = _cliente(session)
    assert cliente.nombre_preferido == "Pablo" and r.texto == "Perfecto, Pablo."
    assert cliente.contexto_cualificacion["nombre_confirmado"] is True


def test_si_pide_otro_nombre_se_guarda_ese(session, cache):
    m = modelo(
        AIMessage("¿Te puedo llamar {nombre}?"),
        llamada("guardar_preferencias", nombre="Pablito"),
        AIMessage("Claro, {nombre}."),
    )
    _enviar(session, cache, "hola", m, nombre="Pablo 🎸")
    r = _enviar(session, cache, "dime Pablito", m)
    assert _cliente(session).nombre_preferido == "Pablito" and r.texto == "Claro, Pablito."


def test_la_marca_del_nombre_nunca_se_guarda_como_nombre(session, cache):
    m = modelo(
        AIMessage("¿Te puedo llamar {nombre}?"),
        llamada("guardar_preferencias", nombre="{nombre}"),
        AIMessage("Listo."),
    )
    _enviar(session, cache, "hola", m, nombre="Pablo 🎸")
    _enviar(session, cache, "sí", m)
    assert _cliente(session).nombre_preferido == "Pablo"


# --- lo que ve el asesor en el panel ---

@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_enviador, None)


def test_la_ficha_muestra_cada_joya_por_separado_y_los_datos_del_cliente(api, session, cache, catalogo):
    m = modelo(
        llamada("guardar_preferencias", categoria="Aretes", material="oro", presupuesto="400 dólares"),
        AIMessage("Anotado."),
        llamada("guardar_preferencias", categoria="Cadenas", presupuesto="800 dólares"),
        llamada("consultar_catalogo", categoria="Cadenas"),
        AIMessage("Tenemos cadenas desde $54.48."),
    )
    r = _enviar(session, cache, "quiero aretes de oro por 400 dólares", m, nombre="Ana Pérez")
    _enviar(session, cache, "y una cadena de 800, ¿cuánto cuestan?", m)
    detalle = api.get(f"/conversaciones/{r.conversacion_id}").json()

    cliente = {i["etiqueta"]: i["valor"] for i in detalle["datos_del_cliente"]}
    assert cliente["Nombre preferido"] == "Ana (de su perfil, sin confirmar)"
    assert cliente["Canal"] == "whatsapp"
    assert cliente["Intención detectada"] == "Ver el catálogo o cotizar"

    aretes, cadena = detalle["intereses"]
    assert (aretes["numero"], aretes["titulo"], aretes["activo"]) == (1, "Aretes de oro", False)
    assert (cadena["numero"], cadena["titulo"], cadena["activo"]) == (2, "Cadenas", True)
    assert {i["etiqueta"]: i["valor"] for i in aretes["datos"]}["Presupuesto"] == "400 dólares"
    assert {i["etiqueta"]: i["valor"] for i in cadena["datos"]}["Presupuesto"] == "800 dólares"
    assert "Presupuesto: 400 dólares" in aretes["descripcion_de_orden"]
    assert "800" not in aretes["descripcion_de_orden"]
    # La ficha y la orden sugerida siguen siendo las de la joya de la que se habla.
    assert {i["etiqueta"]: i["valor"] for i in detalle["ficha"]}["Joya"] == "Cadenas"
    assert "Joya: Cadenas" in detalle["orden_sugerida"]["descripcion"]


def test_pedir_un_asesor_queda_como_la_intencion_detectada(api, session, cache):
    r = _enviar(session, cache, "quiero ver anillos")
    _enviar(session, cache, "quiero hablar con un asesor")
    detalle = api.get(f"/conversaciones/{r.conversacion_id}").json()
    cliente = {i["etiqueta"]: i["valor"] for i in detalle["datos_del_cliente"]}
    assert cliente["Intención detectada"] == "Hablar con un asesor"


def test_un_saludo_no_borra_la_intencion_anterior(api, session, cache):
    r = _enviar(session, cache, "quiero cotizar un anillo")
    _enviar(session, cache, "hola")
    detalle = api.get(f"/conversaciones/{r.conversacion_id}").json()
    cliente = {i["etiqueta"]: i["valor"] for i in detalle["datos_del_cliente"]}
    assert cliente["Intención detectada"] == "Cotizar una joya"
