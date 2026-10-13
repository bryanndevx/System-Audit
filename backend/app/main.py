from fastapi import FastAPI

from app.audits import router as audits_router
from app.auth import router as auth_router
from app.checklists import router as checklists_router
from app.external_connections import router as external_connections_router

app = FastAPI(
    title="Sistema Inteligente de Auditoría BD"
)

app.include_router(auth_router)
app.include_router(checklists_router)
app.include_router(external_connections_router)
app.include_router(audits_router)


@app.get("/health")
def verificar_estado():
    return {"estado": "funcionando"}
