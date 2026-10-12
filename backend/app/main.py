from fastapi import FastAPI

app = FastAPI(
    title="Sistema Inteligente de Auditoría BD"
)


@app.get("/health")
def verificar_estado():
    return {"estado": "funcionando"}