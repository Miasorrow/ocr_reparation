import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from fastapi import HTTPException
from PIL import Image

from schemas.carte_grise import CARTE_GRISE_SCHEMA
from services.ollama_service import OllamaService


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.service = OllamaService()
        self.image = Image.new("RGB", (8, 8), "white")

    def response(self, mock, content):
        mock.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"message": {"content": json.dumps(content)}}
        ).encode()

    @patch("services.ollama_service.urlopen")
    def test_classification_request_and_response(self, mock):
        expected = dict(is_registration_certificate=True,
                        registration_certificate_type="french_siv",
                        confidence=0.9, reason="Document lisible")
        self.response(mock, expected)
        self.assertEqual(self.service.classify(self.image), expected)
        request = mock.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(request.full_url.endswith("/api/chat"))
        self.assertFalse(payload["stream"])
        self.assertTrue(payload["messages"][1]["images"][0])
        self.assertNotIn("source", payload["format"]["required"])

    @patch("services.ollama_service.urlopen")
    def test_extraction_schema(self, mock):
        expected = dict(is_carte_grise=False, confidence=0, document_type="unknown",
                        plate={}, formula_number={}, driver_license="", fields={},
                        missing_fields=["plate"])
        self.response(mock, expected)
        self.assertEqual(self.service.analyse_carte_grise(self.image), expected)
        self.assertEqual(json.loads(mock.call_args.args[0].data)["format"], CARTE_GRISE_SCHEMA)

    @patch("services.ollama_service.urlopen")
    def test_invalid_output(self, mock):
        for content in ({}, {"confidence": "incorrect"}, []):
            self.response(mock, content)
            with self.assertRaises(HTTPException) as caught:
                self.service.classify(self.image)
            self.assertEqual(caught.exception.status_code, 502)

    @patch("services.ollama_service.urlopen")
    def test_connection_errors(self, mock):
        for error, status in [(URLError("refused"), 503), (TimeoutError(), 504),
                              (HTTPError("url", 404, "missing", {}, io.BytesIO()), 502)]:
            mock.side_effect = error
            with self.assertRaises(HTTPException) as caught:
                self.service.classify(self.image)
            self.assertEqual(caught.exception.status_code, status)
