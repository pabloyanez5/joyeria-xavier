"""JOY-76: el modelo no puede inventar precios.

En la medición con Gemini real, ante «Quiero cotizar unas argollas» respondió «desde los $150»
sin consultar el catálogo (lo real es $257). Ahora todo monto que escribe debe venir del catálogo,
de una orden o de lo que dijo el cliente.
"""
from decimal import Decimal

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.agente.lc_agente import AVISO_PRECIOS  # noqa: E402
from app.agente.seguridad import precios_sin_respaldo  # noqa: E402
from app.models import IntentoBloqueado  # noqa: E402
from tests.test_agente_langchain import _enviar, catalogo, entorno, llamada, modelo  # noqa: E402,F401


def _intentos(session):
    return session.scalars(select(IntentoBloqueado)).all()


def test_si_inventa_un_precio_se_le_pide_consultar_el_catalogo(session, cache, catalogo):
    m = modelo(
        AIMessage("¡Qué alegría! Tenemos argollas desde los $150."),  # inventado
        llamada("consultar_catalogo", categoria="Argollas"),
        AIMessage("Las argollas parten desde $257.00 en oro 14k. ¿Para cuándo las necesitas?"),
    )
    r = _enviar(session, cache, "Quiero cotizar unas argollas de matrimonio", m)
    assert "$150" not in r.texto and "$257.00" in r.texto
    assert AVISO_PRECIOS in str(m.recibidos[1][-1].content)
    assert _intentos(session) == []  # se corrigió solo, sin bloquear nada


def test_si_insiste_se_responde_con_el_catalogo_real(session, cache, catalogo):
    m = modelo(
        AIMessage("Tenemos aretes desde $45."),
        AIMessage("Insisto, desde $45."),
    )
    r = _enviar(session, cache, "necesito un presupuesto para unos aretes", m)
    assert "$45" not in r.texto and "catálogo" in r.texto and "http" in r.texto
    (intento,) = _intentos(session)
    assert (intento.motivo, intento.regla) == ("respuesta_corregida", "precio_no_verificado")


def test_un_precio_real_del_catalogo_no_se_toca(session, cache, catalogo):
    m = modelo(
        llamada("consultar_catalogo", categoria="Aretes"),
        AIMessage("Los aretes de argolla van desde $41.20. ¿Los prefieres en oro o plata?"),
    )
    r = _enviar(session, cache, "¿cuánto cuestan los aretes?", m)
    assert "$41.20" in r.texto and len(m.recibidos) == 2


def test_puede_repetir_el_presupuesto_que_dio_el_cliente(session, cache, catalogo):
    m = modelo(AIMessage("Con $400 tienes muy buenas opciones. ¿Qué joya buscas?"))
    r = _enviar(session, cache, "tengo 400 dólares para un regalo", m)
    assert "$400" in r.texto and len(m.recibidos) == 1


CATALOGO = (
    "- Argolla clásica (Argollas): desde $257.00\n- Cadena cubana (Cadenas): desde $1,250.00\n"
    "- Aretes de argolla (Aretes): desde $41.20"
)


@pytest.mark.parametrize(
    "respuesta, sin_respaldo",
    [
        ("desde los $150", [Decimal("150")]),
        ("desde $257", []),
        ("desde $257.00", []),
        ("la cubana está en $1.250", []),  # escrito al estilo de Ecuador
        ("unos 1250 dólares", []),
        ("desde $41", []),  # redondeo a dólares enteros de $41,20
        ("desde $260", [Decimal("260")]),
        ("en oro 18k, talla 7, lista el 12/12", []),  # no son precios
        ("USD 99", [Decimal("99")]),
    ],
)
def test_que_montos_tienen_respaldo(respuesta, sin_respaldo):
    assert precios_sin_respaldo(respuesta, CATALOGO) == sin_respaldo
