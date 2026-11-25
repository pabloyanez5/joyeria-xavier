"""JOY-84 · Asignación de la conversación escalada a un asesor (RF-01, CU-6).

Criterios: con dos asesores, dos escalamientos seguidos se reparten uno a cada uno; la
reasignación queda registrada; pruebas automáticas del reparto.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agente.servicio import atender_mensaje
from app.db import get_session
from app.main import app
from app.meta_envio import Enviador
from app.models import AsignacionConversacion, Conversacion, Usuario
from app.webhook import get_enviador
from tests.conftest import entrar_como


class EnviadorQueAcepta(Enviador):
    def enviar(self, canal, destinatario, texto):
        return True


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: EnviadorQueAcepta()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def asesores(session):
    ana = Usuario(nombre="Ana", email="ana@x.com", rol="asesor")
    luis = Usuario(nombre="Luis", email="luis@x.com", rol="asesor")
    marta = Usuario(nombre="Marta", email="marta@x.com", rol="taller")
    session.add_all([ana, luis, marta])
    session.commit()
    return {"ana": ana, "luis": luis, "marta": marta}


def escalar(session, cache, id_canal: str) -> Conversacion:
    r = atender_mensaje(session, cache, "whatsapp", id_canal, "quiero hablar con un asesor")
    assert r.escalada
    return session.get(Conversacion, r.conversacion_id)


def _registro(session, conversacion_id):
    return session.scalars(
        select(AsignacionConversacion)
        .where(AsignacionConversacion.conversacion_id == conversacion_id)
        .order_by(AsignacionConversacion.id)
    ).all()


# --- reparto automático ---

def test_dos_escalamientos_seguidos_se_reparten_uno_a_cada_asesor(session, cache, asesores):
    primera = escalar(session, cache, "593001")
    segunda = escalar(session, cache, "593002")
    assert {primera.asesor_id, segunda.asesor_id} == {asesores["ana"].id, asesores["luis"].id}
    assert [r.tipo for r in _registro(session, primera.id)] == ["automatica"]


def test_va_al_asesor_con_menos_conversaciones_abiertas(session, cache, asesores):
    for id_canal in ("593001", "593002", "593003"):
        escalar(session, cache, id_canal)
    asignadas = [c.asesor_id for c in session.scalars(select(Conversacion).order_by(Conversacion.id))]
    assert sorted(asignadas.count(asesores[a].id) for a in ("ana", "luis")) == [1, 2]
    # Si uno cierra las suyas, la siguiente le toca a él.
    for c in session.scalars(select(Conversacion).where(Conversacion.asesor_id == asesores["luis"].id)):
        c.estado = "cerrada"
    session.commit()
    cuarta = escalar(session, cache, "593004")
    assert cuarta.asesor_id == asesores["luis"].id


def test_el_taller_y_los_asesores_inactivos_no_reciben_conversaciones(session, cache, asesores):
    asesores["luis"].activo = False
    session.commit()
    for id_canal in ("593001", "593002"):
        assert escalar(session, cache, id_canal).asesor_id == asesores["ana"].id


def test_sin_asesores_activos_queda_en_la_cola_general(session, cache, asesores):
    asesores["ana"].activo = asesores["luis"].activo = False
    session.commit()
    assert escalar(session, cache, "593001").asesor_id is None


def test_si_vuelve_a_escalar_la_sigue_atendiendo_el_mismo(api, session, cache, asesores):
    c = escalar(session, cache, "593001")
    asignado = c.asesor_id
    entrar_como(asesores["ana"])
    api.post(f"/conversaciones/{c.id}/reactivar")
    escalar(session, cache, "593002")  # otra conversación mientras tanto
    escalar(session, cache, "593001")
    session.refresh(c)
    assert c.asesor_id == asignado


# --- tomar y reasignar ---

def test_un_asesor_toma_una_conversacion_y_queda_registrado(api, session, cache, asesores):
    c = escalar(session, cache, "593001")
    otro = asesores["luis"] if c.asesor_id == asesores["ana"].id else asesores["ana"]
    entrar_como(otro)
    r = api.post(f"/conversaciones/{c.id}/tomar")
    assert r.status_code == 200 and r.json()["asesor"] == otro.nombre
    ultimo = _registro(session, c.id)[-1]
    assert (ultimo.tipo, ultimo.asesor_id, ultimo.usuario_id) == ("tomada", otro.id, otro.id)


def test_se_reasigna_a_otro_asesor_o_a_la_cola_general(api, session, cache, asesores):
    c = escalar(session, cache, "593001")
    entrar_como(asesores["ana"])
    r = api.post(f"/conversaciones/{c.id}/asignar", json={"asesor_id": asesores["luis"].id})
    assert r.json()["asesor"] == "Luis"
    r = api.post(f"/conversaciones/{c.id}/asignar", json={"asesor_id": None})
    assert r.json()["asesor"] is None
    historial = api.get(f"/conversaciones/{c.id}/asignaciones").json()
    assert [(h["tipo"], h["asesor"], h["usuario"]) for h in historial[-2:]] == [
        ("reasignada", "Luis", "Ana"),
        ("liberada", None, "Ana"),
    ]


def test_no_se_asigna_al_taller_a_un_inactivo_ni_una_cerrada(api, session, cache, asesores):
    c = escalar(session, cache, "593001")
    entrar_como(asesores["ana"])
    assert api.post(f"/conversaciones/{c.id}/asignar", json={"asesor_id": asesores["marta"].id}).status_code == 422
    asesores["luis"].activo = False
    session.commit()
    assert api.post(f"/conversaciones/{c.id}/asignar", json={"asesor_id": asesores["luis"].id}).status_code == 422
    api.post(f"/conversaciones/{c.id}/cerrar")
    assert api.post(f"/conversaciones/{c.id}/tomar").status_code == 409


def test_si_el_asesor_interviene_por_su_cuenta_la_conversacion_queda_a_su_cargo(api, session, cache, asesores):
    r = atender_mensaje(session, cache, "whatsapp", "593001", "hola")
    entrar_como(asesores["luis"])
    detalle = api.post(f"/conversaciones/{r.conversacion_id}/responder", json={"texto": "Hola, soy Luis"}).json()
    assert detalle["estado"] == "escalada" and detalle["asesor"] == "Luis"
    assert _registro(session, r.conversacion_id)[-1].tipo == "tomada"


# --- lo que ve el panel ---

def test_la_bandeja_muestra_quien_atiende_y_filtra_las_mias(api, session, cache, asesores):
    a = escalar(session, cache, "593001")
    b = escalar(session, cache, "593002")
    de_ana = a if a.asesor_id == asesores["ana"].id else b
    entrar_como(asesores["ana"])
    todas = api.get("/conversaciones").json()
    assert {c["asesor"] for c in todas} == {"Ana", "Luis"}
    mias = api.get("/conversaciones", params={"mias": True}).json()
    assert [c["id"] for c in mias] == [de_ana.id]


def test_la_lista_de_asesores_trae_su_carga(api, session, cache, asesores):
    escalar(session, cache, "593001")
    escalar(session, cache, "593002")
    entrar_como(asesores["ana"])
    lista = api.get("/conversaciones/asesores/activos").json()
    assert [(x["nombre"], x["carga"]) for x in lista] == [("Ana", 1), ("Luis", 1)]
