import os


# Remplacer ce nom fictif par le nom exact affiché par `ollama list`.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mon-modele-vision:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

# Paramètres du pipeline texte local, indépendants du connecteur vision existant.
LOCAL_OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3:4b-instruct')
LOCAL_OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_NUM_CTX = int(os.getenv('OLLAMA_NUM_CTX', '4096'))
OLLAMA_TEMPERATURE = float(os.getenv('OLLAMA_TEMPERATURE', '0'))
TESSERACT_LANG = os.getenv('TESSERACT_LANG', 'fra')
TESSERACT_TIMEOUT_SECONDS = float(os.getenv('TESSERACT_TIMEOUT_SECONDS', '60'))
OCR_MAX_BYTES = int(os.getenv('OCR_MAX_BYTES', str(10 * 1024 * 1024)))
OCR_MAX_PIXELS = int(os.getenv('OCR_MAX_PIXELS', '25000000'))

TESSERACT_AUTO_ROTATE = os.getenv('TESSERACT_AUTO_ROTATE', '1').lower() in ('1', 'true', 'yes')
TESSERACT_ORIENTATION_CONFIDENCE = float(os.getenv('TESSERACT_ORIENTATION_CONFIDENCE', '4'))
