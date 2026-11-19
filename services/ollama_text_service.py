"""Connecteur HTTP texte Ollama ; ne journalise ni OCR ni réponse."""
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError
from schemas.extraction_ocr import ExtractionOCR
from services.prompt_loader import load_prompt


class PipelineError(Exception):
    def __init__(self, code, raw=None):
        self.code, self.raw = code, raw
        super().__init__(code)


class OllamaTextService:
    def __init__(self, base_url, model, timeout, num_ctx, temperature):
        self.base_url, self.model, self.timeout = base_url.rstrip('/'), model, timeout
        self.num_ctx, self.temperature = num_ctx, temperature

    def _request(self, path, payload=None):
        request = Request(self.base_url + path, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise PipelineError('OLLAMA_MODEL_NOT_FOUND' if code == 404 else 'OLLAMA_UNAVAILABLE') from None
        except (TimeoutError, socket.timeout):
            raise PipelineError('OLLAMA_TIMEOUT') from None
        except URLError as exc:
            raise PipelineError('OLLAMA_TIMEOUT' if isinstance(exc.reason, (TimeoutError, socket.timeout)) else 'OLLAMA_UNAVAILABLE') from None
        except (ValueError, UnicodeError):
            raise PipelineError('LLM_INVALID_JSON') from None

    def version(self):
        result = self._request('/api/tags')
        try:
            models = result['models']
            match = next((m for m in models if m.get('name') == self.model or m.get('model') == self.model), None)
            if match is None and ':' not in self.model:
                match = next((m for m in models if m.get('name') == self.model + ':latest'), None)
            if match is None:
                raise PipelineError('OLLAMA_MODEL_NOT_FOUND')
            return match.get('digest') or None
        except (TypeError, KeyError, AttributeError):
            raise PipelineError('OLLAMA_UNAVAILABLE') from None

    def structure(self, text):
        prompt = load_prompt('structuration_ocr_v1')
        schema = ExtractionOCR.model_json_schema()
        # Borne conservatrice en octets UTF-8, avec réserve pour le protocole et la réponse.
        # Elle refuse les textes douteux plutôt que de laisser Ollama tronquer silencieusement.
        if len((prompt + text + json.dumps(schema, ensure_ascii=False)).encode('utf-8')) + 1024 > self.num_ctx:
            raise PipelineError('LLM_CONTEXT_EXCEEDED')
        payload = {'model': self.model, 'stream': False, 'format': schema,
                   'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': text}],
                   'options': {'num_ctx': self.num_ctx, 'temperature': self.temperature, 'num_predict': 512}}
        result = self._request('/api/chat', payload)
        try:
            raw = result['message']['content']
            if not isinstance(raw, str):
                raise TypeError
        except (TypeError, KeyError):
            raise PipelineError('LLM_INVALID_JSON') from None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            raise PipelineError('LLM_INVALID_JSON', raw) from None
        try:
            values = ExtractionOCR.model_validate(data).model_dump()
        except ValidationError:
            raise PipelineError('LLM_SCHEMA_VALIDATION_ERROR', raw) from None
        return raw, values
