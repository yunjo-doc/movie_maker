"""Step 4b: Image-to-Video 클립 생성 (Kling AI)

스토리보드에서 use_i2v=true로 표시된 씬(약 20%)을
Kling AI로 변환하여 비디오 클립을 생성한다.
Kling API 키가 없으면 자동으로 건너뛴다.
"""

import logging
from pathlib import Path
from pipeline.base import Step
from pipeline.context import PipelineContext
from providers.video.kling_provider import KlingI2VProvider
from config import settings, config

logger = logging.getLogger(__name__)


class GenerateI2VClipsStep(Step):
    name = "generate_i2v_clips"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not settings.kling_access_key or not settings.kling_secret_key:
            logger.warning("Kling API 키 없음 — I2V 단계 건너뜀")
            return ctx

        if not ctx.image_paths:
            logger.warning("이미지가 없어 I2V 건너뜀")
            return ctx

        i2v_scenes = [
            (i, s) for i, s in enumerate(ctx.scenes)
            if s.get("use_i2v") and i < len(ctx.image_paths)
        ]

        if not i2v_scenes:
            logger.info("I2V 대상 씬 없음")
            return ctx

        cfg = config.get("i2v", {})
        provider = KlingI2VProvider(
            access_key=settings.kling_access_key,
            secret_key=settings.kling_secret_key,
            model=cfg.get("model", "kling-v2-6"),
            duration=cfg.get("duration", 5),
            mode=cfg.get("mode", "std"),
            cfg_scale=cfg.get("cfg_scale", 0.5),
            poll_interval=cfg.get("poll_interval", 10),
            timeout=cfg.get("timeout", 300),
        )

        clips_dir = Path(ctx.output_dir) / "clips"
        clips_dir.mkdir(exist_ok=True)

        total = len(i2v_scenes)
        for seq, (idx, scene) in enumerate(i2v_scenes):
            image_path = ctx.image_paths[idx]
            clip_path = str(clips_dir / f"clip_{scene.get('scene_id', idx+1):03d}.mp4")
            motion_prompt = scene.get("motion_prompt", "gentle cinematic motion")

            logger.info(f"  [{seq+1}/{total}] I2V 생성: 씬 {scene.get('scene_id', idx+1)}")

            try:
                provider.generate(
                    image_path=image_path,
                    output_path=clip_path,
                    prompt=motion_prompt,
                )
                ctx.video_clips[idx] = clip_path
                logger.info(f"    I2V 성공: {clip_path}")
            except Exception as e:
                logger.warning(f"    I2V 실패 (Ken Burns 폴백): {e}")
                # 실패 시 video_clips[idx]는 빈 문자열 → Ken Burns로 처리

        success = sum(1 for v in ctx.video_clips if v)
        logger.info(f"I2V 완료: {success}/{total}개 클립 생성")
        return ctx
