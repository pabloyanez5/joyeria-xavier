from sqlalchemy import event

from app.clientes import identificar_cliente, registrar_cliente


def test_crea_cliente_nuevo(session):
    cliente, creado = registrar_cliente(session, "whatsapp", "593999111222", "Ana")
    assert creado is True
    assert cliente.id is not None


def test_no_duplica_cliente_existente(session):
    c1, _ = registrar_cliente(session, "whatsapp", "593999111222", "Ana")
    c2, creado = registrar_cliente(session, "whatsapp", "593999111222", "Ana")
    assert creado is False
    assert c2.id == c1.id


def test_mismo_id_en_otro_canal_es_otro_cliente(session):
    c1, _ = registrar_cliente(session, "whatsapp", "123")
    c2, creado = registrar_cliente(session, "instagram", "123")
    assert creado is True
    assert c2.id != c1.id


def test_primer_mensaje_crea_y_guarda_en_cache(session, cache):
    cliente_id, creado = identificar_cliente(session, cache, "whatsapp", "999", "Ana")
    assert creado is True
    assert cache.obtener("whatsapp", "999") == cliente_id


def test_segundo_mensaje_se_sirve_desde_cache_sin_consultar_bd(session, cache):
    id1, creado1 = identificar_cliente(session, cache, "whatsapp", "999", "Ana")
    assert creado1 is True

    consultas = []
    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        lambda conn, cursor, statement, *args: consultas.append(statement),
    )

    id2, creado2 = identificar_cliente(session, cache, "whatsapp", "999", "Ana")
    assert (id2, creado2) == (id1, False)
    assert consultas == []  # no se tocó la base de datos