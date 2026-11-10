import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agente.rutas import get_modelo_chat
from app.agente.rutas import router as agente_router
from app.catalogo import router as catalogo_router
from app.clientes_rutas import router as clientes_router
from app.contacto import router as contacto_router
from app.conversaciones import router as conversaciones_router
from app.metricas import router as metricas_router
from app.ordenes import router as ordenes_router
from app.webhook import router as webhook_router

logger = logging.getLogger("joyeria.main")


def _calentar_agente() -> None:
    try:
        from app.agente.lc_agente import calentar_modelo

        calentar_modelo(get_modelo_chat())
    except Exception:
        logger.warning("No se pudo preparar el agente al iniciar", exc_info=True)


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    # En segundo plano: el servidor atiende de inmediato y el agente se calienta en paralelo.
    threading.Thread(target=_calentar_agente, daemon=True).start()
    yield


app = FastAPI(title="Joyería Xavier API", version="0.1.0", lifespan=ciclo_de_vida)
app.include_router(webhook_router)
app.include_router(catalogo_router)
app.include_router(contacto_router)
app.include_router(agente_router)
app.include_router(clientes_router)
app.include_router(ordenes_router)
app.include_router(conversaciones_router)
app.include_router(metricas_router)


@app.get("/health")
def health():
    return {"status": "ok"}
