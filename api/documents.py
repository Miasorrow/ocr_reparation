from fastapi import APIRouter, UploadFile, File

from schemas.classification import ClassificationResult
from services.classifier_service import ClassifierService

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

classifier_service = ClassifierService()


@router.post("/classify", response_model=ClassificationResult)
async def classify_document(file: UploadFile = File(...)):
    return await classifier_service.classify(file)


@router.post("/analyse")
async def analyse_document(file: UploadFile = File(...)):
    return await classifier_service.analyse_carte_grise(file)