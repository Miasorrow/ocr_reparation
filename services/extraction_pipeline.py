"""Exécution synchrone : chaque étape persistée dans une transaction courte."""
import time
from pathlib import Path
import config
from persistence.database import Database
from services.ollama_text_service import OllamaTextService, PipelineError
from services.tesseract_service import extract_text, OCRError

PROMPT_VERSION = 'structuration_ocr_v1'


class ExtractionPipeline:
    def __init__(self, db=None, ollama=None):
        self.db = db or Database()
        self.ollama = ollama or OllamaTextService(config.LOCAL_OLLAMA_BASE_URL, config.LOCAL_OLLAMA_MODEL, config.OLLAMA_TIMEOUT_SECONDS, config.OLLAMA_NUM_CTX, config.OLLAMA_TEMPERATURE)

    def run(self, document_id):
        doc = self.db.document_par_id(document_id)
        if doc is None:
            raise ValueError('document inconnu')
        version_error = None
        try:
            version = self.ollama.version()
        except PipelineError as exc:
            version, version_error = None, exc
        model = self.db.modele('ollama', self.ollama.model, version)
        settings = {'ollama_model': self.ollama.model, 'num_ctx': self.ollama.num_ctx,
                    'temperature': self.ollama.temperature, 'ollama_timeout_seconds': self.ollama.timeout,
                    'tesseract_lang': config.TESSERACT_LANG, 'tesseract_timeout_seconds': config.TESSERACT_TIMEOUT_SECONDS,
                    'ocr_max_bytes': config.OCR_MAX_BYTES, 'ocr_max_pixels': config.OCR_MAX_PIXELS,
                    'tesseract_auto_rotate': config.TESSERACT_AUTO_ROTATE,
                    'tesseract_orientation_confidence': config.TESSERACT_ORIENTATION_CONFIDENCE}
        extraction_id = self.db.creer_extraction(document_id, model['id'], PROMPT_VERSION, settings)
        self.db.etat_extraction(extraction_id, 'running')
        model_started = None
        try:
            try:
                with Path(doc['chemin_image']).open('rb') as f:
                    content = f.read(config.OCR_MAX_BYTES + 1)
            except (OSError, ValueError):
                raise PipelineError('IMAGE_INVALID') from None
            try:
                ocr = extract_text(content, language=config.TESSERACT_LANG, timeout=config.TESSERACT_TIMEOUT_SECONDS,
                                   max_bytes=config.OCR_MAX_BYTES, max_pixels=config.OCR_MAX_PIXELS,
                                   auto_rotate=config.TESSERACT_AUTO_ROTATE,
                                   orientation_confidence=config.TESSERACT_ORIENTATION_CONFIDENCE)
            except OCRError as exc:
                raise PipelineError(exc.code) from None
            self.db.enregistrer_ocr(extraction_id, ocr['text'], round(ocr['duration_ms']))
            if not ocr['text'].strip():
                raise PipelineError('OCR_EMPTY_TEXT')
            if version_error:
                raise version_error
            model_started = time.perf_counter()
            raw, values = self.ollama.structure(ocr['text'])
            duration = round((time.perf_counter() - model_started) * 1000)
            self.db.etat_extraction(extraction_id, 'succeeded', reponse_brute=raw, duree_modele_ms=duration, **values)
        except PipelineError as exc:
            result = {'code_erreur': exc.code}
            if exc.raw is not None:
                result['reponse_brute'] = exc.raw
            if model_started is not None:
                result['duree_modele_ms'] = round((time.perf_counter() - model_started) * 1000)
            self.db.etat_extraction(extraction_id, 'failed', **result)
        except Exception:
            self.db.etat_extraction(extraction_id, 'failed', code_erreur='PIPELINE_ERROR')
            raise
        return extraction_id
