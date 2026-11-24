"""Mide la precisión del clasificador sobre los 50 casos.

Uso (desde la carpeta backend):
    python -m app.agente.evaluar

Con --agente mide además al agente real (LangChain con herramientas, JOY-76): cada mensaje pasa
por el agente completo, sobre una base temporal en memoria (no toca los datos del servidor), y se
revisa si eligió la acción correcta. En el servidor de staging:
    docker compose -f docker-compose.staging.yml exec api python -m app.agente.evaluar --agente

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


# --- el agente real (JOY-76) ---

# Qué acción del agente corresponde a cada intención de los casos. «cotizar» y «catalogo» se
# atienden igual (la herramienta del catálogo), así que cuentan como la misma acción.
ACCION_ESPERADA = {
    "saludo": {"conversar"},
    "despedida": {"conversar"},
    "cotizar": {"catalogo"},
    "catalogo": {"catalogo"},
    "estado_pedido": {"consultar_orden"},
    "asesor": {"asesor"},
    # Fuera de tema o datos de la joyería: conversar, informar o derivar; nunca inventar con el
    # catálogo ni con una orden.
    "otro": {"conversar", "informacion", "asesor"},
}


def accion_del_agente(herramientas: list[str], escalar: bool) -> str:
    """La acción principal que tomó el agente en una respuesta."""
    if escalar or "derivar_a_asesor" in herramientas:
        return "asesor"
    if "consultar_orden" in herramientas:
        return "consultar_orden"
    if {"consultar_catalogo", "mostrar_opciones"} & set(herramientas):
        return "catalogo"
    if "informacion_joyeria" in herramientas:
        return "informacion"
    return "conversar"


def _base_temporal():
    """Base en memoria con el catálogo de prueba: el agente lee precios y órdenes reales."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401  (registra las tablas)
    from app.db import Base
    from app.seed import cargar

    motor = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    session = sessionmaker(bind=motor)()
    cargar(session)
    return session


def evaluar_agente(modelo, casos=CASOS, pausa: float = 0.0):
    """Pasa cada caso por el agente real, en una conversación nueva, con un cliente que ya tiene
    una orden en producción (así «¿cómo va mi pedido?» tiene algo que consultar)."""
    from datetime import date, timedelta

    from app.agente import lc_agente
    from app.models import Cliente, Conversacion, Orden

    session = _base_temporal()
    resultados = []
    for n, (texto, esperada) in enumerate(casos, start=1):
        if pausa and n > 1:
            time.sleep(pausa)
        cliente = Cliente(
            canal="whatsapp",
            id_canal=f"eval-{n}",
            nombre_preferido="Ana",
            contexto_cualificacion={"nombre_confirmado": True},
        )
        session.add(cliente)
        session.flush()
        session.add(
            Orden(
                cliente_id=cliente.id,
                descripcion="Argollas de matrimonio en oro 18k",
                etapa_actual="en_produccion",
                fecha_entrega_cliente=date.today() + timedelta(days=10),
            )
        )
        conversacion = Conversacion(cliente_id=cliente.id, canal="whatsapp")
        session.add(conversacion)
        session.commit()
        inicio = time.perf_counter()
        try:
            r = lc_agente.responder(session, modelo, cliente, conversacion.id, texto)
            accion, origen, respuesta = accion_del_agente(r.herramientas, r.escalar), r.origen, r.texto
        except Exception as e:  # el modelo no respondió: se cuenta aparte, no como acierto
            accion, origen, respuesta = "error", "error", f"{type(e).__name__}: {str(e)[:120]}"
        resultados.append(
            {
                "texto": texto,
                "esperada": esperada,
                "accion": accion,
                "acierto": accion in ACCION_ESPERADA[esperada],
                "origen": origen,
                "segundos": time.perf_counter() - inicio,
                "respuesta": respuesta,
            }
        )
    session.close()
    return resultados


def mostrar_agente(resultados: list[dict], nombre: str) -> None:
    total = len(resultados)
    aciertos = sum(r["acierto"] for r in resultados)
    errores = [r for r in resultados if r["origen"] == "error"]
    respondidos = total - len(errores)
    tiempos = [r["segundos"] for r in resultados if r["origen"] != "error"] or [0.0]
    print(f"\n== Agente real ({nombre}) ==")
    print(f"Acción correcta: {aciertos / total:.0%} ({aciertos}/{total})")
    if errores:
        bien = sum(r["acierto"] for r in resultados if r["origen"] != "error")
        print(f"Sin contar los {len(errores)} que el modelo no respondió: {bien / max(respondidos, 1):.0%} ({bien}/{respondidos})")
    por_origen = Counter(r["origen"] for r in resultados)
    print("Respondió: " + ", ".join(f"{o} {n}" for o, n in por_origen.most_common()))
    print(f"Tiempo por mensaje: promedio {sum(tiempos) / len(tiempos):.2f} s, máximo {max(tiempos):.2f} s")
    print("\n| # | Mensaje | Esperada | Acción del agente | Origen | Resultado |")
    print("|---|---|---|---|---|---|")
    for n, r in enumerate(resultados, start=1):
        marca = "✅" if r["acierto"] else "❌"
        print(f"| {n} | {r['texto']} | {r['esperada']} | {r['accion']} | {r['origen']} | {marca} |")
    fallos = [r for r in resultados if not r["acierto"]]
    if fallos:
        print("\nRespuestas de los casos fallidos:")
        for r in fallos:
            print(f"  - '{r['texto']}' -> {r['respuesta'][:160]!r}")


def main() -> None:
    import sys

    if "--agente" in sys.argv:
        from app.agente.lc_agente import crear_modelo_desde_entorno

        modelo = crear_modelo_desde_entorno()
        if modelo is None:
            print("Sin GEMINI_API_KEY: el agente real necesita el modelo.")
            return
        pausa = float(os.getenv("EVAL_PAUSA", "0") or 0)
        mostrar_agente(evaluar_agente(modelo, pausa=pausa), os.getenv("GEMINI_MODEL", "gemini"))
        return
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
