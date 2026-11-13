import io
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class OCRError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000


def extract_text(content: bytes) -> dict:
    started = time.perf_counter()
    if len(content) > MAX_UPLOAD_BYTES:
        raise OCRError(413, "Image limitée à 10 Mo.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise OCRError(415, "Seules les images JPEG et PNG sont acceptées.")
            if image.width * image.height > MAX_PIXELS:
                raise OCRError(413, "Image limitée à 25 mégapixels.")
            image.load()
            prepared = ImageOps.exif_transpose(image).convert("RGB")
    except Image.DecompressionBombError:
        raise OCRError(413, "Dimensions de l'image excessives.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise OCRError(422, "Image invalide ou corrompue.") from None

    with tempfile.TemporaryDirectory(prefix="ocr-") as directory:
        path = Path(directory) / "input.png"
        prepared.save(path, format="PNG")
        try:
            result = subprocess.run(
                ["tesseract", str(path), "stdout", "-l", "fra+eng", "--psm", "3"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
        except FileNotFoundError:
            raise OCRError(503, "Tesseract n'est pas installé sur le serveur.") from None
        except subprocess.TimeoutExpired:
            raise OCRError(504, "Le délai OCR de 60 secondes est dépassé.") from None
        if result.returncode:
            raise OCRError(
                503, "Échec Tesseract : vérifier le moteur et les langues fra et eng."
            )

    return {
        "text": result.stdout.strip(),
        "source": "tesseract",
        "language": "fra+eng",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
