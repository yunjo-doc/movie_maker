"""Kling AI Image-to-Video (I2V) 프로바이더

API 문서: https://app.klingai.com/global/dev/document-api
인증: JWT (HS256) — Access Key + Secret Key
"""

import base64
import time
import logging
import jwt
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

KLING_BASE_URL = "https://api.klingai.com"


class KlingI2VProvider:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        model: str = "kling-v2-6",
        duration: int = 5,
        mode: str = "std",
        cfg_scale: float = 0.5,
        poll_interval: int = 10,
        timeout: int = 300,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.model = model
        self.duration = duration
        self.mode = mode
        self.cfg_scale = cfg_scale
        self.poll_interval = poll_interval
        self.timeout = timeout

    def _generate_token(self) -> str:
        """JWT 토큰 생성 (30분 유효)"""
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._generate_token()}",
            "Content-Type": "application/json",
        }

    def generate(
        self,
        image_path: str,
        output_path: str,
        prompt: str = "",
        negative_prompt: str = "blurry, distorted, low quality",
    ) -> str:
        """이미지를 비디오 클립으로 변환

        Args:
            image_path: 입력 이미지 경로
            output_path: 출력 MP4 경로
            prompt: 움직임/애니메이션 설명 (영어)
            negative_prompt: 제외할 요소

        Returns:
            출력 파일 경로
        """
        task_id = self._submit(image_path, prompt, negative_prompt)
        logger.info(f"  Kling 작업 제출: {task_id}")

        video_url = self._poll(task_id)
        logger.info(f"  Kling 생성 완료, 다운로드 중...")

        self._download(video_url, output_path)
        return output_path

    def _submit(self, image_path: str, prompt: str,
                negative_prompt: str) -> str:
        """I2V 작업 제출 → task_id 반환"""
        from PIL import Image as PILImage
        import io

        # JPEG 변환 후 raw base64 (Kling API 요구 형식)
        img = PILImage.open(image_path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        payload = {
            "model_name": self.model,
            "image": image_b64,
            "prompt": prompt,
            "duration": str(self.duration),
            "mode": self.mode,
            "cfg_scale": self.cfg_scale,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        resp = requests.post(
            f"{KLING_BASE_URL}/v1/videos/image2video",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"Kling 제출 실패: {data.get('message', 'unknown error')}"
            )

        return data["data"]["task_id"]

    def _poll(self, task_id: str) -> str:
        """작업 완료까지 폴링 → 비디오 URL 반환"""
        start = time.time()
        while time.time() - start < self.timeout:
            resp = requests.get(
                f"{KLING_BASE_URL}/v1/videos/image2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data["task_status"]

            if status == "succeed":
                videos = data["task_result"]["videos"]
                return videos[0]["url"]
            elif status == "failed":
                msg = data.get("task_status_msg", "unknown")
                raise RuntimeError(f"Kling 생성 실패: {msg}")

            elapsed = int(time.time() - start)
            logger.debug(f"    Kling 폴링 중... ({elapsed}초 경과, 상태: {status})")
            time.sleep(self.poll_interval)

        raise TimeoutError(
            f"Kling 생성 타임아웃 ({self.timeout}초 초과)"
        )

    def _download(self, url: str, output_path: str):
        """비디오 URL → 로컬 파일 다운로드"""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
