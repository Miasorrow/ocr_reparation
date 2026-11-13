from fastapi import FastAPI

from api.documents import router as documents_router
from api.ocr import router as ocr_router

app = FastAPI(
    title="Document AI API",
    version="1.0.0",
    description="API de classification de carte grise avec OpenCV et Claude Vision."
)

app.include_router(documents_router)
app.include_router(ocr_router)


@app.get("/v1/health")
def health():
    return {"status": "ok"}

