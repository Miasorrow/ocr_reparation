from fastapi import UploadFile
from PIL import Image

from schemas.classification import ClassificationResult
from services.ollama_service import OllamaService
from services.image_preprocessor import ImagePreprocessor


class ClassifierService:
    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.ollama_service = OllamaService()

    async def classify(self, file: UploadFile) -> ClassificationResult:
        image = Image.open(file.file)

        processed_image = self.preprocessor.preprocess(image)

        result = self.ollama_service.classify(processed_image)

        return ClassificationResult(
            is_registration_certificate=result["is_registration_certificate"],
            registration_certificate_type=result["registration_certificate_type"],
            confidence=result["confidence"],
            reason=result["reason"],
            source="ollama_vision"
        )

    async def analyse_carte_grise(self, file: UploadFile) -> dict:
        image = Image.open(file.file)
        processed_image = self.preprocessor.preprocess(image)

        return self.ollama_service.analyse_carte_grise(processed_image)
