
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Precio, Producto

CATALOGO = [
    ("Anillo solitario clásico", "Anillos", "Engaste de garras, diseño atemporal.",
     [("oro", "18k", "450.00"), ("oro", "14k", "360.00"), ("plata", None, "85.00")]),
    ("Anillo de compromiso con halo", "Anillos", "Piedra central rodeada de pequeños brillantes.",
     [("oro", "18k", "780.00"), ("oro", "14k", "640.00")]),
    ("Anillo sello", "Anillos", "Superficie lisa para grabar iniciales.",
     [("oro", "18k", "390.00"), ("plata", None, "70.00")]),
    ("Argolla de matrimonio clásica", "Argollas", "Media caña, acabado pulido.",
     [("oro", "18k", "320.00"), ("oro", "14k", "260.00")]),
    ("Argolla de matrimonio diamantada", "Argollas", "Acabado diamantado con borde pulido.",
     [("oro", "18k", "360.00"), ("oro", "14k", "295.00")]),
    ("Cadena cubana", "Cadenas", "Eslabones gruesos, cierre de seguridad.",
     [("oro", "18k", "980.00"), ("oro", "14k", "790.00"), ("plata", None, "140.00")]),
    ("Cadena veneciana", "Cadenas", "Eslabón fino y resistente para uso diario.",
     [("oro", "18k", "310.00"), ("plata", None, "55.00")]),
    ("Pulsera tejida", "Pulseras", "Diseño tejido flexible, largo ajustable.",
     [("oro", "18k", "540.00"), ("plata", None, "95.00")]),
    ("Pulsera esclava", "Pulseras", "Placa frontal personalizable.",
     [("oro", "18k", "420.00"), ("oro", "14k", "340.00")]),
    ("Aretes de argolla", "Aretes", "Argolla mediana con cierre a presión.",
     [("oro", "18k", "230.00"), ("plata", None, "40.00")]),
    ("Aretes con perla", "Aretes", "Perla cultivada sobre base de oro.",
     [("oro", "18k", "260.00"), ("oro", "14k", "210.00")]),
    ("Dije corazón", "Dijes", "Dije liso con opción de grabado.",
     [("oro", "18k", "150.00"), ("plata", None, "28.00")]),
]


def cargar(session: Session) -> int:

    creados = 0
    for nombre, categoria, descripcion, precios in CATALOGO:
        if session.scalar(select(Producto).where(Producto.nombre == nombre)):
            continue
        producto = Producto(nombre=nombre, categoria=categoria, descripcion=descripcion)
        session.add(producto)
        session.flush()
        for material, quilataje, precio in precios:
            session.add(
                Precio(
                    producto_id=producto.id,
                    material=material,
                    quilataje=quilataje,
                    precio=Decimal(precio),
                    vigente_desde=date(2026, 1, 1),
                )
            )
        creados += 1
    session.commit()
    return creados


def main() -> None:
    with SessionLocal() as session:
        print(f"Productos creados: {cargar(session)}")


if __name__ == "__main__":
    main()