"""Pexels/Pixabay 스톡 이미지 폴백 Provider"""

import logging
import requests
from utils.retry import api_retry

logger = logging.getLogger(__name__)


class StockImageProvider:
    def __init__(self, pexels_key: str = "", pixabay_key: str = ""):
        self.pexels_key = pexels_key
        self.pixabay_key = pixabay_key

    @api_retry
    def search_and_download(self, keyword: str, output_path: str) -> str:
        """키워드로 스톡 이미지 검색 + 다운로드"""
        if self.pexels_key:
            return self._pexels_download(keyword, output_path)
        elif self.pixabay_key:
            return self._pixabay_download(keyword, output_path)
        raise ValueError("스톡 이미지 API 키 없음 (Pexels 또는 Pixabay)")

    def _pexels_download(self, keyword: str, output_path: str) -> str:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": keyword, "per_page": 1, "orientation": "landscape"},
            headers={"Authorization": self.pexels_key},
            timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            raise ValueError(f"Pexels 결과 없음: {keyword}")

        img_url = photos[0]["src"]["large2x"]
        img_resp = requests.get(img_url, timeout=60)
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        logger.info(f"Pexels 이미지 다운로드: {keyword} → {output_path}")
        return output_path

    def _pixabay_download(self, keyword: str, output_path: str) -> str:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": self.pixabay_key, "q": keyword,
                "per_page": 3, "orientation": "horizontal",
                "image_type": "photo",
            },
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        if not hits:
            raise ValueError(f"Pixabay 결과 없음: {keyword}")

        img_url = hits[0]["largeImageURL"]
        img_resp = requests.get(img_url, timeout=60)
        with open(output_path, "wb") as f:
            f.write(img_resp.content)
        logger.info(f"Pixabay 이미지 다운로드: {keyword} → {output_path}")
        return output_path
