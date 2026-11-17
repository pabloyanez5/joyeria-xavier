"""JOY-21: el cliente recibe el estado real de su pedido aunque el modelo no responda."""
from datetime import date

import pytest
from app.agente import estado_ordenes
from app.agente.servicio import atender_mensaje
from app.models import Cliente, Conversacion, Orden, Producto
from sqlalchemy import select

TEL = "593987000111"


@pytest.fixture
def cliente(session, cache):
    atender_mensaje(session, cache, "whatsapp", TEL, "hola", nombre="Pablo Yánez")
    return session.scalar(select(Cliente).where(Cliente.id_canal == TEL))


def _orden(session, cliente, etapa, descripcion, **extra):
    orden = Orden(cliente_id=cliente.id, descripcion=descripcion, etapa_actual=etapa, **extra)
    session.add(orden)
    session.commit()
    return orden


def _preguntar(session, cache, texto="¿Cómo va mi pedido?", modelo=None):
    return atender_mensaje(session, cache, "whatsapp", TEL, texto, modelo=modelo)


def test_sin_modelo_responde_el_estado_de_cada_joya(session, cache, cliente):
    aretes = Producto(nombre="Aretes de argolla", categoria="Aretes", activo=True)
    session.add(aretes)
    session.commit()
    a = _orden(session, cliente, "en_produccion", "Joya: Aretes. Origen: conversación #1",
               producto_id=aretes.id, fecha_entrega_cliente=date(2026, 12, 1))
    c = _orden(session, cliente, "por_verificar",
               "Joya: Cadenas; Modelo: Cadena veneciana. Origen: conversación #1")

    r = _preguntar(session, cache)

    assert not r.escalada
    assert f"OP-{a.id:06d} · Aretes de argolla: en producción" in r.texto
    assert "Entrega estimada: 01/12/2026" in r.texto
    assert f"OP-{c.id:06d} · Joya: Cadenas; Modelo: Cadena veneciana" in r.texto
    assert "pendiente de confirmar el abono" in r.texto
    assert "Origen" not in r.texto  # el dato interno no se le muestra al cliente
    assert "tus pedidos" in r.texto


def test_si_el_modelo_falla_igual_recibe_el_estado(session, cache, cliente):
    pytest.importorskip("langchain_core")
    from tests.test_agente_langchain import modelo

    _orden(session, cliente, "en_cola", "Anillo de oro")
    r = _preguntar(session, cache, modelo=modelo(falla=True))

    assert not r.escalada
    assert "confirmada, en la cola del taller" in r.texto


def test_sin_ordenes_pasa_a_un_asesor(session, cache, cliente):
    r = _preguntar(session, cache)

    assert r.escalada
    assert "No encuentro un pedido registrado a tu nombre" in r.texto
    conversacion = session.get(Conversacion, r.conversacion_id)
    assert conversacion.estado == "escalada"


def test_las_entregadas_no_tapan_a_las_abiertas(session, cache, cliente):
    _orden(session, cliente, "entregada", "Pulsera vieja")
    _orden(session, cliente, "terminada", "Dije nuevo")

    r = _preguntar(session, cache)

    assert "Dije nuevo: terminada" in r.texto and "Pulsera vieja" not in r.texto


def test_si_todas_se_entregaron_cuenta_la_ultima(session, cache, cliente):
    _orden(session, cliente, "entregada", "Pulsera de plata",
           fecha_entrega_cliente=date(2026, 11, 1))

    r = _preguntar(session, cache)

    assert not r.escalada
    assert "Pulsera de plata: entregada." in r.texto
    assert "Entrega estimada" not in r.texto


def test_solo_ve_sus_propias_ordenes(session, cache, cliente):
    otro = Cliente(canal="whatsapp", id_canal="593000999", nombre_perfil="Otra persona")
    session.add(otro)
    session.commit()
    _orden(session, otro, "en_produccion", "Anillo ajeno")

    r = _preguntar(session, cache)

    assert r.escalada and "Anillo ajeno" not in r.texto


def test_la_herramienta_del_agente_sugiere_derivar_si_no_hay_ordenes(session, cliente):
    texto = estado_ordenes.para_el_agente(session, cliente.id)
    assert "no tiene órdenes" in texto and "asesor" in texto
