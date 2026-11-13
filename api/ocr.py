from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from services.tesseract_service import MAX_UPLOAD_BYTES, OCRError, extract_text


class OCRResult(BaseModel):
    text: str
    source: str
    language: str
    duration_ms: float


router = APIRouter(prefix="/documents", tags=["OCR local"])


@router.post("/ocr", response_model=OCRResult)
def read_document(file: UploadFile = File(...)):
    # Une route synchrone est exécutée dans le thread pool de FastAPI.
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return extract_text(content)
    except OCRError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
