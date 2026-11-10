from fastapi import FastAPI

from app.agente.rutas import router as agente_router
from app.catalogo import router as catalogo_router
from app.clientes_rutas import router as clientes_router
from app.contacto import router as contacto_router
from app.conversaciones import router as conversaciones_router
from app.ordenes import router as ordenes_router
from app.webhook import router as webhook_router

app = FastAPI(title="Joyería Xavier API", version="0.1.0")
app.include_router(webhook_router)
app.include_router(catalogo_router)
app.include_router(contacto_router)
app.include_router(agente_router)
app.include_router(clientes_router)
app.include_router(ordenes_router)
app.include_router(conversaciones_router)


@app.get("/health")
def health():
    return {"status": "ok"}
