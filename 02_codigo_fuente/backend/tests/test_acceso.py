"""JOY-78: inicio de sesión y permisos por rol (RNF-01)."""
from datetime import datetime, timedelta, timezone

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient

from app import acceso
from app.acceso import Intentos, clave_correcta, cifrar_clave, crear_token, get_intentos
from app.db import get_session
from app.main import app
from app.models import Cliente, Mensaje, Orden, Usuario
from app.usuarios import activar, cambiar_clave, crear_usuario
from app.webhook import get_enviador
from tests.conftest import datos_de_orden, sin_sesion, verificar
from tests.test_conversaciones import EnviadorFalso

CLAVE = "clave-larga-123"


@pytest.fixture
def api(session):
    sin_sesion()  # aquí se prueba el control de acceso real
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_enviador] = lambda: None
    intentos = Intentos(fakeredis.FakeRedis(decode_responses=True))
    app.dependency_overrides[get_intentos] = lambda: intentos
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def usuarios(session):
    return {
        rol: crear_usuario(session, f"Persona {rol}", f"{rol}@joyeria.test", rol, CLAVE)
        for rol in ("asesor", "taller", "direccion", "admin")
    }


def entrar(api, email, clave=CLAVE):
    return api.post("/sesion", json={"email": email, "clave": clave})


def cabecera(api, rol):
    token = entrar(api, f"{rol}@joyeria.test").json()["token"]
    return {"Authorization": f"Bearer {token}"}


# --- claves ---

def test_la_clave_se_guarda_cifrada_y_con_sal_distinta_cada_vez():
    a, b = cifrar_clave(CLAVE), cifrar_clave(CLAVE)
    assert CLAVE not in a and a != b
    assert clave_correcta(CLAVE, a) and clave_correcta(CLAVE, b)
    assert not clave_correcta("otra-clave-456", a)


def test_una_clave_guardada_dañada_o_vacia_nunca_es_correcta():
    assert not clave_correcta(CLAVE, None)
    assert not clave_correcta(CLAVE, "")
    assert not clave_correcta(CLAVE, "texto-sin-formato")
    assert not clave_correcta(CLAVE, "md5$1$abc$def")


def test_no_se_aceptan_claves_cortas_ni_roles_inventados(session):
    with pytest.raises(ValueError):
        crear_usuario(session, "Ana", "ana@joyeria.test", "asesor", "corta")
    with pytest.raises(ValueError):
        crear_usuario(session, "Ana", "ana@joyeria.test", "invitado", CLAVE)


def test_no_se_repite_un_correo(session, usuarios):
    with pytest.raises(ValueError):
        crear_usuario(session, "Otro", "ASESOR@joyeria.test", "asesor", CLAVE)


# --- inicio de sesión ---

def test_inicia_sesion_y_recibe_token_y_sus_datos(api, usuarios):
    r = entrar(api, "Asesor@Joyeria.test")  # el correo no distingue mayúsculas
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["tipo"] == "Bearer" and cuerpo["expira_en"] == 8 * 3600
    assert cuerpo["usuario"] == {
        "id": usuarios["asesor"].id,
        "nombre": "Persona asesor",
        "email": "asesor@joyeria.test",
        "rol": "asesor",
    }
    yo = api.get("/sesion", headers={"Authorization": f"Bearer {cuerpo['token']}"})
    assert yo.status_code == 200 and yo.json()["rol"] == "asesor"


def test_clave_o_correo_incorrectos_dan_el_mismo_error(api, usuarios):
    mala = entrar(api, "asesor@joyeria.test", "clave-equivocada")
    nadie = entrar(api, "nadie@joyeria.test")
    assert mala.status_code == nadie.status_code == 401
    assert mala.json() == nadie.json()  # no revela qué correos existen


def test_un_usuario_sin_clave_o_desactivado_no_entra(api, session, usuarios):
    session.add(Usuario(nombre="Viejo", email="viejo@joyeria.test", rol="asesor"))
    session.commit()
    assert entrar(api, "viejo@joyeria.test", "").status_code == 422
    assert entrar(api, "viejo@joyeria.test", "cualquier-clave").status_code == 401
    activar(session, "taller@joyeria.test", False)
    assert entrar(api, "taller@joyeria.test").status_code == 401


def test_tras_cinco_fallos_se_bloquea_el_correo_por_un_rato(api, usuarios):
    for _ in range(5):
        assert entrar(api, "asesor@joyeria.test", "clave-equivocada").status_code == 401
    assert entrar(api, "asesor@joyeria.test").status_code == 429  # ni con la clave buena


def test_un_inicio_correcto_borra_los_fallos_anteriores(session, usuarios):
    intentos = Intentos(fakeredis.FakeRedis(decode_responses=True))
    sin_sesion()
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_intentos] = lambda: intentos
    try:
        api = TestClient(app)
        for _ in range(4):
            entrar(api, "asesor@joyeria.test", "clave-equivocada")
        assert entrar(api, "asesor@joyeria.test").status_code == 200
        for _ in range(4):
            entrar(api, "asesor@joyeria.test", "clave-equivocada")
        assert entrar(api, "asesor@joyeria.test").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_cambiar_la_clave_invalida_la_anterior(api, session, usuarios):
    cambiar_clave(session, "asesor@joyeria.test", "clave-nueva-456")
    assert entrar(api, "asesor@joyeria.test").status_code == 401
    assert entrar(api, "asesor@joyeria.test", "clave-nueva-456").status_code == 200


# --- token ---

@pytest.mark.parametrize("ruta", ["/ordenes", "/ordenes/cola", "/clientes", "/conversaciones", "/metricas", "/sesion"])
def test_sin_token_no_se_entra_a_ninguna_ruta_del_panel(api, ruta):
    r = api.get(ruta)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_las_rutas_publicas_siguen_abiertas(api):
    assert api.get("/health").status_code == 200
    assert api.get("/productos").status_code == 200
    assert api.get("/contacto").status_code == 200


def test_un_token_alterado_caducado_o_firmado_con_otra_clave_no_sirve(api, usuarios):
    token = entrar(api, "asesor@joyeria.test").json()["token"]
    alterado = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    hace_un_dia = datetime.now(timezone.utc) - timedelta(days=1)
    caducado = crear_token(usuarios["asesor"], ahora=hace_un_dia)
    ajeno = jwt.encode(
        {"sub": str(usuarios["asesor"].id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "otra-clave-secreta-de-al-menos-32-caracteres",
        algorithm="HS256",
    )
    sin_firma = jwt.encode({"sub": str(usuarios["admin"].id), "exp": 9999999999}, "", algorithm="none")
    for malo in (alterado, caducado, ajeno, sin_firma, "no-es-un-token"):
        r = api.get("/conversaciones", headers={"Authorization": f"Bearer {malo}"})
        assert r.status_code == 401, malo


def test_desactivar_a_un_usuario_corta_su_sesion_de_inmediato(api, session, usuarios):
    cabeza = cabecera(api, "asesor")
    assert api.get("/conversaciones", headers=cabeza).status_code == 200
    activar(session, "asesor@joyeria.test", False)
    assert api.get("/conversaciones", headers=cabeza).status_code == 401


def test_el_rol_se_lee_de_la_base_y_no_del_token(api, session, usuarios):
    cabeza = cabecera(api, "asesor")
    usuarios["asesor"].rol = "taller"
    session.commit()
    assert api.get("/conversaciones", headers=cabeza).status_code == 403


def test_el_secreto_de_entorno_firma_los_tokens(monkeypatch, usuarios):
    monkeypatch.setenv("SESION_SECRETO", "s" * 40)
    token = crear_token(usuarios["asesor"])
    assert acceso.leer_token(token)["sub"] == str(usuarios["asesor"].id)
    monkeypatch.setenv("SESION_SECRETO", "t" * 40)
    assert acceso.leer_token(token) is None


# --- permisos por rol ---

PERMISOS = [
    # (método, ruta, roles que pueden; admin puede siempre)
    ("get", "/conversaciones", {"asesor"}),
    ("get", "/clientes", {"asesor"}),
    ("get", "/ordenes", {"asesor", "taller"}),
    ("get", "/ordenes/cola", {"asesor", "taller"}),
    ("get", "/metricas", {"direccion"}),
]


@pytest.mark.parametrize("metodo,ruta,permitidos", PERMISOS)
def test_cada_rol_ve_solo_lo_suyo(api, usuarios, metodo, ruta, permitidos):
    for rol in ("asesor", "taller", "direccion", "admin"):
        r = getattr(api, metodo)(ruta, headers=cabecera(api, rol))
        esperado = 200 if rol in permitidos | {"admin"} else 403
        assert r.status_code == esperado, (rol, ruta)


def test_solo_el_asesor_crea_ordenes_y_solo_el_taller_las_avanza(api, session, usuarios):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    session.add(cliente)
    session.commit()
    cuerpo = datos_de_orden(cliente_id=cliente.id, descripcion="Argollas en oro 18k")
    for rol in ("taller", "direccion"):
        assert api.post("/ordenes", json=cuerpo, headers=cabecera(api, rol)).status_code == 403
    orden = api.post("/ordenes", json=cuerpo, headers=cabecera(api, "asesor")).json()
    abono = {"abono": "100.00", "avisar_al_cliente": False}
    for rol in ("taller", "direccion"):  # solo el asesor registra el abono
        r = api.post(f"/ordenes/{orden['id']}/verificar", json=abono, headers=cabecera(api, rol))
        assert r.status_code == 403
    verificar(api, orden, headers=cabecera(api, "asesor"))
    etapa = {"etapa": "en_produccion", "avisar_al_cliente": False}
    for rol in ("asesor", "direccion"):
        r = api.post(f"/ordenes/{orden['id']}/etapa", json=etapa, headers=cabecera(api, rol))
        assert r.status_code == 403
        r = api.post(f"/ordenes/{orden['id']}/acuse", headers=cabecera(api, rol))
        assert r.status_code == 403
    r = api.post(f"/ordenes/{orden['id']}/etapa", json=etapa, headers=cabecera(api, "taller"))
    assert r.status_code == 200


def test_la_direccion_no_puede_modificar_nada(api, session, usuarios):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    session.add(cliente)
    session.commit()
    cabeza = cabecera(api, "direccion")
    assert api.get("/metricas", headers=cabeza).status_code == 200
    assert api.post(
        "/ordenes", json=datos_de_orden(cliente_id=cliente.id, descripcion="algo"), headers=cabeza
    ).status_code == 403
    assert api.post("/conversaciones/1/cerrar", headers=cabeza).status_code == 403
    assert api.post("/conversaciones/1/responder", json={"texto": "hola"}, headers=cabeza).status_code == 403


# --- queda registrado quién hizo cada cosa ---

def test_el_acuse_guarda_quien_lo_confirmo_y_cuando(api, session, usuarios):
    cliente = Cliente(canal="whatsapp", id_canal="593111", nombre_perfil="Ana Pérez")
    session.add(cliente)
    session.commit()
    orden = api.post(
        "/ordenes",
        json=datos_de_orden(cliente_id=cliente.id, descripcion="Argollas en oro 18k"),
        headers=cabecera(api, "asesor"),
    ).json()
    orden = verificar(api, orden, headers=cabecera(api, "asesor"))
    assert orden["acuse_por"] is None and orden["acuse_en"] is None
    assert orden["verificada_por"] == "Persona asesor" and orden["verificada_en"] is not None
    r = api.post(f"/ordenes/{orden['id']}/acuse", headers=cabecera(api, "taller")).json()
    assert r["acuse_pendiente"] is False
    assert r["acuse_por"] == "Persona taller" and r["acuse_en"] is not None
    guardada = session.get(Orden, orden["id"])
    assert guardada.acuse_usuario_id == usuarios["taller"].id


def test_la_respuesta_del_asesor_guarda_quien_la_escribio(api, session, cache, usuarios):
    from app.agente.servicio import atender_mensaje

    r = atender_mensaje(session, cache, "whatsapp", "593111", "hola", proveedor=None)
    app.dependency_overrides[get_enviador] = lambda: EnviadorFalso()
    detalle = api.post(
        f"/conversaciones/{r.conversacion_id}/responder",
        json={"texto": "Hola, soy el asesor."},
        headers=cabecera(api, "asesor"),
    )
    assert detalle.status_code == 200
    ultimo = detalle.json()["historial"][-1]
    assert ultimo["autor"] == "asesor" and ultimo["usuario"] == "Persona asesor"
    mensaje = session.get(Mensaje, ultimo["id"])
    assert mensaje.usuario_id == usuarios["asesor"].id


# --- línea de comandos ---

class _SesionPrestada:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *_):
        return False


def test_la_linea_de_comandos_crea_lista_y_desactiva(session, monkeypatch, capsys):
    from app import db, usuarios as cli

    monkeypatch.setattr(db, "SessionLocal", lambda: _SesionPrestada(session))
    monkeypatch.setenv("USUARIO_CLAVE", CLAVE)
    orden = ["crear", "--nombre", "Ana Ruiz", "--email", "ana@joyeria.test", "--rol", "asesor"]
    assert cli.main(orden) == 0
    assert cli.main(orden) == 1  # el correo ya existe
    assert cli.main(["desactivar", "--email", "ana@joyeria.test"]) == 0
    assert cli.main(["listar"]) == 0
    salida = capsys.readouterr()
    assert "ana@joyeria.test\tasesor\tdesactivado\tcon clave" in salida.out
    assert CLAVE not in salida.out + salida.err  # la clave nunca se imprime
    assert "Ya existe un usuario" in salida.err
