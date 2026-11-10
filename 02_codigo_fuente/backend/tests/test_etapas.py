import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente.servicio import atender_mensaje
from app.cache import get_cache
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador, ErrorMeta
from app.models import Cliente, HistorialEtapa, Mensaje, Orden, Usuario
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
def api(session, cache):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_cache] = lambda: cache
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def con_enviador(enviador):
    app.dependency_overrides[get_enviador] = lambda: enviador


@pytest.fixture
def datos(session):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    taller = Usuario(nombre="Marta", email="marta@x.com", rol="taller")
    asesor = Usuario(nombre="Luis", email="luis@x.com", rol="asesor")
    session.add_all([cliente, taller, asesor])
    session.commit()
    return {"cliente": cliente, "taller": taller, "asesor": asesor}


def nueva_orden(api, datos):
    return api.post(
        "/ordenes", json={"cliente_id": datos["cliente"].id, "descripcion": "Argollas en oro 18k"}
    ).json()


def avanzar(api, orden, etapa, **extra):
    return api.post(f"/ordenes/{orden['id']}/etapa", json={"etapa": etapa, **extra})


def test_una_orden_nueva_propone_la_etapa_siguiente(api, datos):
    orden = nueva_orden(api, datos)
    assert orden["etapa_actual"] == "en_cola" and orden["siguiente_etapa"] == "en_produccion"


def test_el_taller_avanza_etapa_por_etapa_hasta_la_entrega(api, session, datos):
    orden = nueva_orden(api, datos)
    for etapa, siguiente in [
        ("en_produccion", "terminada"),
        ("terminada", "entregada"),
        ("entregada", None),
    ]:
        r = avanzar(api, orden, etapa, usuario_id=datos["taller"].id)
        assert r.status_code == 200
        assert r.json()["etapa_actual"] == etapa and r.json()["siguiente_etapa"] == siguiente
    historial = api.get(f"/ordenes/{orden['id']}/historial").json()
    assert [h["etapa"] for h in historial] == ["en_cola", "en_produccion", "terminada", "entregada"]
    assert historial[1]["usuario"] == "Marta" and historial[0]["usuario"] is None


def test_salir_de_la_cola_cuenta_como_acuse_del_taller(api, datos):
    orden = nueva_orden(api, datos)
    assert orden["acuse_pendiente"] is True
    r = avanzar(api, orden, "en_produccion").json()
    assert r["acuse_pendiente"] is False
    assert api.get("/ordenes/cola").json() == []


def test_no_se_puede_saltar_ni_retroceder_etapas(api, datos):
    orden = nueva_orden(api, datos)
    saltar = avanzar(api, orden, "terminada")
    assert saltar.status_code == 409 and "en_produccion" in saltar.json()["detail"]
    avanzar(api, orden, "en_produccion")
    assert avanzar(api, orden, "en_cola").status_code == 409
    assert avanzar(api, orden, "inventada").status_code == 422


def test_una_orden_entregada_ya_no_avanza(api, datos):
    orden = nueva_orden(api, datos)
    for etapa in ("en_produccion", "terminada", "entregada"):
        avanzar(api, orden, etapa)
    r = avanzar(api, orden, "entregada")
    assert r.status_code == 409 and "entregada" in r.json()["detail"]


def test_orden_o_usuario_inexistente_y_rol_incorrecto(api, datos):
    assert api.post("/ordenes/999/etapa", json={"etapa": "en_produccion"}).status_code == 404
    orden = nueva_orden(api, datos)
    assert avanzar(api, orden, "en_produccion", usuario_id=999).status_code == 404
    assert avanzar(api, orden, "en_produccion", usuario_id=datos["asesor"].id).status_code == 422


def test_el_cliente_recibe_un_aviso_por_su_canal(api, session, datos):
    falso = EnviadorFalso()
    con_enviador(falso)
    orden = nueva_orden(api, datos)
    r = avanzar(api, orden, "en_produccion").json()
    assert r["aviso_al_cliente"] == "enviado" and r["detalle_aviso"] is None
    canal, destino, texto = falso.enviados[0]
    assert (canal, destino) == ("whatsapp", "593111")
    assert orden["codigo"] in texto and "producción" in texto


def test_el_aviso_queda_en_la_conversacion_abierta_del_cliente(api, session, cache, datos):
    atender_mensaje(session, cache, "whatsapp", "593111", "hola")  # abre la conversación
    con_enviador(EnviadorFalso())
    orden = nueva_orden(api, datos)
    avanzar(api, orden, "en_produccion")
    ultimo = session.scalars(select(Mensaje).order_by(Mensaje.id.desc())).first()
    assert ultimo.autor == "sistema" and ultimo.direccion == "saliente"
    assert orden["codigo"] in ultimo.contenido


def test_el_taller_puede_avanzar_sin_avisar(api, datos):
    falso = EnviadorFalso()
    con_enviador(falso)
    orden = nueva_orden(api, datos)
    r = avanzar(api, orden, "en_produccion", avisar_al_cliente=False).json()
    assert r["aviso_al_cliente"] == "omitido" and falso.enviados == []


def test_si_meta_rechaza_el_aviso_la_orden_igual_avanza(api, session, datos):
    con_enviador(EnviadorFalso(falla=True))
    orden = nueva_orden(api, datos)
    r = avanzar(api, orden, "en_produccion")
    assert r.status_code == 200
    assert r.json()["aviso_al_cliente"] == "no_enviado" and "24 horas" in r.json()["detalle_aviso"]
    assert session.get(Orden, orden["id"]).etapa_actual == "en_produccion"


def test_sin_envio_configurado_o_en_canal_no_soportado_no_falla(api, datos):
    orden = nueva_orden(api, datos)
    r = avanzar(api, orden, "en_produccion").json()
    assert r["aviso_al_cliente"] == "omitido" and "no está configurado" in r["detalle_aviso"]
    con_enviador(EnviadorFalso(acepta=False))
    r = avanzar(api, orden, "terminada").json()
    assert r["aviso_al_cliente"] == "omitido" and "todavía no está disponible" in r["detalle_aviso"]


def test_cada_etapa_tiene_su_aviso():
    from app.ordenes import AVISOS_AL_CLIENTE, ETAPAS

    assert set(AVISOS_AL_CLIENTE) == set(ETAPAS[1:])


def test_lista_de_ordenes_con_filtro_por_etapa(api, datos):
    a = nueva_orden(api, datos)
    b = nueva_orden(api, datos)
    avanzar(api, a, "en_produccion")
    todas = api.get("/ordenes").json()
    assert [o["id"] for o in todas] == [b["id"], a["id"]]  # la más reciente primero
    assert [o["id"] for o in api.get("/ordenes?etapa=en_produccion").json()] == [a["id"]]
    assert api.get("/ordenes?etapa=otra").status_code == 422


def test_historial_de_orden_inexistente(api):
    assert api.get("/ordenes/999/historial").status_code == 404


def test_el_agente_informa_la_etapa_actual_al_cliente(api, session, cache, datos):
    orden = nueva_orden(api, datos)
    avanzar(api, orden, "en_produccion")
    from tests.test_agente_langchain import ModeloGuion, llamada
    from langchain_core.messages import AIMessage, ToolMessage

    modelo = ModeloGuion(
        respuestas=[llamada("consultar_orden"), AIMessage("Tu orden está en producción.")],
        recibidos=[],
        falla=False,
    )
    atender_mensaje(session, cache, "whatsapp", "593111", "cómo va mi pedido?", modelo=modelo)
    salida = [m for m in modelo.recibidos[1] if isinstance(m, ToolMessage)][0].content
    assert orden["codigo"] in salida and "en produccion" in salida
