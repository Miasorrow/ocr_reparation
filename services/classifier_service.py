from fastapi import UploadFile
from PIL import Image

from schemas.classification import ClassificationResult
from services.bedrock_service import BedrockService
from services.image_preprocessor import ImagePreprocessor
from services.claude_vision_classifier import ClaudeVisionClassifier


class ClassifierService:
    def __init__(self):
        self.preprocessor = ImagePreprocessor()
        self.claude_classifier = ClaudeVisionClassifier()
        self.bedrock_service = BedrockService()

    async def classify(self, file: UploadFile) -> ClassificationResult:
        image = Image.open(file.file)

        processed_image = self.preprocessor.preprocess(image)

        result = self.claude_classifier.classify(processed_image)

        return ClassificationResult(
            is_registration_certificate=result["is_registration_certificate"],
            registration_certificate_type=result["registration_certificate_type"],
            confidence=result["confidence"],
            reason=result["reason"],
            source="claude_vision"
        )

    async def analyse_carte_grise(self, file: UploadFile) -> dict:
        image = Image.open(file.file)
        processed_image = self.preprocessor.preprocess(image)

        return self.bedrock_service.analyse_carte_grise(processed_image)
