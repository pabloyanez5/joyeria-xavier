"""JOY-75 · Cotizador correcto en el 100 % de al menos 20 casos (RNF-07).

Cada caso arma su propia pieza, su precio de tabla y su tarifa, y cotiza por la API igual que
la web y el agente. La tabla de casos está documentada en
03_pruebas/unitarias/JOY-75_casos_del_cotizador.md, y la última prueba revisa que el documento y
este archivo digan lo mismo.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Precio, Producto, TarifaMaterial

HOY = date.today()
DOCUMENTO = (
    Path(__file__).resolve().parents[3] / "03_pruebas" / "unitarias" / "JOY-75_casos_del_cotizador.md"
)
NO_SE_COTIZA = "no se cotiza"


@dataclass(frozen=True)
class Caso:
    id: str
    descripcion: str
    material: str
    quilataje: str | None
    peso: str | None  # gramos de la pieza; None = sin peso registrado
    precio_gramo: str | None  # tarifa vigente; None = sin tarifa para ese material
    mano_obra: str | None
    precio_tabla: str  # precio fijo de respaldo de la tabla `precios`
    esperado: str  # precio en USD, o NO_SE_COTIZA
    metodo: str | None  # formula | tabla | None (no se cotiza)
    # Cómo lo pide el cliente y cómo está escrita la tarifa, si no es igual a la pieza.
    consulta: tuple[str, str | None] | None = None
    tarifa_como: tuple[str, str | None] | None = None

    @property
    def resultado(self) -> str:
        """Como aparece en el documento: «458,00 (fórmula)», «85,00 (tabla)» o «no se cotiza»."""
        if self.metodo is None:
            return NO_SE_COTIZA
        metodo = "fórmula" if self.metodo == "formula" else "tabla"
        return f"{self.esperado.replace('.', ',')} ({metodo})"


CASOS = [
    # --- Fórmula con el catálogo de la joyería: peso x precio del gramo + mano de obra ---
    Caso("C01", "Anillo solitario en oro 18k", "oro", "18k", "4.00", "95.00", "78.00", "450.00", "458.00", "formula"),
    Caso("C02", "Anillo solitario en oro 14k", "oro", "14k", "4.00", "74.00", "78.00", "360.00", "374.00", "formula"),
    Caso("C03", "Anillo solitario en plata", "plata", None, "4.00", "1.60", "78.00", "85.00", "84.40", "formula"),
    Caso("C04", "Anillo con halo en oro 18k", "oro", "18k", "6.00", "95.00", "210.00", "780.00", "780.00", "formula"),
    Caso("C05", "Anillo sello en plata", "plata", None, "3.50", "1.60", "62.00", "70.00", "67.60", "formula"),
    Caso("C06", "Argolla clásica en oro 14k", "oro", "14k", "3.00", "74.00", "35.00", "260.00", "257.00", "formula"),
    Caso("C07", "Argolla diamantada en oro 18k", "oro", "18k", "3.20", "95.00", "56.00", "360.00", "360.00", "formula"),
    Caso("C08", "Cadena cubana en oro 18k", "oro", "18k", "9.00", "95.00", "125.00", "980.00", "980.00", "formula"),
    Caso("C09", "Cadena veneciana en plata", "plata", None, "2.80", "1.60", "50.00", "55.00", "54.48", "formula"),
    Caso("C10", "Pulsera esclava en oro 14k", "oro", "14k", "4.20", "74.00", "21.00", "340.00", "331.80", "formula"),
    Caso("C11", "Aretes con perla en oro 14k", "oro", "14k", "1.80", "74.00", "89.00", "210.00", "222.20", "formula"),
    Caso("C12", "Dije corazón en oro 18k", "oro", "18k", "1.20", "95.00", "36.00", "150.00", "150.00", "formula"),
    # --- Redondeo a centavos (mitad hacia arriba) ---
    Caso("C13", "Redondeo hacia arriba (117,5265)", "oro", "18k", "1.23", "95.55", "10.00", "1.00", "127.53", "formula"),
    Caso("C14", "Redondeo hacia abajo (82,2843)", "oro", "14k", "1.11", "74.13", "5.00", "1.00", "87.28", "formula"),
    Caso("C15", "Medio centavo exacto (0,505) sube", "plata", None, "0.50", "1.01", "20.00", "1.00", "20.51", "formula"),
    # --- Datos incompletos o extremos ---
    Caso("C16", "Sin mano de obra registrada (cuenta 0)", "oro", "18k", "2.00", "95.00", None, "1.00", "190.00", "formula"),
    Caso("C17", "Pieza pesada (125,5 g)", "oro", "18k", "125.50", "95.00", "300.00", "1.00", "12222.50", "formula"),
    Caso("C18", "Material y quilataje escritos distinto (ORO 18K)", "oro", "18k", "4.00", "95.00", "78.00", "450.00", "458.00", "formula",
         consulta=("Oro", "18K"), tarifa_como=("ORO", "18K")),
    # --- Sin tarifa o sin peso: precio fijo de la tabla ---
    Caso("C19", "Material sin tarifa vigente", "plata", None, "4.00", None, "78.00", "85.00", "85.00", "tabla"),
    Caso("C20", "Pieza sin peso registrado", "oro", "18k", None, "95.00", "78.00", "450.00", "450.00", "tabla"),
    # --- Valores no válidos: no se usa la fórmula ---
    Caso("C21", "Peso cero", "oro", "18k", "0.00", "95.00", "78.00", "450.00", "450.00", "tabla"),
    Caso("C22", "Peso negativo", "oro", "18k", "-4.00", "95.00", "78.00", "450.00", "450.00", "tabla"),
    Caso("C23", "Precio del gramo en cero", "oro", "18k", "4.00", "0.00", "78.00", "450.00", "450.00", "tabla"),
    Caso("C24", "Mano de obra negativa", "oro", "18k", "4.00", "95.00", "-10.00", "450.00", "450.00", "tabla"),
    Caso("C25", "Peso cero y sin precio de tabla válido", "oro", "18k", "0.00", "95.00", "78.00", "0.00", NO_SE_COTIZA, None),
    Caso("C26", "Combinación que la pieza no ofrece (pide 14k)", "oro", "18k", "4.00", "74.00", "78.00", "450.00", NO_SE_COTIZA, None,
         consulta=("oro", "14k"), tarifa_como=("oro", "14k")),
]


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _sembrar(session, caso: Caso) -> int:
    pieza = Producto(
        nombre=f"Pieza {caso.id}",
        categoria="Pruebas",
        peso_gramos=None if caso.peso is None else Decimal(caso.peso),
        mano_obra=None if caso.mano_obra is None else Decimal(caso.mano_obra),
    )
    session.add(pieza)
    session.commit()
    session.add(
        Precio(producto_id=pieza.id, material=caso.material, quilataje=caso.quilataje,
               precio=Decimal(caso.precio_tabla), vigente_desde=HOY)
    )
    if caso.precio_gramo is not None:
        material, quilataje = caso.tarifa_como or (caso.material, caso.quilataje)
        session.add(
            TarifaMaterial(material=material, quilataje=quilataje,
                           precio_gramo=Decimal(caso.precio_gramo), vigente_desde=HOY)
        )
    session.commit()
    return pieza.id


@pytest.mark.parametrize("caso", CASOS, ids=[c.id for c in CASOS])
def test_cotizacion(api, session, caso):
    pieza = _sembrar(session, caso)
    material, quilataje = caso.consulta or (caso.material, caso.quilataje)
    params = {"material": material, **({"quilataje": quilataje} if quilataje else {})}
    r = api.get(f"/productos/{pieza}/cotizacion", params=params)

    if caso.metodo is None:
        assert r.status_code == 422, r.text  # la web y el agente lo derivan a un asesor
        return
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["metodo"] == caso.metodo
    assert Decimal(datos["precio"]) == Decimal(caso.esperado)
    assert Decimal(datos["precio"]).as_tuple().exponent == -2  # siempre en centavos
    if caso.metodo == "formula":
        # El desglose que ve el cliente suma exactamente el precio.
        assert Decimal(datos["costo_material"]) + Decimal(datos["mano_obra"]) == Decimal(datos["precio"])
    else:
        assert datos["peso_gramos"] is None and datos["costo_material"] is None


def test_son_al_menos_20_casos_y_sin_repetir():
    assert len(CASOS) >= 20
    assert len({c.id for c in CASOS}) == len(CASOS)


def test_un_precio_no_valido_tampoco_aparece_en_el_catalogo(api, session):
    caso = next(c for c in CASOS if c.id == "C25")
    pieza = _sembrar(session, caso)
    detalle = api.get(f"/productos/{pieza}").json()
    assert detalle["precios"] == [] and detalle["precio_desde"] is None


def test_la_tarifa_mas_reciente_es_la_que_cuenta(api, session):
    pieza = _sembrar(session, CASOS[0])
    session.add_all([
        TarifaMaterial(material="oro", quilataje="18k", precio_gramo=Decimal("90.00"),
                       vigente_desde=HOY - timedelta(days=30)),
        TarifaMaterial(material="oro", quilataje="18k", precio_gramo=Decimal("500.00"),
                       vigente_desde=HOY + timedelta(days=1)),
    ])
    session.commit()
    datos = api.get(f"/productos/{pieza}/cotizacion", params={"material": "oro", "quilataje": "18k"}).json()
    assert Decimal(datos["precio_gramo"]) == Decimal("95.00")  # ni la vieja ni la futura


def test_el_documento_tiene_los_mismos_casos():
    filas = {}
    for linea in DOCUMENTO.read_text(encoding="utf-8").splitlines():
        celdas = [c.strip() for c in linea.strip().strip("|").split("|")]
        if celdas and re.fullmatch(r"C\d{2}", celdas[0]):
            filas[celdas[0]] = celdas[-1]
    assert filas == {c.id: c.resultado for c in CASOS}
