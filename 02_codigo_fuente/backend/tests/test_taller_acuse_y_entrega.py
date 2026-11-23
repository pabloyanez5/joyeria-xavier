"""Validación de JOY-18 (US-10) y JOY-19 (US-11): el taller ve sus órdenes, confirma el acuse y
actualiza las etapas; cada paso queda con responsable y hora, y la entrega física se registra.

Criterios de aceptación en Jira:
- JOY-18: «Taller confirma acuse; orden pasa a 'en producción' con marca de tiempo y usuario
  responsable.» El acuse guarda el usuario de taller y la hora.
- JOY-19: «Transición de etapa registrada con marca de tiempo; historial completo visible.» Cada
  transición guarda responsable y hora; se añade el registro de la entrega física (fecha y quién
  entrega).
"""
from datetime import datetime, timedelta, timezone

from app.models import Usuario
from tests.conftest import entrar_como
from tests.test_etapas import EnviadorFalso, api, avanzar, con_enviador, datos, nueva_orden  # noqa: F401


def _hace_un_momento(iso: str) -> bool:
    momento = datetime.fromisoformat(iso)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return abs(datetime.now(timezone.utc) - momento) < timedelta(minutes=1)


def _en_produccion_con_cambio_pendiente(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    api.post(f"/ordenes/{orden['id']}/acuse")
    entrar_como(datos["asesor"])
    r = api.patch(f"/ordenes/{orden['id']}", json={"peso_gramos": "5.10", "motivo": "Más gruesa"})
    assert r.json()["acuse_pendiente"] is True
    entrar_como(datos["taller"])
    return orden


# --- JOY-18 · US-10: ver las órdenes asignadas y confirmar el acuse ---

def test_el_taller_ve_las_ordenes_que_le_llegan(api, datos):
    a = nueva_orden(api, datos)
    b = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    cola = api.get("/ordenes/cola").json()
    assert [o["id"] for o in cola] == [a["id"], b["id"]]  # la más antigua primero
    assert all(o["acuse_pendiente"] for o in cola)


def test_confirmar_el_acuse_pasa_la_orden_a_produccion_con_responsable_y_hora(api, datos):
    enviador = EnviadorFalso()
    con_enviador(enviador)
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])

    r = api.post(f"/ordenes/{orden['id']}/acuse")
    assert r.status_code == 200, r.text
    datos_orden = r.json()
    assert datos_orden["etapa_actual"] == "en_produccion"
    assert datos_orden["acuse_pendiente"] is False
    assert datos_orden["acuse_por"] == "Marta" and _hace_un_momento(datos_orden["acuse_en"])

    ultimo = api.get(f"/ordenes/{orden['id']}/historial").json()[-1]
    assert (ultimo["etapa"], ultimo["usuario"]) == ("en_produccion", "Marta")
    assert _hace_un_momento(ultimo["creado_en"])
    # El cliente se entera por su canal, igual que con cualquier avance.
    assert datos_orden["aviso_al_cliente"] == "enviado" and "producción" in enviador.enviados[-1][2]
    assert api.get("/ordenes/cola").json() == []


def test_el_acuse_se_puede_confirmar_sin_avisar_al_cliente(api, datos):
    enviador = EnviadorFalso()
    con_enviador(enviador)
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    r = api.post(f"/ordenes/{orden['id']}/acuse", json={"avisar_al_cliente": False}).json()
    assert r["etapa_actual"] == "en_produccion" and r["aviso_al_cliente"] == "omitido"
    assert enviador.enviados == []


def test_si_el_asesor_cambio_la_orden_en_produccion_el_acuse_solo_confirma_que_la_vio(api, datos):
    orden = _en_produccion_con_cambio_pendiente(api, datos)
    r = api.post(f"/ordenes/{orden['id']}/acuse").json()
    assert r["etapa_actual"] == "en_produccion"  # no salta a terminada
    assert r["acuse_pendiente"] is False and r["acuse_por"] == "Marta"
    assert r["aviso_al_cliente"] == "omitido"


def test_confirmar_dos_veces_no_cambia_nada(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    primera = api.post(f"/ordenes/{orden['id']}/acuse").json()
    segunda = api.post(f"/ordenes/{orden['id']}/acuse").json()
    assert segunda["etapa_actual"] == "en_produccion" and segunda["acuse_en"] == primera["acuse_en"]
    historial = api.get(f"/ordenes/{orden['id']}/historial").json()
    assert [h["etapa"] for h in historial].count("en_produccion") == 1


def test_solo_el_taller_confirma_el_acuse(api, session, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["asesor"])
    assert api.post(f"/ordenes/{orden['id']}/acuse").status_code == 403
    jefa = Usuario(nombre="Dir", email="dir@x.com", rol="direccion")
    session.add(jefa)
    session.commit()
    entrar_como(jefa)
    assert api.post(f"/ordenes/{orden['id']}/acuse").status_code == 403


# --- JOY-19 · US-11: actualizar la etapa, historial completo y entrega física ---

def test_cada_transicion_queda_con_responsable_y_hora_y_el_historial_es_completo(api, datos):
    entrar_como(datos["asesor"])
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    api.post(f"/ordenes/{orden['id']}/acuse")
    avanzar(api, orden, "terminada")
    entrar_como(datos["asesor"])
    avanzar(api, orden, "entregada")

    historial = api.get(f"/ordenes/{orden['id']}/historial").json()
    assert [(h["etapa"], h["usuario"]) for h in historial] == [
        ("por_verificar", "Luis"),
        ("en_cola", "Luis"),
        ("en_produccion", "Marta"),
        ("terminada", "Marta"),
        ("entregada", "Luis"),
    ]
    assert all(_hace_un_momento(h["creado_en"]) for h in historial)
    horas = [h["creado_en"] for h in historial]
    assert horas == sorted(horas)  # en el orden en que pasó


def test_la_entrega_fisica_guarda_quien_la_entrego_cuando_y_quien_retiro(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    api.post(f"/ordenes/{orden['id']}/acuse")
    avanzar(api, orden, "terminada")
    entrar_como(datos["asesor"])

    r = avanzar(api, orden, "entregada", nota="  Carlos Pérez (esposo)  ")
    assert r.status_code == 200, r.text
    assert r.json()["entregada_por"] == "Luis" and _hace_un_momento(r.json()["entregada_en"])
    ultimo = api.get(f"/ordenes/{orden['id']}/historial").json()[-1]
    assert ultimo["nota"] == "Retiró: Carlos Pérez (esposo)"
    assert api.get(f"/ordenes/{orden['id']}").json()["entregada_por"] == "Luis"


def test_la_entrega_sin_nota_no_inventa_quien_retiro(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    api.post(f"/ordenes/{orden['id']}/acuse")
    avanzar(api, orden, "terminada")
    r = avanzar(api, orden, "entregada").json()
    assert r["entregada_por"] == "Marta"
    assert api.get(f"/ordenes/{orden['id']}/historial").json()[-1]["nota"] is None


def test_el_asesor_solo_registra_la_entrega(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["asesor"])
    r = avanzar(api, orden, "en_produccion")
    assert r.status_code == 403 and "entrega" in r.json()["detail"]


def test_una_orden_sin_entregar_no_tiene_datos_de_entrega(api, datos):
    orden = nueva_orden(api, datos)
    assert orden["entregada_por"] is None and orden["entregada_en"] is None


def test_la_nota_de_entrega_tiene_un_largo_maximo(api, datos):
    orden = nueva_orden(api, datos)
    entrar_como(datos["taller"])
    api.post(f"/ordenes/{orden['id']}/acuse")
    avanzar(api, orden, "terminada")
    assert avanzar(api, orden, "entregada", nota="x" * 201).status_code == 422
