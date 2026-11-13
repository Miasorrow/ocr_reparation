import cv2
import numpy as np

from PIL import Image


class ImagePreprocessor:
    def preprocess(self, image: Image.Image) -> Image.Image:
        image_np = np.array(image.convert("RGB"))

        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)

        gray = cv2.resize(
            gray,
            None,
            fx=2,
            fy=2,
            interpolation=cv2.INTER_CUBIC
        )

        gray = cv2.equalizeHist(gray)

        gray = cv2.GaussianBlur(gray, (3, 3), 0)

        processed_rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

        return Image.fromarray(processed_rgb)