import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Cliente,
    Conversacion,
    HistorialEtapa,
    Mensaje,
    Orden,
    Usuario,
)


def crear_cliente(session):
    cliente = Cliente(canal="whatsapp", id_canal="593900000001")
    session.add(cliente)
    session.commit()
    return cliente


def crear_conversacion(session):
    cliente = crear_cliente(session)
    conversacion = Conversacion(cliente_id=cliente.id, canal="whatsapp")
    session.add(conversacion)
    session.commit()
    return conversacion


def test_conversacion_rechaza_estado_invalido(session):
    cliente = crear_cliente(session)
    session.add(
        Conversacion(cliente_id=cliente.id, canal="whatsapp", estado="invalido")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_conversacion_nace_activa(session):
    conversacion = crear_conversacion(session)
    assert conversacion.estado == "activa"


def test_usuario_rechaza_rol_invalido(session):
    session.add(Usuario(nombre="Ana", email="ana@example.com", rol="invitado"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_mensaje_rechaza_direccion_invalida(session):
    conversacion = crear_conversacion(session)
    session.add(
        Mensaje(conversacion_id=conversacion.id, direccion="otra", contenido="hola")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_mensaje_id_externo_no_se_repite(session):
    conversacion = crear_conversacion(session)
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="entrante",
            contenido="hola",
            id_externo="wamid.1",
        )
    )
    session.commit()
    session.add(
        Mensaje(
            conversacion_id=conversacion.id,
            direccion="entrante",
            contenido="hola otra vez",
            id_externo="wamid.1",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_mensajes_sin_id_externo_pueden_repetirse(session):
    conversacion = crear_conversacion(session)
    for texto in ("uno", "dos"):
        session.add(
            Mensaje(
                conversacion_id=conversacion.id,
                direccion="saliente",
                contenido=texto,
            )
        )
    session.commit()
    total = session.query(Mensaje).filter_by(conversacion_id=conversacion.id).count()
    assert total == 2


def test_orden_registra_historial_de_etapas(session):
    cliente = crear_cliente(session)
    usuario = Usuario(nombre="Luis", email="luis@example.com", rol="taller")
    session.add(usuario)
    orden = Orden(
        cliente_id=cliente.id, descripcion="Anillo de prueba", etapa_actual="recepcion"
    )
    session.add(orden)
    session.commit()
    session.add(
        HistorialEtapa(orden_id=orden.id, etapa="recepcion", usuario_id=usuario.id)
    )
    session.commit()
    historial = session.query(HistorialEtapa).filter_by(orden_id=orden.id).all()
    assert len(historial) == 1
    assert historial[0].etapa == "recepcion"