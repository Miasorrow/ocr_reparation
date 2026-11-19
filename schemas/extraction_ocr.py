"""Validation stricte des cinq valeurs produites par le modèle."""
import re
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, field_validator


class ExtractionOCR(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    immatriculation: str | None
    date_premiere_immatriculation: str | None
    marque: str | None
    modele_vehicule: str | None
    numero_formule: str | None

    @field_validator('*', mode='before')
    @classmethod
    def normalize(cls, value):
        if isinstance(value, str):
            return ' '.join(value.split()) or None
        return value

    @field_validator('date_premiere_immatriculation')
    @classmethod
    def normalize_date(cls, value):
        if value is None:
            return None
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat()
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}', value):
            return datetime.strptime(value, '%d/%m/%Y').date().isoformat()
        raise ValueError('date attendue au format AAAA-MM-JJ ou JJ/MM/AAAA')
