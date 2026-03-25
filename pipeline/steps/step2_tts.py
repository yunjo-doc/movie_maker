"""Step 2: TTS + SRT 생성 (config.yaml의 primary/fallback 설정에 따라 자동 선택)"""

import asyncio
import logging
from pipeline.base import Step
from pipeline.context import PipelineContext
from config import config, settings

logger = logging.getLogger(__name__)


class GenerateTTSStep(Step):
    name = "generate_tts"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        chapters = ctx.script.get("chapters", [])
        if not chapters:
            raise ValueError("대본(script)이 비어있습니다. Step 1을 먼저 실행하세요.")

        audio_path = f"{ctx.output_dir}/narration.mp3"
        srt_path = f"{ctx.output_dir}/subtitles.srt"

        primary = config["tts"].get("primary", "edge")
        fallback = config["tts"].get("fallback", "edge")

        try:
            self._run_tts(primary, chapters, audio_path, srt_path)
        except Exception as e:
            logger.warning(f"{primary} TTS 실패: {e}")
            logger.info(f"{fallback} 폴백 시도...")
            self._run_tts(fallback, chapters, audio_path, srt_path)

        ctx.audio_path = audio_path
        ctx.srt_path = srt_path
        return ctx

    def _run_tts(self, engine: str, chapters, audio_path, srt_path):
        if engine == "openai":
            if not settings.openai_api_key:
                raise RuntimeError("OpenAI API 키가 없습니다")
            logger.info("OpenAI TTS로 음성 생성...")
            from providers.tts.openai_tts_provider import OpenAITTSProvider
            provider = OpenAITTSProvider(
                api_key=settings.openai_api_key,
                cfg=config["tts"]["openai"]
            )
            provider.generate_chapters(chapters, audio_path, srt_path)
            logger.info("OpenAI TTS 성공!")
        elif engine == "elevenlabs":
            if not settings.elevenlabs_api_key:
                raise RuntimeError("ElevenLabs API 키가 없습니다")
            logger.info("ElevenLabs TTS로 음성 생성...")
            from providers.tts.elevenlabs_provider import ElevenLabsProvider
            provider = ElevenLabsProvider(
                api_key=settings.elevenlabs_api_key,
                cfg=config["tts"]["elevenlabs"]
            )
            provider.generate_chapters(chapters, audio_path, srt_path)
            logger.info("ElevenLabs TTS 성공!")
        else:
            logger.info("Edge TTS로 음성 생성...")
            from providers.tts.edge_tts_provider import EdgeTTSProvider
            provider = EdgeTTSProvider(config["tts"]["edge"])
            asyncio.run(provider.generate_chapters(chapters, audio_path, srt_path))
            logger.info("Edge TTS 성공!")
