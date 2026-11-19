import io
import re
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class OCRError(Exception):
    def __init__(self, status_code: int, detail: str, code: str = "IMAGE_INVALID"):
        self.code = code
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 25_000_000


def prepare_image(content: bytes, *, max_bytes=MAX_UPLOAD_BYTES, max_pixels=MAX_PIXELS):
    if len(content) > max_bytes:
        raise OCRError(413, "Image limitée à 10 Mo.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise OCRError(415, "Seules les images JPEG et PNG sont acceptées.")
            if image.width * image.height > max_pixels:
                raise OCRError(413, "Image limitée à 25 mégapixels.")
            image.load()
            prepared = ImageOps.exif_transpose(image).convert("RGB")
    except Image.DecompressionBombError:
        raise OCRError(413, "Dimensions de l'image excessives.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise OCRError(422, "Image invalide ou corrompue.") from None

    return prepared


def extract_text(content: bytes, *, language="fra+eng", timeout=60, max_bytes=MAX_UPLOAD_BYTES, max_pixels=MAX_PIXELS, auto_rotate=False, orientation_confidence=4.0) -> dict:
    started = time.perf_counter()
    prepared = prepare_image(content, max_bytes=max_bytes, max_pixels=max_pixels)
    with tempfile.TemporaryDirectory(prefix="ocr-") as directory:
        path = Path(directory) / "input.png"
        prepared.save(path, format="PNG")
        rotation = 0
        if auto_rotate:
            # L'orientation OSD est facultative : si elle échoue, conserver l'image.
            try:
                osd = subprocess.run(
                    ["tesseract", str(path), "stdout", "-l", "osd", "--psm", "0"],
                    capture_output=True, text=True, encoding="utf-8",
                    timeout=min(15, max(0.01, timeout - (time.perf_counter() - started))), check=False,
                )
                angle = re.search(r"(?m)^Rotate:\s*(0|90|180|270)\s*$", osd.stdout or "")
                confidence = re.search(r"(?m)^Orientation confidence:\s*([0-9.]+)\s*$", osd.stdout or "")
                if osd.returncode == 0 and angle and confidence and float(confidence.group(1)) >= orientation_confidence:
                    rotation = int(angle.group(1))
                    if rotation:
                        prepared.rotate(-rotation, expand=True).save(path, format="PNG")
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                pass
        remaining = timeout - (time.perf_counter() - started)
        if remaining <= 0:
            raise OCRError(504, "Le délai OCR est dépassé.", "OCR_TIMEOUT")
        try:
            result = subprocess.run(
                ["tesseract", str(path), "stdout", "-l", language, "--psm", "3"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=remaining,
                check=False,
            )
        except FileNotFoundError:
            raise OCRError(503, "Tesseract n'est pas installé sur le serveur.", "TESSERACT_NOT_INSTALLED") from None
        except subprocess.TimeoutExpired:
            raise OCRError(504, "Le délai OCR est dépassé.", "OCR_TIMEOUT") from None
        if result.returncode:
            stderr = getattr(result, "stderr", "") or ""
            if "Failed loading language" in stderr or "Error opening data file" in stderr or "Could not initialize tesseract" in stderr:
                raise OCRError(503, "Langue Tesseract indisponible.", "TESSERACT_LANGUAGE_MISSING")
            raise OCRError(
                503, "Échec Tesseract.", "TESSERACT_ERROR"
            )

    return {
        "text": result.stdout.strip(),
        "source": "tesseract",
        "language": language,
        "rotation_degrees": rotation,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
