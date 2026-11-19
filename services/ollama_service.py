import base64
import io
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from jsonschema import ValidationError, validate
from PIL import Image

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from schemas.carte_grise import CARTE_GRISE_SCHEMA
from schemas.classification import ClassificationResult
from services.prompt_loader import load_prompt


class OllamaService:
    def classify(self, image: Image.Image) -> dict:
        schema = ClassificationResult.model_json_schema()
        # La source est renseignée par l'application, pas par le modèle.
        schema["properties"].pop("source")
        schema["required"].remove("source")
        return self._chat(image, load_prompt("classification_system_prompt"), schema, 500)

    def analyse_carte_grise(self, image: Image.Image) -> dict:
        return self._chat(
            image, load_prompt("carte_grise_system_prompt"), CARTE_GRISE_SCHEMA, 2000
        )

    def _chat(self, image: Image.Image, prompt: str, schema: dict, max_tokens: int) -> dict:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": prompt + "\nRéponds uniquement en JSON selon le schéma fourni."},
                {
                    "role": "user",
                    "content": "Analyse ce document.",
                    "images": [base64.b64encode(buffer.getvalue()).decode("ascii")],
                },
            ],
            "options": {"temperature": 0, "num_predict": max_tokens},
        }
        request = Request(
            OLLAMA_BASE_URL.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read())
        except HTTPError as exc:
            detail = (
                f"Modèle Ollama introuvable : {OLLAMA_MODEL}. Configurez OLLAMA_MODEL avec un modèle vision installé."
                if exc.code == 404 else
                "Ollama a refusé la requête. Vérifiez que le modèle prend en charge les images et les sorties JSON structurées."
            )
            raise HTTPException(status_code=502, detail=detail) from None
        except (TimeoutError, socket.timeout):
            raise HTTPException(status_code=504, detail="Délai de réponse Ollama dépassé.") from None
        except URLError:
            raise HTTPException(
                status_code=503,
                detail="Ollama est inaccessible. Démarrez ollama serve et vérifiez OLLAMA_BASE_URL.",
            ) from None
        except (ValueError, UnicodeError):
            raise HTTPException(status_code=502, detail="Réponse Ollama invalide.") from None

        try:
            data = json.loads(result["message"]["content"])
            validate(instance=data, schema=schema)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise HTTPException(status_code=502, detail="La réponse du modèle ne respecte pas le schéma JSON attendu.") from None
        return data
