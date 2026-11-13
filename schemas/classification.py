from pydantic import BaseModel


class ClassificationResult(BaseModel):
    is_registration_certificate: bool
    registration_certificate_type: str
    confidence: float
    reason: str
    source: str