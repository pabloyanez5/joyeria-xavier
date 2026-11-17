"""Importa clientes y órdenes desde archivos CSV a la base de datos (JOY-48).

Uso (desde la carpeta backend):
    python -m app.migracion --demo
    python -m app.migracion --clientes clientes.csv --ordenes ordenes.csv

Cada fila se valida por separado: una fila con error se informa y se sigue con las demás.
Se puede ejecutar varias veces: lo que ya existe se omite y no se duplica.
"""
import argparse
import csv
import io
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seed
from app.db import SessionLocal
from app.models import Cliente, HistorialEtapa, Orden, Producto

CANALES = ("whatsapp", "instagram", "messenger")
ETAPAS = ("en_cola", "en_produccion", "terminada", "entregada")
COLUMNAS_CLIENTES = ("canal", "id_canal", "nombre")
COLUMNAS_ORDENES = ("canal", "id_canal", "descripcion", "etapa", "fecha")
DATOS_DEMO = Path(__file__).parent / "datos_demo"


class ErrorArchivo(Exception):
    """El archivo no se puede leer o no tiene las columnas esperadas."""


@dataclass
class Reporte:
    nombre: str
    importadas: int = 0
    omitidas: int = 0
    errores: list[tuple[int, str]] = field(default_factory=list)


def leer_filas(ruta: Path, columnas: tuple[str, ...]) -> list[tuple[int, dict]]:
    """Devuelve (número de fila en el archivo, datos) de cada fila. Acepta ',' o ';'."""
    try:
        texto = ruta.read_text(encoding="utf-8-sig")  # utf-8-sig: el CSV de Excel trae BOM
    except OSError as e:
        raise ErrorArchivo(f"No se pudo abrir {ruta}: {e.strerror or e}") from e
    primera = texto.splitlines()[0] if texto.strip() else ""
    delimitador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    lector.fieldnames = [(c or "").strip().lower() for c in (lector.fieldnames or [])]
    faltan = [c for c in columnas if c not in lector.fieldnames]
    if faltan:
        raise ErrorArchivo(f"A {ruta.name} le faltan columnas: {', '.join(faltan)}")
    filas = []
    for numero, fila in enumerate(lector, start=2):  # la fila 1 es el encabezado
        datos = {k: (v or "").strip() for k, v in fila.items() if k}
        if any(datos.values()):  # se ignoran las filas totalmente vacías
            filas.append((numero, datos))
    return filas


def importar_clientes(session: Session, filas: list[tuple[int, dict]]) -> Reporte:
    reporte = Reporte("clientes")
    for numero, f in filas:
        canal = f["canal"].lower()
        if canal not in CANALES:
            reporte.errores.append((numero, f"canal '{f['canal']}' no válido ({'/'.join(CANALES)})"))
            continue
        if not f["id_canal"] or len(f["id_canal"]) > 100:
            reporte.errores.append((numero, "id_canal vacío o de más de 100 caracteres"))
            continue
        if not f["nombre"] or len(f["nombre"]) > 200:
            reporte.errores.append((numero, "nombre vacío o de más de 200 caracteres"))
            continue
        if len(f.get("talla", "")) > 20:
            reporte.errores.append((numero, "talla de más de 20 caracteres"))
            continue
        existe = session.scalar(
            select(Cliente.id).where(Cliente.canal == canal, Cliente.id_canal == f["id_canal"])
        )
        if existe is not None:
            reporte.omitidas += 1
            continue
        session.add(
            Cliente(
                canal=canal,
                id_canal=f["id_canal"],
                nombre_perfil=f["nombre"],
                talla=f.get("talla") or None,
            )
        )
        session.flush()
        reporte.importadas += 1
    return reporte


def importar_ordenes(session: Session, filas: list[tuple[int, dict]]) -> Reporte:
    reporte = Reporte("órdenes")
    productos = {p.nombre.lower(): p.id for p in session.scalars(select(Producto))}
    for numero, f in filas:
        canal = f["canal"].lower()
        cliente_id = session.scalar(
            select(Cliente.id).where(Cliente.canal == canal, Cliente.id_canal == f["id_canal"])
        )
        if cliente_id is None:
            reporte.errores.append((numero, f"el cliente {canal}/{f['id_canal']} no existe"))
            continue
        etapa = f["etapa"].lower()
        if etapa not in ETAPAS:
            reporte.errores.append((numero, f"etapa '{f['etapa']}' no válida ({', '.join(ETAPAS)})"))
            continue
        if not 3 <= len(f["descripcion"]) <= 1000:
            reporte.errores.append((numero, "la descripción debe tener entre 3 y 1000 caracteres"))
            continue
        try:
            dia = date.fromisoformat(f["fecha"])
        except ValueError:
            reporte.errores.append((numero, f"fecha '{f['fecha']}' no válida (use AAAA-MM-DD)"))
            continue
        producto_id = None
        if f.get("producto"):
            producto_id = productos.get(f["producto"].lower())
            if producto_id is None:
                reporte.errores.append((numero, f"el producto '{f['producto']}' no está en el catálogo"))
                continue
        momento = datetime.combine(dia, time(12, 0), tzinfo=timezone.utc)
        existe = session.scalar(
            select(Orden.id).where(
                Orden.cliente_id == cliente_id,
                Orden.descripcion == f["descripcion"],
                Orden.creado_en == momento,
            )
        )
        if existe is not None:
            reporte.omitidas += 1
            continue
        orden = Orden(
            cliente_id=cliente_id,
            producto_id=producto_id,
            descripcion=f["descripcion"],
            etapa_actual=etapa,
            acuse_pendiente=etapa == "en_cola",
            publicada_en=momento,
            creado_en=momento,
            actualizado_en=momento,
        )
        session.add(orden)
        session.flush()
        session.add(HistorialEtapa(orden_id=orden.id, etapa=etapa, creado_en=momento))
        reporte.importadas += 1
    return reporte


def mostrar(reporte: Reporte) -> None:
    print(
        f"{reporte.nombre.capitalize()}: {reporte.importadas} importadas, "
        f"{reporte.omitidas} omitidas (ya existían), {len(reporte.errores)} con error"
    )
    for numero, motivo in reporte.errores:
        print(f"  fila {numero}: {motivo}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa clientes y órdenes desde CSV.")
    parser.add_argument("--clientes", type=Path, help="CSV con: canal, id_canal, nombre, talla")
    parser.add_argument(
        "--ordenes",
        type=Path,
        help="CSV con: canal, id_canal, producto, descripcion, etapa, fecha",
    )
    parser.add_argument(
        "--demo", action="store_true", help="carga el catálogo y los datos ficticios de demostración"
    )
    args = parser.parse_args(argv)
    clientes, ordenes = args.clientes, args.ordenes
    if args.demo:
        clientes, ordenes = DATOS_DEMO / "clientes.csv", DATOS_DEMO / "ordenes.csv"
    if clientes is None and ordenes is None:
        parser.error("indica --demo, o al menos --clientes o --ordenes")

    try:
        filas_clientes = leer_filas(clientes, COLUMNAS_CLIENTES) if clientes else []
        filas_ordenes = leer_filas(ordenes, COLUMNAS_ORDENES) if ordenes else []
    except ErrorArchivo as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    reportes = []
    with SessionLocal() as session:
        if args.demo:
            print(f"Catálogo: {seed.cargar(session)} productos nuevos")
        try:
            if clientes:
                reportes.append(importar_clientes(session, filas_clientes))
            if ordenes:
                reportes.append(importar_ordenes(session, filas_ordenes))
            session.commit()
        except Exception:
            session.rollback()
            raise
    for reporte in reportes:
        mostrar(reporte)
    return 1 if any(r.errores for r in reportes) else 0


if __name__ == "__main__":
    sys.exit(main())
