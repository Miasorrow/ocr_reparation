import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from PIL import Image
from persistence.database import Database, FIELDS
from services.extraction_pipeline import ExtractionPipeline
from services.ollama_text_service import OllamaTextService, PipelineError
from services.tesseract_service import extract_text, OCRError


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        Image.new('RGB', (20, 20), 'white').save(self.path / 'image.png')
        self.db = Database(self.path / 'db.sqlite')
        self.db.initialize()
        self.doc = self.db.document('a'*64, self.path / 'image.png')['id']
        self.client = OllamaTextService('http://localhost:11434', 'qwen3:4b-instruct', 2, 4096, 0)
        self.pipeline = ExtractionPipeline(self.db, self.client)
        self.data = dict(immatriculation='  001 AA  ', date_premiere_immatriculation='01/02/2020', marque=' Fictive ', modele_vehicule=None, numero_formule=' 000123 ')

    def result(self, content):
        response = json.dumps({'message': {'content': content}}).encode()
        return SimpleNamespace(__enter__=None), response

    def run_pipeline(self, raw=None, ocr='texte fictif', failure=None):
        raw = raw if raw is not None else json.dumps(self.data)
        with patch.object(self.client, 'version', return_value='digest-fictif'), patch('services.extraction_pipeline.extract_text', return_value={'text': ocr, 'duration_ms': 3}), patch.object(self.client, '_request', side_effect=failure if failure else lambda *args: {'message': {'content': raw}}):
            x = self.pipeline.run(self.doc)
        return next(r for r in self.db.historique(self.doc)['extractions'] if r['id'] == x)

    def test_success_retry_and_human_validation(self):
        values = dict.fromkeys(FIELDS); values['marque'] = 'Humain'
        states = {f: 'known' if f == 'marque' else 'absent' for f in FIELDS}
        v = self.db.valider(self.doc, values, states)
        row = self.run_pipeline()
        self.assertEqual(row['statut'], 'succeeded')
        self.assertEqual(row['immatriculation'], '001 AA')
        self.assertEqual(row['numero_formule'], '000123')
        self.assertEqual(row['date_premiere_immatriculation'], '2020-02-01')
        self.assertIsNone(row['modele_vehicule'])
        self.assertNotEqual(row['id'], self.run_pipeline()['id'])
        self.assertEqual(self.db.derniere_validation(self.doc)['id'], v)
        self.assertEqual(self.db.derniere_validation(self.doc)['marque'], 'Humain')

    def test_invalid_outputs_and_ocr_retained(self):
        extra = dict(self.data, autre='x')
        wrong_type = dict(self.data, marque=42)
        bad_date = dict(self.data, date_premiere_immatriculation='31/02/2020')
        for raw, code in [('invalid', 'LLM_INVALID_JSON'), (json.dumps(extra), 'LLM_SCHEMA_VALIDATION_ERROR'), (json.dumps(wrong_type), 'LLM_SCHEMA_VALIDATION_ERROR'), (json.dumps(bad_date), 'LLM_SCHEMA_VALIDATION_ERROR')]:
            with self.subTest(code=code, raw=raw):
                row = self.run_pipeline(raw)
                self.assertEqual(row['code_erreur'], code)
                self.assertEqual(row['texte_ocr'], 'texte fictif')
                self.assertEqual(row['reponse_brute'], raw)
                self.assertIsNone(row['marque'])

    def test_empty_ocr_and_failures(self):
        row = self.run_pipeline(ocr='')
        self.assertEqual(row['code_erreur'], 'OCR_EMPTY_TEXT')
        for code in ['OLLAMA_UNAVAILABLE', 'OLLAMA_MODEL_NOT_FOUND', 'OLLAMA_TIMEOUT', 'LLM_CONTEXT_EXCEEDED']:
            row = self.run_pipeline(failure=PipelineError(code))
            self.assertEqual(row['code_erreur'], code)
            self.assertEqual(row['texte_ocr'], 'texte fictif')
        with patch.object(self.client, 'version', side_effect=PipelineError('OLLAMA_UNAVAILABLE')), patch('services.extraction_pipeline.extract_text', return_value={'text': 'texte fictif', 'duration_ms': 3}):
            x = self.pipeline.run(self.doc)
        row = self.db.historique(self.doc)['extractions'][-1]
        self.assertEqual((row['id'], row['code_erreur'], row['texte_ocr']), (x, 'OLLAMA_UNAVAILABLE', 'texte fictif'))

    def test_ollama_http_errors(self):
        for exc, code in [(URLError('refused'), 'OLLAMA_UNAVAILABLE'), (TimeoutError(), 'OLLAMA_TIMEOUT'), (HTTPError('url', 404, 'missing', {}, io.BytesIO()), 'OLLAMA_MODEL_NOT_FOUND')]:
            with self.subTest(code=code), patch('services.ollama_text_service.urlopen', side_effect=exc), self.assertRaises(PipelineError) as caught:
                self.client.version()
            self.assertEqual(caught.exception.code, code)
        with patch.object(self.client, '_request', return_value={'models': []}), self.assertRaises(PipelineError) as caught:
            self.client.version()
        self.assertEqual(caught.exception.code, 'OLLAMA_MODEL_NOT_FOUND')

    def test_context_and_request(self):
        with patch.object(self.client, '_request') as request, self.assertRaises(PipelineError) as caught:
            self.client.structure('a' * 10000)
        self.assertEqual(caught.exception.code, 'LLM_CONTEXT_EXCEEDED')
        request.assert_not_called()
        with patch.object(self.client, '_request', return_value={'message': {'content': json.dumps(self.data)}}) as request:
            self.client.structure('texte fictif')
        payload = request.call_args.args[1]
        self.assertFalse(payload['stream'])
        self.assertEqual(payload['options']['num_ctx'], 4096)
        self.assertEqual(payload['format']['additionalProperties'], False)

    def test_tesseract_errors(self):
        image = (self.path / 'image.png').read_bytes()
        cases = [(FileNotFoundError(), 'TESSERACT_NOT_INSTALLED'), (subprocess.TimeoutExpired('tesseract', 1), 'OCR_TIMEOUT')]
        for error, code in cases:
            with patch('services.tesseract_service.subprocess.run', side_effect=error), self.assertRaises(OCRError) as caught:
                extract_text(image, language='fra')
            self.assertEqual(caught.exception.code, code)
        with patch('services.tesseract_service.subprocess.run', return_value=SimpleNamespace(returncode=1, stderr='Failed loading language')):
            with self.assertRaises(OCRError) as caught:
                extract_text(image, language='fra')
            self.assertEqual(caught.exception.code, 'TESSERACT_LANGUAGE_MISSING')
        with patch.object(self.client, 'version', return_value=None), patch('services.extraction_pipeline.extract_text', side_effect=OCRError(504, 'timeout', 'OCR_TIMEOUT')):
            self.pipeline.run(self.doc)
        self.assertEqual(self.db.historique(self.doc)['extractions'][-1]['code_erreur'], 'OCR_TIMEOUT')


if __name__ == '__main__':
    unittest.main()
