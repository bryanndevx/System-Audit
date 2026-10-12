from fastapi import FastAPI

from app.checklists import router as checklists_router

app = FastAPI(
    title="Sistema Inteligente de Auditoría BD"
)

app.include_router(checklists_router)


@app.get("/health")
def verificar_estado():
    return {"estado": "funcionando"}
