import io
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from services.tesseract_service import MAX_UPLOAD_BYTES, OCRError, extract_text


def image_bytes(format="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format=format)
    return buffer.getvalue()


class TesseractTests(unittest.TestCase):
    @patch("services.tesseract_service.subprocess.run")
    def test_text_and_temporary_file_cleanup(self, run):
        from pathlib import Path

        paths = []

        def recognize(command, **kwargs):
            path = Path(command[1])
            self.assertTrue(path.exists())
            paths.append(path)
            self.assertEqual(command[2:], ["stdout", "-l", "fra+eng", "--psm", "3"])
            return SimpleNamespace(returncode=0, stdout=" Bonjour\n")

        run.side_effect = recognize
        result = extract_text(image_bytes())
        self.assertEqual(result["text"], "Bonjour")
        self.assertFalse(paths[0].exists())

    @patch("services.tesseract_service.subprocess.run")
    def test_invalid_inputs_do_not_start_engine(self, run):
        for data, status in [
            (b"not an image", 422),
            (image_bytes("GIF"), 415),
            (b"x" * (MAX_UPLOAD_BYTES + 1), 413),
        ]:
            with self.subTest(status=status), self.assertRaises(OCRError) as caught:
                extract_text(data)
            self.assertEqual(caught.exception.status_code, status)
        run.assert_not_called()

    @patch("services.tesseract_service.subprocess.run")
    def test_service_failures(self, run):
        for error, status in [
            (FileNotFoundError(), 503),
            (subprocess.TimeoutExpired("tesseract", 60), 504),
        ]:
            run.side_effect = error
            with self.subTest(status=status), self.assertRaises(OCRError) as caught:
                extract_text(image_bytes())
            self.assertEqual(caught.exception.status_code, status)

    @patch("services.tesseract_service.subprocess.run")
    def test_engine_failure_does_not_expose_stderr(self, run):
        run.return_value = SimpleNamespace(returncode=1, stderr="private data")
        with self.assertRaises(OCRError) as caught:
            extract_text(image_bytes())
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("private data", caught.exception.detail)
