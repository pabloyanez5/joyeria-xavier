from app.clientes import registrar_cliente


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