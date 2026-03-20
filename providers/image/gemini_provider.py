"""Gemini / Imagen 이미지 생성 Provider"""

import base64
import logging
from pathlib import Path
from google import genai
from google.genai import types
from utils.retry import rate_limit_retry

logger = logging.getLogger(__name__)


class GeminiImageProvider:
    def __init__(self, api_key: str, model: str = "imagen-4.0-generate-001",
                 style_suffix: str = ""):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.style_suffix = style_suffix

    @rate_limit_retry
    def generate(self, prompt: str, output_path: str) -> str:
        """16:9 가로형 이미지 생성"""
        full_prompt = prompt + self.style_suffix

        # Imagen 모델은 generate_images API 사용
        if "imagen" in self.model:
            return self._generate_imagen(full_prompt, output_path)
        else:
            return self._generate_gemini(full_prompt, output_path)

    def _generate_imagen(self, prompt: str, output_path: str) -> str:
        """Imagen 4 API — aspect_ratio 파라미터 지원"""
        response = self.client.models.generate_images(
            model=self.model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
            )
        )
        if response.generated_images:
            img_bytes = response.generated_images[0].image.image_bytes
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(img_bytes)
            return output_path
        raise ValueError("Imagen 응답에 이미지가 없음")

    def _generate_gemini(self, prompt: str, output_path: str) -> str:
        """Gemini Flash 이미지 생성 (폴백용)"""
        wide_prompt = f"Generate a wide landscape image in 16:9 aspect ratio. {prompt}"
        response = self.client.models.generate_content(
            model=self.model,
            contents=wide_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            )
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    image_data = base64.b64decode(image_data)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(image_data)
                return output_path
        raise ValueError("Gemini 응답에 이미지가 없음")
