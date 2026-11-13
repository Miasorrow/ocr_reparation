import io

import boto3
from PIL import Image

from config import AWS_REGION, CLAUDE_MODEL_ID
from schemas.carte_grise import TOOL_CONFIG
from services.prompt_loader import load_prompt


class BedrockService:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION
        )

    def analyse_carte_grise(self, image: Image.Image) -> dict:
        image_bytes = self.image_to_jpeg_bytes(image)
        prompt = load_prompt("carte_grise_system_prompt")

        response = self.client.converse(
            modelId=CLAUDE_MODEL_ID,
            system=[
                {
                    "text": prompt
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "image": {
                                "format": "jpeg",
                                "source": {
                                    "bytes": image_bytes
                                }
                            }
                        },
                        {
                            "text": "Analyse ce document."
                        }
                    ]
                }
            ],
            toolConfig=TOOL_CONFIG,
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 2000
            }
        )

        return self.extract_tool_input(response)

    def extract_tool_input(self, response: dict) -> dict:
        for block in response["output"]["message"]["content"]:
            if "toolUse" in block:
                return block["toolUse"]["input"]

        raise ValueError("La reponse Bedrock ne contient aucun toolUse.")

    def image_to_jpeg_bytes(self, image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=90
        )

        return buffer.getvalue()
