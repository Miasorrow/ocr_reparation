import base64
import io
import json

import boto3

from PIL import Image

from config import AWS_REGION, CLAUDE_MODEL_ID


class ClaudeVisionClassifier:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION
        )

    def classify(self, image: Image.Image) -> dict:
        image_base64 = self.image_to_base64(image)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": self.build_prompt(),
                        },
                    ],
                }
            ],
        }

        response = self.client.invoke_model(
            modelId=CLAUDE_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())
        text_response = response_body["content"][0]["text"]

        return json.loads(text_response)

    def build_prompt(self) -> str:
        return """
Tu es un expert des certificats d'immatriculation.

Analyse l'image fournie.

Tu dois déterminer :
1. Si le document est une carte grise / certificat d'immatriculation.
2. Si oui, quel type de carte grise.

Types possibles :
- french_siv : carte grise française moderne
- french_old_fni : ancienne carte grise française
- provisional_cpi : certificat provisoire d'immatriculation
- foreign : certificat d'immatriculation étranger
- unknown : inconnu

Réponds uniquement avec un JSON strict au format suivant :

{
  "is_registration_certificate": true,
  "registration_certificate_type": "french_siv",
  "confidence": 0.95,
  "reason": "Explication courte"
}
"""

    def image_to_base64(self, image: Image.Image) -> str:
        buffer = io.BytesIO()

        image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=90
        )

        return base64.b64encode(buffer.getvalue()).decode("utf-8")