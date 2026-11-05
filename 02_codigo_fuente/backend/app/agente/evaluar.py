"""Mide la precisión del clasificador sobre los 50 casos.

Uso (desde la carpeta backend):
    python -m app.agente.evaluar

Si existe GEMINI_API_KEY, evalúa también con el modelo y mide los tiempos.
Si el nivel gratuito se queda sin cupo por minuto (error 429), repite con una
pausa entre mensajes:
    set EVAL_PAUSA=4
"""
import os
import time
from collections import Counter

from app.agente.casos_evaluacion import CASOS
from app.agente.intenciones import clasificar, clasificar_con_reglas
from app.agente.llm import ErrorLLM, ProveedorLLM, proveedor_desde_entorno


class ConErrores(ProveedorLLM):
    """Envuelve al proveedor y anota cada llamada que falla (para no esconderlas)."""

    def __init__(self, interno):
        self.interno = interno
        self.modelo = interno.modelo
        self.errores: list[str] = []

    def generar(self, sistema: str, usuario: str) -> str:
        try:
            return self.interno.generar(sistema, usuario)
        except ErrorLLM as e:
            self.errores.append(str(e))
            raise


def precision(clasificador, pausa: float = 0.0):
    fallos, tiempos = [], []
    for texto, esperada in CASOS:
        if pausa:
            time.sleep(pausa)
        inicio = time.perf_counter()
        obtenida = clasificador(texto)
        tiempos.append(time.perf_counter() - inicio)
        if obtenida != esperada:
            fallos.append((texto, esperada, obtenida))
    return 1 - len(fallos) / len(CASOS), fallos, tiempos


def mostrar(nombre: str, clasificador, pausa: float = 0.0, proveedor=None) -> None:
    aciertos, fallos, tiempos = precision(clasificador, pausa)
    print(f"\n== {nombre} ==")
    print(f"Precisión: {aciertos:.0%} ({len(CASOS) - len(fallos)}/{len(CASOS)})")
    print(f"Tiempo por mensaje: promedio {sum(tiempos) / len(tiempos):.2f} s, máximo {max(tiempos):.2f} s")
    for texto, esperada, obtenida in fallos:
        print(f"  - '{texto}': esperada={esperada}, obtenida={obtenida}")
    if proveedor is not None:
        total = len(proveedor.errores)
        print(f"Llamadas al modelo que fallaron (se usaron las reglas): {total} de {len(CASOS)}")
        for mensaje, veces in Counter(proveedor.errores).most_common(3):
            print(f"  {veces} x {mensaje}")


def main() -> None:
    mostrar("Reglas (sin modelo)", clasificar_con_reglas)
    interno = proveedor_desde_entorno()
    if interno is None:
        print("\n(Sin GEMINI_API_KEY: no se evaluó con el modelo.)")
        return
    proveedor = ConErrores(interno)
    pausa = float(os.getenv("EVAL_PAUSA", "0") or 0)
    mostrar(
        f"Modelo {proveedor.modelo}",
        lambda t: clasificar(t, proveedor),
        pausa,
        proveedor,
    )


if __name__ == "__main__":
    main()
