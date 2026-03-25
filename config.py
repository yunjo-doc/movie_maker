"""설정 관리: .env (API 키) + config.yaml (파라미터)"""

import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

_PROJECT_ROOT = Path(__file__).parent

# .env 로드 (한글 경로 문제 우회: dotenv로 직접 로드)
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(str(_env_path), encoding="utf-8")


class Settings:
    """환경 변수에서 API 키 로드"""
    @property
    def anthropic_api_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def openai_api_key(self) -> str:
        return os.getenv("OPENAI_API_KEY", "")

    @property
    def elevenlabs_api_key(self) -> str:
        return os.getenv("ELEVENLABS_API_KEY", "")

    @property
    def pexels_api_key(self) -> str:
        return os.getenv("PEXELS_API_KEY", "")

    @property
    def pixabay_api_key(self) -> str:
        return os.getenv("PIXABAY_API_KEY", "")

    @property
    def kling_access_key(self) -> str:
        return os.getenv("KLING_ACCESS_KEY", "")

    @property
    def kling_secret_key(self) -> str:
        return os.getenv("KLING_SECRET_KEY", "")

    @property
    def youtube_client_id(self) -> str:
        return os.getenv("YOUTUBE_CLIENT_ID", "")

    @property
    def youtube_client_secret(self) -> str:
        return os.getenv("YOUTUBE_CLIENT_SECRET", "")


settings = Settings()


def load_config(path: str = None) -> dict:
    config_path = path or str(_PROJECT_ROOT / "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
