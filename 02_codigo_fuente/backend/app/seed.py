from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Precio, Producto, TarifaMaterial

VIGENTE_DESDE = date(2026, 1, 1)

# Precio por gramo de referencia (USD). Son valores de demostración: la joyería los
# actualiza cuando cambia el precio del metal, sin tocar el código.
TARIFAS = [
    ("oro", "18k", "95.00"),
    ("oro", "14k", "74.00"),
    ("plata", None, "1.60"),
]

# Fotos provisionales por categoría (carpeta public/img de la web). Se reemplazan por las
# fotos reales de la joyería cambiando `imagen_url` de cada producto.
IMAGEN_CATEGORIA = {
    "Anillos": "/img/anillos.png",
    "Argollas": "/img/argollas.png",
    "Cadenas": "/img/cadenas.png",
    "Pulseras": "/img/pulseras.png",
    "Aretes": "/img/aretes.png",
    "Dijes": "/img/dijes.png",
}

# (nombre, categoría, descripción, peso en gramos, mano de obra USD, combinaciones que se ofrecen)
# Precio = peso x precio por gramo del material + mano de obra. El precio de cada
# combinación en la tabla `precios` es el respaldo si no hubiera peso o tarifa.
CATALOGO = [
    ("Anillo solitario clásico", "Anillos", "Engaste de garras, diseño atemporal.",
     "4.00", "78.00",
     [("oro", "18k", "450.00"), ("oro", "14k", "360.00"), ("plata", None, "85.00")]),
    ("Anillo de compromiso con halo", "Anillos", "Piedra central rodeada de pequeños brillantes.",
     "6.00", "210.00",
     [("oro", "18k", "780.00"), ("oro", "14k", "640.00")]),
    ("Anillo sello", "Anillos", "Superficie lisa para grabar iniciales.",
     "3.50", "62.00",
     [("oro", "18k", "390.00"), ("plata", None, "70.00")]),
    ("Argolla de matrimonio clásica", "Argollas", "Media caña, acabado pulido.",
     "3.00", "35.00",
     [("oro", "18k", "320.00"), ("oro", "14k", "260.00")]),
    ("Argolla de matrimonio diamantada", "Argollas", "Acabado diamantado con borde pulido.",
     "3.20", "56.00",
     [("oro", "18k", "360.00"), ("oro", "14k", "295.00")]),
    ("Cadena cubana", "Cadenas", "Eslabones gruesos, cierre de seguridad.",
     "9.00", "125.00",
     [("oro", "18k", "980.00"), ("oro", "14k", "790.00"), ("plata", None, "140.00")]),
    ("Cadena veneciana", "Cadenas", "Eslabón fino y resistente para uso diario.",
     "2.80", "50.00",
     [("oro", "18k", "310.00"), ("plata", None, "55.00")]),
    ("Pulsera tejida", "Pulseras", "Diseño tejido flexible, largo ajustable.",
     "4.50", "90.00",
     [("oro", "18k", "540.00"), ("plata", None, "95.00")]),
    ("Pulsera esclava", "Pulseras", "Placa frontal personalizable.",
     "4.20", "21.00",
     [("oro", "18k", "420.00"), ("oro", "14k", "340.00")]),
    ("Aretes de argolla", "Aretes", "Argolla mediana con cierre a presión.",
     "2.00", "38.00",
     [("oro", "18k", "230.00"), ("plata", None, "40.00")]),
    ("Aretes con perla", "Aretes", "Perla cultivada sobre base de oro.",
     "1.80", "89.00",
     [("oro", "18k", "260.00"), ("oro", "14k", "210.00")]),
    ("Dije corazón", "Dijes", "Dije liso con opción de grabado.",
     "1.20", "36.00",
     [("oro", "18k", "150.00"), ("plata", None, "28.00")]),
]


def _cargar_tarifas(session: Session) -> None:
    for material, quilataje, precio_gramo in TARIFAS:
        existe = session.scalar(
            select(TarifaMaterial).where(
                TarifaMaterial.material == material,
                TarifaMaterial.quilataje.is_(None)
                if quilataje is None
                else TarifaMaterial.quilataje == quilataje,
            )
        )
        if existe is None:
            session.add(
                TarifaMaterial(
                    material=material,
                    quilataje=quilataje,
                    precio_gramo=Decimal(precio_gramo),
                    vigente_desde=VIGENTE_DESDE,
                )
            )


def cargar(session: Session) -> int:
    """Carga el catálogo de prueba. Es repetible: no duplica y completa peso y mano de
    obra en productos que ya existían sin ellos (sin pisar valores ya editados)."""
    creados = 0
    for nombre, categoria, descripcion, peso, mano_obra, precios in CATALOGO:
        producto = session.scalar(select(Producto).where(Producto.nombre == nombre))
        if producto is not None:
            if producto.peso_gramos is None:
                producto.peso_gramos = Decimal(peso)
            if producto.mano_obra is None:
                producto.mano_obra = Decimal(mano_obra)
            if producto.imagen_url is None:
                producto.imagen_url = IMAGEN_CATEGORIA.get(categoria)
            continue
        producto = Producto(
            nombre=nombre,
            categoria=categoria,
            descripcion=descripcion,
            peso_gramos=Decimal(peso),
            mano_obra=Decimal(mano_obra),
            imagen_url=IMAGEN_CATEGORIA.get(categoria),
        )
        session.add(producto)
        session.flush()
        for material, quilataje, precio in precios:
            session.add(
                Precio(
                    producto_id=producto.id,
                    material=material,
                    quilataje=quilataje,
                    precio=Decimal(precio),
                    vigente_desde=VIGENTE_DESDE,
                )
            )
        creados += 1
    _cargar_tarifas(session)
    session.commit()
    return creados


def main() -> None:
    with SessionLocal() as session:
        print(f"Productos creados: {cargar(session)}")


if __name__ == "__main__":
    main()
