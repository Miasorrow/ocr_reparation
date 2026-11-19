import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile, HTTPException
from api.extraction import extraire_document
from PIL import Image
from main import app
from persistence.database import Database
from services.ollama_text_service import PipelineError


def image_bytes():
    output = io.BytesIO()
    Image.new('RGB', (30, 30), 'white').save(output, format='PNG')
    return output.getvalue()


class APIExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / 'db.sqlite'
        self.images = Path(self.temp.name) / 'images'
        env = patch.dict(os.environ, {'OCR_DB_PATH': str(self.db_path), 'OCR_IMAGE_DIR': str(self.images)})
        env.start()
        self.addCleanup(env.stop)

    def send(self, content=None):
        return extraire_document(UploadFile(filename='nom-prive.png', file=io.BytesIO(content if content is not None else image_bytes())))

    @patch('services.extraction_pipeline.extract_text', return_value={'text': 'OCR fictif', 'duration_ms': 5})
    @patch('services.ollama_text_service.OllamaTextService.structure')
    @patch('services.ollama_text_service.OllamaTextService.version', return_value='digest-fictif')
    def test_import_result_and_duplicate(self, version, structure, ocr):
        structure.return_value = ('{}', {'immatriculation': '001 AA', 'date_premiere_immatriculation': None, 'marque': 'Fictive', 'modele_vehicule': None, 'numero_formule': None})
        first = self.send()
        second = self.send()
        self.assertIn('/documents/extraire', [route.path for route in app.routes])
        a, b = first, second
        self.assertEqual(a['statut'], 'succeeded')
        self.assertEqual(a['immatriculation'], '001 AA')
        self.assertEqual(a['document_id'], b['document_id'])
        self.assertNotEqual(a['extraction_id'], b['extraction_id'])
        db = Database(self.db_path)
        doc = db.document_par_id(a['document_id'])
        self.assertEqual(Path(doc['chemin_image']).read_bytes(), image_bytes())
        self.assertNotIn('nom-prive', doc['chemin_image'])
        self.assertEqual(len(list(self.images.iterdir())), 1)
        self.assertEqual(len(db.historique(a['document_id'])['extractions']), 2)

    @patch('services.extraction_pipeline.extract_text', return_value={'text': 'OCR fictif', 'duration_ms': 5})
    @patch('services.ollama_text_service.OllamaTextService.version', side_effect=PipelineError('OLLAMA_UNAVAILABLE'))
    def test_error_is_persisted(self, version, ocr):
        result = self.send()
        data = result
        self.assertEqual((data['statut'], data['code_erreur']), ('failed', 'OLLAMA_UNAVAILABLE'))
        record = Database(self.db_path).historique(data['document_id'])['extractions'][0]
        self.assertEqual(record['texte_ocr'], 'OCR fictif')

    def test_invalid_image_not_saved(self):
        with self.assertRaises(HTTPException) as caught:
            self.send(b'pas une image')
        self.assertEqual(caught.exception.status_code, 422)
        self.assertFalse(self.db_path.exists())
        self.assertFalse(self.images.exists())

    @patch('services.extraction_pipeline.extract_text', return_value={'text': 'OCR fictif', 'duration_ms': 5})
    @patch('services.ollama_text_service.OllamaTextService.version', side_effect=PipelineError('OLLAMA_UNAVAILABLE'))
    def test_reimport_repairs_missing_file(self, version, ocr):
        first = self.send()
        db = Database(self.db_path)
        Path(db.document_par_id(first['document_id'])['chemin_image']).unlink()
        second = self.send()
        self.assertEqual(first['document_id'], second['document_id'])
        self.assertTrue(Path(db.document_par_id(first['document_id'])['chemin_image']).is_file())


if __name__ == '__main__':
    unittest.main()
