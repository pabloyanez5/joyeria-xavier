import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente.servicio import atender_mensaje
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador, ErrorMeta
from app.models import Cliente, Mensaje, TransicionConversacion
from app.seed import cargar
from app.webhook import get_enviador


class EnviadorFalso(Enviador):
    def __init__(self, falla=False, acepta=True):
        self.enviados = []
        self.falla = falla
        self.acepta = acepta

    def enviar(self, canal, destinatario, texto):
        if self.falla:
            raise ErrorMeta("Meta respondió 400: fuera de la ventana de 24 horas")
        if self.acepta:
            self.enviados.append((canal, destinatario, texto))
        return self.acepta


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def con_enviador(enviador):
    app.dependency_overrides[get_enviador] = lambda: enviador


def hablar(session, cache, texto, id_canal="593111", nombre=None):
    return atender_mensaje(session, cache, "whatsapp", id_canal, texto, nombre=nombre)


def escalada(session, cache, id_canal="593111"):
    hablar(session, cache, "quiero argollas de oro 18k talla 7", id_canal)
    return hablar(session, cache, "quiero hablar con un asesor", id_canal)


def test_sin_conversaciones_la_lista_esta_vacia(api):
    assert api.get("/conversaciones").json() == []


def test_la_lista_pone_primero_las_escaladas_y_resume_cada_una(api, session, cache):
    hablar(session, cache, "hola", id_canal="593222")
    resp = escalada(session, cache, id_canal="593111")
    lista = api.get("/conversaciones").json()
    assert [c["estado"] for c in lista] == ["escalada", "activa"]
    primera = lista[0]
    assert primera["id"] == resp.conversacion_id
    assert primera["canal"] == "whatsapp" and primera["total_mensajes"] == 4
    assert primera["ultimo_autor"] == "agente" and "asesor" in primera["ultimo_mensaje"]
    assert primera["ordenes_activas"] == 0


def test_la_lista_se_filtra_por_estado(api, session, cache):
    hablar(session, cache, "hola", id_canal="593222")
    escalada(session, cache)
    assert [c["estado"] for c in api.get("/conversaciones?estado=activa").json()] == ["activa"]
    assert api.get("/conversaciones?estado=otra").status_code == 422


def test_el_detalle_trae_ficha_historial_y_orden_sugerida(api, session, cache):
    cargar(session)
    c = escalada(session, cache)
    detalle = api.get(f"/conversaciones/{c.conversacion_id}").json()
    ficha = {i["etiqueta"]: i["valor"] for i in detalle["ficha"]}
    assert ficha["Joya"] == "Argollas" and ficha["Material"] == "oro"
    assert ficha["Quilataje"] == "18k" and ficha["Talla"] == "7"
    assert [m["autor"] for m in detalle["historial"]] == ["cliente", "agente", "cliente", "agente"]
    assert [t["estado_nuevo"] for t in detalle["transiciones"]] == ["activa", "escalada"]
    sugerida = detalle["orden_sugerida"]
    assert sugerida["cliente_id"] == detalle["cliente_id"]
    assert "Joya: Argollas" in sugerida["descripcion"] and "Talla: 7" in sugerida["descripcion"]
    assert f"conversación #{c.conversacion_id}" in sugerida["descripcion"]


def test_conversacion_inexistente(api):
    assert api.get("/conversaciones/999").status_code == 404
    assert api.post("/conversaciones/999/reactivar").status_code == 404


def test_reactivar_devuelve_la_conversacion_al_agente(api, session, cache):
    c = escalada(session, cache)
    assert hablar(session, cache, "hola").texto is None  # escalada: el agente calla
    r = api.post(f"/conversaciones/{c.conversacion_id}/reactivar")
    assert r.status_code == 200 and r.json()["estado"] == "activa"
    assert [t["estado_nuevo"] for t in r.json()["transiciones"]] == ["activa", "escalada", "activa"]
    assert hablar(session, cache, "hola").texto is not None  # vuelve a responder


def test_solo_se_reactiva_una_conversacion_escalada(api, session, cache):
    c = hablar(session, cache, "hola")
    assert api.post(f"/conversaciones/{c.conversacion_id}/reactivar").status_code == 409


def test_cerrar_termina_la_conversacion_y_la_siguiente_es_nueva(api, session, cache):
    c = hablar(session, cache, "hola")
    r = api.post(f"/conversaciones/{c.conversacion_id}/cerrar")
    assert r.json()["estado"] == "cerrada"
    assert api.post(f"/conversaciones/{c.conversacion_id}/cerrar").status_code == 409
    nueva = hablar(session, cache, "hola otra vez")
    assert nueva.conversacion_id != c.conversacion_id


def test_el_asesor_responde_por_el_canal_del_cliente_y_el_agente_se_calla(api, session, cache):
    c = hablar(session, cache, "hola")
    falso = EnviadorFalso()
    con_enviador(falso)
    r = api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "  Hola, soy Ana, de Joyería Xavier  "})
    assert r.status_code == 200
    assert falso.enviados == [("whatsapp", "593111", "Hola, soy Ana, de Joyería Xavier")]
    detalle = r.json()
    assert detalle["historial"][-1]["autor"] == "asesor"
    assert detalle["estado"] == "escalada"  # al intervenir una persona, el agente se calla
    assert hablar(session, cache, "gracias").texto is None


def test_si_meta_rechaza_el_mensaje_no_se_guarda(api, session, cache):
    c = hablar(session, cache, "hola")
    con_enviador(EnviadorFalso(falla=True))
    antes = len(session.scalars(select(Mensaje)).all())
    r = api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "Hola"})
    assert r.status_code == 502 and "24 horas" in r.json()["detail"]
    assert len(session.scalars(select(Mensaje)).all()) == antes
    assert api.get(f"/conversaciones/{c.conversacion_id}").json()["estado"] == "activa"


def test_responder_sin_envio_configurado_o_en_canal_no_soportado(api, session, cache):
    c = hablar(session, cache, "hola")
    r = api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "Hola"})
    assert r.status_code == 503
    con_enviador(EnviadorFalso(acepta=False))
    r = api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "Hola"})
    assert r.status_code == 422


def test_responder_valida_el_texto_y_el_estado(api, session, cache):
    c = hablar(session, cache, "hola")
    con_enviador(EnviadorFalso())
    assert api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "   "}).status_code == 422
    api.post(f"/conversaciones/{c.conversacion_id}/cerrar")
    assert api.post(f"/conversaciones/{c.conversacion_id}/responder", json={"texto": "Hola"}).status_code == 409


def test_la_ficha_muestra_el_motivo_solo_mientras_esta_escalada(api, session, cache):
    c = escalada(session, cache)
    cliente = session.scalar(select(Cliente))
    cliente.contexto_cualificacion = {**cliente.contexto_cualificacion, "motivo_escalamiento": "cliente molesto"}
    session.commit()
    assert api.get(f"/conversaciones/{c.conversacion_id}").json()["motivo_escalamiento"] == "cliente molesto"
    reactivada = api.post(f"/conversaciones/{c.conversacion_id}/reactivar").json()
    assert reactivada["motivo_escalamiento"] is None
    assert "motivo_escalamiento" not in session.scalar(select(Cliente)).contexto_cualificacion


def test_una_conversacion_sin_datos_tiene_ficha_vacia_y_orden_con_origen(api, session, cache):
    c = hablar(session, cache, "hola")
    detalle = api.get(f"/conversaciones/{c.conversacion_id}").json()
    assert detalle["ficha"] == []
    assert detalle["orden_sugerida"]["descripcion"].startswith("Origen: conversación #")
