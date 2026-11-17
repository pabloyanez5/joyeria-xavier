"""JOY-79 y JOY-22: orden con datos obligatorios, pedidos de varias joyas y verificación del abono."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import get_session
from app.main import app
from app.models import Cliente, HistorialEtapa, Orden, Pedido, Producto, Usuario
from app.webhook import get_enviador
from tests.conftest import datos_de_orden, entrar_como, verificar
from tests.test_conversaciones import EnviadorFalso


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_enviador, None)


@pytest.fixture
def datos(session):
    cliente = Cliente(canal="whatsapp", id_canal="593987654321", nombre_perfil="Ana 💎")
    producto = Producto(nombre="Aretes con perla", categoria="Aretes", activo=True)
    asesor = Usuario(nombre="Luis", email="luis@x.com", rol="asesor")
    taller = Usuario(nombre="Marta", email="marta@x.com", rol="taller")
    session.add_all([cliente, producto, asesor, taller])
    session.commit()
    return {"cliente": cliente, "producto": producto, "asesor": asesor, "taller": taller}


def _orden(datos, **extra) -> dict:
    return datos_de_orden(
        **{"cliente_id": datos["cliente"].id, "descripcion": "Aretes de oro 18k", **extra}
    )


def _joya(**extra) -> dict:
    joya = datos_de_orden(**{"descripcion": "Aretes de oro 18k", **extra})
    joya.pop("nombre_completo")
    joya.pop("telefono")
    return joya


def _cuantas(session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo))


# --- datos obligatorios (JOY-79) ---

@pytest.mark.parametrize(
    "campo",
    ["nombre_completo", "telefono", "descripcion", "peso_gramos", "fecha_entrega_taller",
     "fecha_entrega_cliente", "total"],
)
def test_no_se_crea_una_orden_si_falta_un_dato_obligatorio(api, session, datos, campo):
    cuerpo = _orden(datos)
    cuerpo.pop(campo)
    assert api.post("/ordenes", json=cuerpo).status_code == 422
    assert _cuantas(session, Orden) == 0


@pytest.mark.parametrize(
    "cambio",
    [
        {"peso_gramos": "0"},
        {"total": "0"},
        {"total": "-5"},
        {"abono": "400.00"},  # mayor que el total (350)
        {"abono": "-1"},
        {"fecha_entrega_cliente": "2026-11-30"},  # antes de la entrega al taller
        {"telefono": "abc"},
        {"telefono": "123"},
        {"nombre_completo": "  "},
        {"foto_referencia_url": "javascript:alert(1)"},
    ],
)
def test_rechaza_datos_que_no_tienen_sentido(api, session, datos, cambio):
    assert api.post("/ordenes", json=_orden(datos, **cambio)).status_code == 422
    assert _cuantas(session, Orden) == 0


def test_la_orden_guarda_todos_sus_datos_y_calcula_el_saldo(api, datos):
    orden = api.post(
        "/ordenes",
        json=_orden(
            datos,
            producto_id=datos["producto"].id,
            abono="100.00",
            foto_referencia_url="https://fotos.test/aretes.jpg",
        ),
    ).json()
    assert orden["peso_gramos"] == "4.50"
    assert orden["fecha_entrega_taller"] == "2026-12-01"
    assert orden["fecha_entrega_cliente"] == "2026-12-10"
    assert (orden["total"], orden["abono"], orden["saldo"]) == ("350.00", "100.00", "250.00")
    assert orden["foto_referencia_url"] == "https://fotos.test/aretes.jpg"
    assert orden["producto"] == "Aretes con perla" and orden["pedido"] is None


def test_los_datos_de_contacto_quedan_en_el_cliente(api, session, datos):
    api.post("/ordenes", json=_orden(datos, nombre_completo="  Ana   María Pérez ", telefono="(099) 123-4567"))
    cliente = session.get(Cliente, datos["cliente"].id)
    assert cliente.nombre_completo == "Ana María Pérez"
    assert cliente.telefono == "0991234567"


def test_el_panel_sugiere_el_telefono_de_whatsapp_y_recuerda_el_confirmado(api, session, datos):
    session.add(Cliente(canal="messenger", id_canal="psid-1", nombre_perfil="Leo"))
    session.commit()
    por_canal = {c["canal"]: c for c in api.get("/clientes").json()}
    assert por_canal["whatsapp"]["telefono"] == "593987654321"  # el número desde el que escribe
    assert por_canal["messenger"]["telefono"] is None  # en Messenger hay que pedirlo
    api.post("/ordenes", json=_orden(datos, telefono="0998887766"))
    confirmado = next(c for c in api.get("/clientes").json() if c["canal"] == "whatsapp")
    assert confirmado["telefono"] == "0998887766" and confirmado["nombre_completo"] == "Ana Pérez"


# --- verificación del abono antes del taller (JOY-22) ---

def test_sin_abono_registrado_el_taller_no_puede_tocar_la_orden(api, datos):
    orden = api.post("/ordenes", json=_orden(datos)).json()
    assert orden["etapa_actual"] == "por_verificar" and orden["siguiente_etapa"] is None
    entrar_como(datos["taller"])
    avance = api.post(f"/ordenes/{orden['id']}/etapa", json={"etapa": "en_produccion"})
    assert avance.status_code == 409 and "verificación del abono" in avance.json()["detail"]
    assert api.post(f"/ordenes/{orden['id']}/etapa", json={"etapa": "en_cola"}).status_code == 409
    assert api.post(f"/ordenes/{orden['id']}/acuse").status_code == 409


def test_el_taller_ve_las_ordenes_por_verificar_solo_como_prevision(api, datos):
    orden = api.post("/ordenes", json=_orden(datos)).json()
    entrar_como(datos["taller"])
    assert api.get("/ordenes/cola").json() == []
    previstas = api.get("/ordenes?etapa=por_verificar").json()
    assert [o["id"] for o in previstas] == [orden["id"]]


def test_verificar_registra_el_abono_quien_y_cuando(api, session, datos):
    entrar_como(datos["asesor"])
    orden = api.post("/ordenes", json=_orden(datos)).json()
    verificada = verificar(api, orden, abono="150.00")
    assert verificada["etapa_actual"] == "en_cola" and verificada["siguiente_etapa"] == "en_produccion"
    assert (verificada["abono"], verificada["saldo"]) == ("150.00", "200.00")
    assert verificada["verificada_por"] == "Luis" and verificada["verificada_en"] is not None
    etapas = session.scalars(
        select(HistorialEtapa).where(HistorialEtapa.orden_id == orden["id"]).order_by(HistorialEtapa.id)
    ).all()
    assert [(h.etapa, h.usuario_id) for h in etapas] == [
        ("por_verificar", datos["asesor"].id), ("en_cola", datos["asesor"].id),
    ]


def test_el_abono_debe_ser_mayor_que_cero_y_no_pasar_del_total(api, datos):
    orden = api.post("/ordenes", json=_orden(datos)).json()
    ruta = f"/ordenes/{orden['id']}/verificar"
    assert api.post(ruta, json={"abono": "0"}).status_code == 422
    assert api.post(ruta, json={}).status_code == 422
    assert api.post(ruta, json={"abono": "350.01"}).status_code == 422
    assert api.get(f"/ordenes/{orden['id']}").json()["etapa_actual"] == "por_verificar"
    assert api.post(ruta, json={"abono": "350.00", "avisar_al_cliente": False}).status_code == 200


def test_una_orden_no_se_verifica_dos_veces(api, datos):
    orden = verificar(api, api.post("/ordenes", json=_orden(datos)).json())
    repetida = api.post(f"/ordenes/{orden['id']}/verificar", json={"abono": "50.00"})
    assert repetida.status_code == 409
    assert api.get(f"/ordenes/{orden['id']}").json()["abono"] == "100.00"
    assert api.post("/ordenes/999/verificar", json={"abono": "50.00"}).status_code == 404


def test_al_verificar_el_cliente_recibe_la_confirmacion_por_su_canal(api, datos):
    falso = EnviadorFalso()
    app.dependency_overrides[get_enviador] = lambda: falso
    orden = api.post("/ordenes", json=_orden(datos)).json()
    r = api.post(f"/ordenes/{orden['id']}/verificar", json={"abono": "100.00"}).json()
    assert r["aviso_al_cliente"] == "enviado"
    canal, destinatario, texto = falso.enviados[0]
    assert (canal, destinatario) == ("whatsapp", "593987654321")
    assert orden["codigo"] in texto and "abono" in texto


# --- pedido: varias joyas, una orden por cada una ---

def test_un_pedido_crea_una_orden_por_joya_y_las_une(api, session, datos):
    entrar_como(datos["asesor"])
    r = api.post(
        "/ordenes/pedido",
        json={
            "cliente_id": datos["cliente"].id,
            "nombre_completo": "Ana Pérez",
            "telefono": "0991234567",
            "joyas": [
                _joya(total="400.00", abono="100.00"),
                _joya(descripcion="Cadena de plata", total="800.00", peso_gramos="12.00"),
            ],
        },
    )
    assert r.status_code == 201
    pedido = r.json()
    assert pedido["codigo"] == f"PD-{pedido['id']:06d}"
    assert (pedido["total"], pedido["abono"], pedido["saldo"]) == ("1200.00", "100.00", "1100.00")
    aretes, cadena = pedido["ordenes"]
    assert aretes["pedido"] == cadena["pedido"] == pedido["codigo"]
    assert aretes["id"] != cadena["id"] and cadena["descripcion"] == "Cadena de plata"
    assert {o["etapa_actual"] for o in pedido["ordenes"]} == {"por_verificar"}
    assert session.get(Pedido, pedido["id"]).usuario_id == datos["asesor"].id
    assert api.get(f"/ordenes/pedido/{pedido['id']}").json() == pedido


def test_cada_joya_del_pedido_avanza_por_su_cuenta(api, datos):
    pedido = api.post(
        "/ordenes/pedido",
        json={
            "cliente_id": datos["cliente"].id,
            "nombre_completo": "Ana Pérez",
            "telefono": "0991234567",
            "joyas": [_joya(), _joya(descripcion="Cadena de plata")],
        },
    ).json()
    aretes, cadena = pedido["ordenes"]
    verificar(api, aretes)
    api.post(f"/ordenes/{aretes['id']}/etapa", json={"etapa": "en_produccion", "avisar_al_cliente": False})
    estado = {o["descripcion"]: o["etapa_actual"] for o in api.get(f"/ordenes/pedido/{pedido['id']}").json()["ordenes"]}
    assert estado == {"Aretes de oro 18k": "en_produccion", "Cadena de plata": "por_verificar"}


def test_si_una_joya_del_pedido_esta_mal_no_se_crea_ninguna(api, session, datos):
    cuerpo = {
        "cliente_id": datos["cliente"].id,
        "nombre_completo": "Ana Pérez",
        "telefono": "0991234567",
        "joyas": [_joya(), _joya(producto_id=999)],
    }
    assert api.post("/ordenes/pedido", json=cuerpo).status_code == 404
    session.rollback()
    assert _cuantas(session, Orden) == 0 and _cuantas(session, Pedido) == 0


def test_un_pedido_necesita_al_menos_una_joya_y_tiene_tope(api, datos):
    base = {"cliente_id": datos["cliente"].id, "nombre_completo": "Ana Pérez", "telefono": "0991234567"}
    assert api.post("/ordenes/pedido", json={**base, "joyas": []}).status_code == 422
    assert api.post("/ordenes/pedido", json={**base, "joyas": [_joya()] * 9}).status_code == 422
    assert api.get("/ordenes/pedido/999").status_code == 404


def test_solo_el_asesor_crea_pedidos(api, datos):
    entrar_como(datos["taller"])
    cuerpo = {
        "cliente_id": datos["cliente"].id,
        "nombre_completo": "Ana Pérez",
        "telefono": "0991234567",
        "joyas": [_joya()],
    }
    assert api.post("/ordenes/pedido", json=cuerpo).status_code == 403


# --- lo que el agente le cuenta al cliente ---

def test_el_agente_dice_que_la_orden_espera_el_abono(api, session, cache, datos):
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage, ToolMessage

    from app.agente.servicio import atender_mensaje
    from tests.test_agente_langchain import llamada, modelo

    orden = api.post("/ordenes", json=_orden(datos)).json()
    m = modelo(llamada("consultar_orden"), AIMessage("Tu orden espera la confirmación del abono."))
    atender_mensaje(session, cache, "whatsapp", "593987654321", "cómo va mi pedido?", modelo=m)
    salida = [x for x in m.recibidos[1] if isinstance(x, ToolMessage)][0].content
    assert orden["codigo"] in salida and "pendiente de confirmar el abono" in salida
