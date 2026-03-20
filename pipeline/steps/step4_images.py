"""Step 4: 이미지 배치 생성 (3단계 폴백)"""

import time
import shutil
import logging
from pathlib import Path
from pipeline.base import Step
from pipeline.context import PipelineContext
from providers.image.gemini_provider import GeminiImageProvider
from providers.image.stock_provider import StockImageProvider
from config import settings, config

logger = logging.getLogger(__name__)


class GenerateImagesStep(Step):
    name = "generate_images"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        images_dir = Path(ctx.output_dir) / "images"
        images_dir.mkdir(exist_ok=True)

        cfg = config["images"]

        # brief에 visual_style이 있으면 우선 사용
        brief_vs = ctx.brief.get("visual_style", {}) if ctx.brief else {}
        style_suffix = brief_vs.get("style_suffix") or cfg.get("style_suffix", "")

        gemini = GeminiImageProvider(
            api_key=settings.gemini_api_key,
            model=cfg["model"],
            style_suffix=style_suffix,
        )

        stock = None
        if settings.pexels_api_key or settings.pixabay_api_key:
            stock = StockImageProvider(
                pexels_key=settings.pexels_api_key,
                pixabay_key=settings.pixabay_api_key,
            )

        delay = cfg["batch_delay"]
        max_retries = cfg["max_retries"]
        paths = []
        last_success = None

        total = len(ctx.scenes)
        for i, scene in enumerate(ctx.scenes):
            output_path = str(images_dir / f"scene_{scene.get('scene_id', i+1):03d}.png")
            logger.info(f"  [{i+1}/{total}] 이미지 생성...")

            success = False

            # --- 폴백 체인 ---

            # 1차: Gemini API (최대 max_retries회, 프롬프트 단순화)
            prompt = scene.get("prompt_en", "a beautiful landscape")
            for attempt in range(max_retries):
                try:
                    gemini.generate(prompt, output_path)
                    success = True
                    logger.info(f"    Gemini 성공 (시도 {attempt+1})")
                    break
                except Exception as e:
                    logger.warning(f"    Gemini 시도 {attempt+1} 실패: {e}")
                    prompt = self._simplify_prompt(prompt)
                    time.sleep(3)

            # 2차: 스톡 이미지
            if not success and stock:
                keyword = scene.get("search_keyword", "nature landscape")
                logger.info(f"    스톡 이미지 폴백: '{keyword}'")
                try:
                    stock.search_and_download(keyword, output_path)
                    success = True
                except Exception as e:
                    logger.warning(f"    스톡 이미지 실패: {e}")

            # 3차: 이전 씬 이미지 재사용
            if not success and last_success:
                logger.info("    이전 씬 이미지 재사용")
                shutil.copy2(last_success, output_path)
                success = True

            if success:
                last_success = output_path
                paths.append(output_path)
            else:
                logger.error(f"    씬 {scene.get('scene_id', i+1)} 완전 실패!")
                paths.append(None)

            # rate limit 대응
            if i < total - 1:
                time.sleep(delay)

        # None 채우기 (가장 가까운 성공 이미지)
        for i in range(len(paths)):
            if paths[i] is None:
                for j in range(i - 1, -1, -1):
                    if paths[j]:
                        paths[i] = paths[j]
                        break
                if paths[i] is None:
                    for j in range(i + 1, len(paths)):
                        if paths[j]:
                            paths[i] = paths[j]
                            break

        ctx.image_paths = [p for p in paths if p]
        ctx.video_clips = [""] * len(ctx.image_paths)
        logger.info(f"이미지 생성 완료: {len(ctx.image_paths)}/{total}장")
        return ctx

    @staticmethod
    def _simplify_prompt(prompt: str) -> str:
        """프롬프트를 단순화하여 콘텐츠 정책 거부 회피"""
        words = prompt.split(",")
        if len(words) > 4:
            return ", ".join(words[:4]).strip() + ", simple clean illustration"
        return prompt + ", simple, clean, safe"
