from functools import lru_cache

from fastapi import APIRouter, UploadFile, File

from schemas.classification import ClassificationResult

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

@lru_cache
def get_classifier_service():
    from services.classifier_service import ClassifierService

    return ClassifierService()


@router.post("/classify", response_model=ClassificationResult)
async def classify_document(file: UploadFile = File(...)):
    return await get_classifier_service().classify(file)


@router.post("/analyse")
async def analyse_document(file: UploadFile = File(...)):
    return await get_classifier_service().analyse_carte_grise(file)