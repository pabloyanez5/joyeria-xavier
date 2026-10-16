from fastapi import FastAPI
from app.webhook import router as webhook_router


app = FastAPI(title="Joyería Xavier API", version="0.1.0")
app.include_router(webhook_router)

@app.get("/health")
def health():
    return {"status": "ok"}