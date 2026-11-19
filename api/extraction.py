"""Import et analyse synchrones d'une image enregistrée localement."""
import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

import config
from persistence.database import Database, FIELDS
from services.extraction_pipeline import ExtractionPipeline
from services.tesseract_service import OCRError, prepare_image

router = APIRouter(prefix='/documents', tags=['Pré-saisie'])


class ExtractionResponse(BaseModel):
    document_id: int
    extraction_id: int
    statut: str
    code_erreur: str | None
    immatriculation: str | None
    date_premiere_immatriculation: str | None
    marque: str | None
    modele_vehicule: str | None
    numero_formule: str | None


@router.post('/extraire', response_model=ExtractionResponse)
def extraire_document(file: UploadFile = File(...)):
    # Route synchrone : FastAPI la lance dans son pool de threads.
    try:
        content = file.file.read(config.OCR_MAX_BYTES + 1)
    finally:
        file.file.close()
    try:
        prepare_image(content, max_bytes=config.OCR_MAX_BYTES, max_pixels=config.OCR_MAX_PIXELS)
    except OCRError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

    db = Database()
    db.initialize()
    directory = Path(os.environ.get('OCR_IMAGE_DIR', Path(__file__).resolve().parents[1] / 'var' / 'images')).resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix='document_', suffix='.image', dir=directory, delete=False) as output:
            path = Path(output.name)
            output.write(content)
        document = db.importer_image(hashlib.sha256(content).hexdigest(), str(path))
        if document['chemin_image'] != str(path):
            path.unlink()
            path = None
    except Exception:
        if path is not None:
            path.unlink(missing_ok=True)
        raise

    extraction_id = ExtractionPipeline(db).run(document['id'])
    with db.connect() as c:
        extraction = c.execute('SELECT * FROM extractions WHERE id=?', (extraction_id,)).fetchone()
    return {'document_id': document['id'], 'extraction_id': extraction_id,
            'statut': extraction['statut'], 'code_erreur': extraction['code_erreur'],
            **{field: extraction[field] for field in FIELDS}}
