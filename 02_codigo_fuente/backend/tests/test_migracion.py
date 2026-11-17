from sqlalchemy import func, select

from app import migracion, seed
from app.models import Cliente, HistorialEtapa, Orden

CLIENTES = "canal,id_canal,nombre,talla\nwhatsapp,593990000001,Ana Pérez,7\ninstagram,ana.demo,Ana IG,\n"
ORDENES = (
    "canal,id_canal,producto,descripcion,etapa,fecha\n"
    "whatsapp,593990000001,Anillo sello,Anillo sello en plata talla 7,en_cola,2026-10-01\n"
    "whatsapp,593990000001,,Reparación de cadena,entregada,2026-03-15\n"
)


def escribir(tmp_path, nombre, texto, codificacion="utf-8"):
    ruta = tmp_path / nombre
    ruta.write_bytes(texto.encode(codificacion))
    return ruta


def cargar_basico(session, tmp_path):
    seed.cargar(session)
    c = migracion.importar_clientes(
        session, migracion.leer_filas(escribir(tmp_path, "c.csv", CLIENTES), migracion.COLUMNAS_CLIENTES)
    )
    o = migracion.importar_ordenes(
        session, migracion.leer_filas(escribir(tmp_path, "o.csv", ORDENES), migracion.COLUMNAS_ORDENES)
    )
    return c, o


def test_importa_clientes_y_ordenes(session, tmp_path):
    c, o = cargar_basico(session, tmp_path)
    assert (c.importadas, c.omitidas, c.errores) == (2, 0, [])
    assert (o.importadas, o.omitidas, o.errores) == (2, 0, [])
    ordenes = session.scalars(select(Orden).order_by(Orden.id)).all()
    assert ordenes[0].etapa_actual == "en_cola" and ordenes[0].acuse_pendiente is True
    assert ordenes[0].producto_id is not None
    assert ordenes[1].etapa_actual == "entregada" and ordenes[1].acuse_pendiente is False
    assert ordenes[1].producto_id is None
    assert ordenes[1].creado_en.date().isoformat() == "2026-03-15"
    assert session.scalar(select(func.count()).select_from(HistorialEtapa)) == 2


def test_es_idempotente(session, tmp_path):
    cargar_basico(session, tmp_path)
    c, o = cargar_basico(session, tmp_path)
    assert (c.importadas, c.omitidas) == (0, 2)
    assert (o.importadas, o.omitidas) == (0, 2)
    assert session.scalar(select(func.count()).select_from(Cliente)) == 2
    assert session.scalar(select(func.count()).select_from(Orden)) == 2


def test_filas_malas_se_informan_y_no_detienen_la_carga(session, tmp_path):
    seed.cargar(session)
    clientes = (
        "canal,id_canal,nombre,talla\n"
        "telegram,1,Sin Canal,7\n"
        "whatsapp,,Sin Id,7\n"
        "whatsapp,593990000009,,7\n"
        "whatsapp,593990000001,Ana Pérez,7\n"
    )
    c = migracion.importar_clientes(
        session, migracion.leer_filas(escribir(tmp_path, "c.csv", clientes), migracion.COLUMNAS_CLIENTES)
    )
    assert c.importadas == 1
    assert [n for n, _ in c.errores] == [2, 3, 4]

    ordenes = (
        "canal,id_canal,producto,descripcion,etapa,fecha\n"
        "whatsapp,000,,Cliente inexistente,en_cola,2026-10-01\n"
        "whatsapp,593990000001,,Etapa mala,pintada,2026-10-01\n"
        "whatsapp,593990000001,,Fecha mala,en_cola,01/10/2026\n"
        "whatsapp,593990000001,Producto inventado,Producto que no existe,en_cola,2026-10-01\n"
        "whatsapp,593990000001,,ok,en_cola,2026-10-01\n"
        "whatsapp,593990000001,,Orden correcta,en_cola,2026-10-01\n"
    )
    o = migracion.importar_ordenes(
        session, migracion.leer_filas(escribir(tmp_path, "o.csv", ordenes), migracion.COLUMNAS_ORDENES)
    )
    assert o.importadas == 1
    assert [n for n, _ in o.errores] == [2, 3, 4, 5, 6]


def test_acepta_punto_y_coma_y_bom(tmp_path):
    texto = "canal;id_canal;nombre;talla\nwhatsapp;1;Ana;7\n"
    ruta = escribir(tmp_path, "c.csv", "﻿" + texto)
    filas = migracion.leer_filas(ruta, migracion.COLUMNAS_CLIENTES)
    assert filas == [(2, {"canal": "whatsapp", "id_canal": "1", "nombre": "Ana", "talla": "7"})]


def test_ignora_filas_vacias(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "canal,id_canal,nombre,talla\n,,,\nwhatsapp,1,Ana,7\n")
    assert len(migracion.leer_filas(ruta, migracion.COLUMNAS_CLIENTES)) == 1


def test_columnas_faltantes(tmp_path):
    ruta = escribir(tmp_path, "c.csv", "canal,nombre\nwhatsapp,Ana\n")
    try:
        migracion.leer_filas(ruta, migracion.COLUMNAS_CLIENTES)
    except migracion.ErrorArchivo as e:
        assert "id_canal" in str(e)
    else:
        raise AssertionError("debía fallar")


def test_archivo_inexistente(tmp_path):
    try:
        migracion.leer_filas(tmp_path / "no_existe.csv", migracion.COLUMNAS_CLIENTES)
    except migracion.ErrorArchivo as e:
        assert "no_existe.csv" in str(e)
    else:
        raise AssertionError("debía fallar")


def test_demo_carga_sin_errores_y_deja_ordenes_en_cola(session, monkeypatch, capsys):
    monkeypatch.setattr(migracion, "SessionLocal", lambda: session)
    assert migracion.main(["--demo"]) == 0
    assert session.scalar(select(func.count()).select_from(Cliente)) == 12
    assert session.scalar(select(func.count()).select_from(Orden)) == 18
    en_cola = session.scalar(
        select(func.count()).select_from(Orden).where(Orden.acuse_pendiente.is_(True))
    )
    assert en_cola == 3
    # segunda ejecución: nada se duplica
    assert migracion.main(["--demo"]) == 0
    assert session.scalar(select(func.count()).select_from(Orden)) == 18
    assert "0 con error" in capsys.readouterr().out


def test_main_devuelve_codigo_1_si_hay_errores(session, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(migracion, "SessionLocal", lambda: session)
    ruta = escribir(tmp_path, "c.csv", "canal,id_canal,nombre,talla\ntelegram,1,Ana,7\n")
    assert migracion.main(["--clientes", str(ruta)]) == 1
    assert "fila 2" in capsys.readouterr().out
