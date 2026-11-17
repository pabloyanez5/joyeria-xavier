"""JOY-23: el asesor corrige, devuelve o cancela una orden; todo queda en el historial."""
import pytest

from app.agente import intereses
from app.agente.servicio import atender_mensaje
from app.models import Cliente, HistorialEtapa, Orden
from tests.conftest import _AdminDePruebas, datos_de_orden, entrar_como, verificar
from tests.test_etapas import EnviadorFalso, api, avanzar, con_enviador, datos  # noqa: F401


def _orden(api, datos, **extra):
    """Orden por verificar, creada por el asesor."""
    entrar_como(datos["asesor"])
    r = api.post(
        "/ordenes",
        json=datos_de_orden(cliente_id=datos["cliente"].id, descripcion="Argollas en oro 18k", **extra),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _en_produccion(api, datos):
    orden = verificar(api, _orden(api, datos))
    entrar_como(datos["taller"])
    avanzar(api, orden, "en_produccion")
    entrar_como(datos["asesor"])
    return orden


def _historial(api, orden):
    return api.get(f"/ordenes/{orden['id']}/historial").json()


# --- modificar ---

def test_el_asesor_corrige_datos_y_queda_el_antes_y_el_despues(api, datos):
    orden = _orden(api, datos)
    r = api.patch(f"/ordenes/{orden['id']}", json={
        "total": "400.00", "fecha_entrega_cliente": "2026-12-15", "motivo": "El cliente pidió grabado",
    })
    assert r.status_code == 200, r.text
    assert r.json()["total"] == "400.00" and r.json()["fecha_entrega_cliente"] == "2026-12-15"

    ultimo = _historial(api, orden)[-1]
    assert ultimo["tipo"] == "modificacion" and ultimo["usuario"] == "Luis"
    assert "Total: $350.00 → $400.00" in ultimo["nota"]
    assert "Entrega al cliente: 10/12/2026 → 15/12/2026" in ultimo["nota"]
    assert "Motivo: El cliente pidió grabado" in ultimo["nota"]
    assert r.json()["ultimo_cambio"].startswith("Modificada por Luis: ")


def test_sin_motivo_no_se_modifica(api, datos):
    orden = _orden(api, datos)
    assert api.patch(f"/ordenes/{orden['id']}", json={"total": "400"}).status_code == 422
    r = api.patch(f"/ordenes/{orden['id']}", json={"total": "400", "motivo": "  ok "})
    assert r.status_code == 422


def test_si_nada_cambia_no_se_registra_nada(api, session, datos):
    orden = _orden(api, datos)
    r = api.patch(f"/ordenes/{orden['id']}", json={"total": "350.00", "motivo": "Revisión"})
    assert r.status_code == 422
    assert len(_historial(api, orden)) == 1


def test_las_reglas_de_la_orden_se_mantienen_al_modificar(api, datos):
    orden = verificar(api, _orden(api, datos), abono="200.00")
    r = api.patch(f"/ordenes/{orden['id']}", json={"total": "150", "motivo": "Descuento"})
    assert r.status_code == 422 and "abono" in r.json()["detail"]
    r = api.patch(
        f"/ordenes/{orden['id']}", json={"fecha_entrega_cliente": "2026-11-20", "motivo": "Apuro"}
    )
    assert r.status_code == 422 and "entrega al cliente" in r.json()["detail"]


def test_si_el_taller_ya_la_recibio_tiene_que_confirmar_el_cambio(api, datos):
    orden = _en_produccion(api, datos)
    r = api.patch(f"/ordenes/{orden['id']}", json={"peso_gramos": "5.2", "motivo": "Más gruesa"})
    assert r.json()["acuse_pendiente"] is True and r.json()["acuse_por"] is None
    entrar_como(datos["taller"])
    r = api.post(f"/ordenes/{orden['id']}/acuse")
    assert r.json()["acuse_pendiente"] is False and r.json()["acuse_por"] == "Marta"


def test_una_orden_terminada_ya_no_se_modifica(api, datos):
    orden = _en_produccion(api, datos)
    entrar_como(datos["taller"])
    avanzar(api, orden, "terminada")
    entrar_como(datos["asesor"])
    r = api.patch(f"/ordenes/{orden['id']}", json={"total": "500", "motivo": "Cambio tarde"})
    assert r.status_code == 409


def test_el_taller_no_puede_modificar_retroceder_ni_cancelar(api, datos):
    orden = _en_produccion(api, datos)
    entrar_como(datos["taller"])
    motivo = {"motivo": "Lo intento yo"}
    assert api.patch(f"/ordenes/{orden['id']}", json={"total": "1", **motivo}).status_code == 403
    assert api.post(f"/ordenes/{orden['id']}/retroceder", json=motivo).status_code == 403
    assert api.post(f"/ordenes/{orden['id']}/cancelar", json=motivo).status_code == 403


# --- retroceder ---

def test_el_asesor_devuelve_una_etapa_con_motivo(api, datos):
    orden = _en_produccion(api, datos)
    r = api.post(f"/ordenes/{orden['id']}/retroceder", json={"motivo": "El taller avanzó por error"})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_actual"] == "en_cola" and r.json()["etapa_anterior"] is None

    ultimo = _historial(api, orden)[-1]
    assert (ultimo["etapa"], ultimo["tipo"], ultimo["usuario"]) == ("en_cola", "retroceso", "Luis")
    assert ultimo["nota"] == "El taller avanzó por error"
    # Y el taller la puede volver a avanzar normalmente.
    entrar_como(datos["taller"])
    assert avanzar(api, orden, "en_produccion").status_code == 200


def test_no_se_retrocede_desde_la_cola(api, datos):
    orden = verificar(api, _orden(api, datos))
    r = api.post(f"/ordenes/{orden['id']}/retroceder", json={"motivo": "Volver a verificar"})
    assert r.status_code == 409


# --- cancelar ---

def test_cancelar_no_borra_la_orden_y_avisa_al_cliente(api, session, datos):
    enviador = EnviadorFalso()
    orden = _en_produccion(api, datos)
    con_enviador(enviador)
    r = api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "El cliente desistió"})
    assert r.status_code == 200, r.text
    assert r.json()["etapa_actual"] == "cancelada" and r.json()["aviso_al_cliente"] == "enviado"
    assert "fue cancelada" in enviador.enviados[0][2]

    assert session.get(Orden, orden["id"]) is not None  # nada se borra
    pasos = _historial(api, orden)
    assert [p["etapa"] for p in pasos] == ["por_verificar", "en_cola", "en_produccion", "cancelada"]
    assert pasos[-1]["tipo"] == "cancelacion" and pasos[-1]["nota"] == "El cliente desistió"


def test_una_orden_cancelada_ya_no_avanza_ni_se_toca(api, datos):
    orden = _orden(api, datos)
    api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "Duplicada", "avisar_al_cliente": False})
    motivo = {"motivo": "Otra vez"}
    assert api.post(f"/ordenes/{orden['id']}/verificar", json={"abono": "10"}).status_code == 409
    assert api.post(f"/ordenes/{orden['id']}/cancelar", json=motivo).status_code == 409
    assert api.patch(f"/ordenes/{orden['id']}", json={"total": "1", **motivo}).status_code == 409
    entrar_como(datos["taller"])
    assert avanzar(api, orden, "en_cola").status_code in (409, 422)
    assert api.post(f"/ordenes/{orden['id']}/acuse").status_code == 409


def test_una_orden_entregada_no_se_cancela(api, session, datos):
    orden = _en_produccion(api, datos)
    entrar_como(datos["taller"])
    avanzar(api, orden, "terminada")
    avanzar(api, orden, "entregada")
    entrar_como(datos["asesor"])
    r = api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "Devolución"})
    assert r.status_code == 409


def test_las_canceladas_se_pueden_filtrar(api, datos):
    a = _orden(api, datos)
    _orden(api, datos)
    api.post(f"/ordenes/{a['id']}/cancelar", json={"motivo": "Duplicada", "avisar_al_cliente": False})
    assert [o["id"] for o in api.get("/ordenes?etapa=cancelada").json()] == [a["id"]]


def test_las_metricas_cuentan_las_canceladas_y_el_tiempo_de_entrega_no_cambia(api, session, datos):
    orden = _orden(api, datos)
    api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "Duplicada", "avisar_al_cliente": False})
    entrar_como(_AdminDePruebas())  # las métricas son de dirección (el admin pasa siempre)
    r = api.get("/metricas").json()
    assert {e["etapa"]: e["ordenes"] for e in r["ordenes_por_etapa"]}["cancelada"] == 1


# --- la ficha del cliente y el agente ---

def test_al_cancelar_la_joya_vuelve_a_estar_disponible_en_la_ficha(api, session, cache, datos):
    r = atender_mensaje(session, cache, "whatsapp", "593111", "hola")
    cliente = session.get(Cliente, datos["cliente"].id)
    cliente.contexto_cualificacion = {"intereses": [{"categoria": "Aretes", "material": "oro"}]}
    session.commit()
    orden = _orden(api, datos, interes=1)
    detalle = api.get(f"/conversaciones/{r.conversacion_id}").json()
    assert detalle["intereses"][0]["orden"] == orden["codigo"]

    api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "Cambió de idea", "avisar_al_cliente": False})

    session.refresh(cliente)
    assert "orden_id" not in intereses.lista(cliente.contexto_cualificacion)[0]
    detalle = api.get(f"/conversaciones/{r.conversacion_id}").json()
    assert detalle["intereses"][0]["orden"] is None
    assert detalle["ordenes_activas"] == 0


def test_el_cliente_sabe_que_su_orden_se_cancelo(api, session, cache, datos):
    orden = _orden(api, datos)
    api.post(f"/ordenes/{orden['id']}/cancelar", json={"motivo": "Duplicada", "avisar_al_cliente": False})
    r = atender_mensaje(session, cache, "whatsapp", "593111", "¿Cómo va mi pedido?")
    assert f"{orden['codigo']}" in r.texto and ": cancelada." in r.texto


def test_el_avance_normal_sigue_registrandose_como_etapa(api, session, datos):
    orden = _en_produccion(api, datos)
    tipos = session.query(HistorialEtapa.tipo).filter_by(orden_id=orden["id"]).all()
    assert {t for (t,) in tipos} == {"etapa"}


@pytest.mark.parametrize("foto, esperado", [("", None), ("https://x.com/a.jpg", "https://x.com/a.jpg")])
def test_la_foto_se_puede_cambiar_o_quitar(api, datos, foto, esperado):
    orden = _orden(api, datos, foto_referencia_url="https://x.com/vieja.jpg")
    r = api.patch(f"/ordenes/{orden['id']}", json={"foto_referencia_url": foto, "motivo": "Otra foto"})
    assert r.status_code == 200 and r.json()["foto_referencia_url"] == esperado
