"""Step 5: FFmpeg 영상 합성 + BGM 자동 선택"""

import logging
from pipeline.base import Step
from pipeline.context import PipelineContext
from providers.video.ffmpeg_composer import FFmpegComposer
from utils.bgm_selector import select_bgm
from config import config

logger = logging.getLogger(__name__)


class ComposeVideoStep(Step):
    name = "compose_video"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.image_paths:
            raise ValueError("이미지가 없습니다. Step 4를 먼저 실행하세요.")
        if not ctx.audio_path:
            raise ValueError("오디오가 없습니다. Step 2를 먼저 실행하세요.")

        composer = FFmpegComposer(config["video"])

        # segments 구성: 이미지/비디오 클립 + 씬 정보 결합
        segments = []
        for i, img_path in enumerate(ctx.image_paths):
            scene = ctx.scenes[i] if i < len(ctx.scenes) else {}
            clip = ctx.video_clips[i] if i < len(ctx.video_clips) else ""
            seg = {
                "image": img_path,
                "duration": scene.get("duration", 5.0),
                "effect": scene.get("effect", "zoom_in"),
            }
            if clip:
                seg["video_clip"] = clip
            segments.append(seg)

        # BGM 자동 선택 (bgm/ 폴더에서 내용에 맞는 곡)
        bgm_path = None
        bgm_dir = config["video"].get("bgm_dir", "bgm")
        title = ctx.script.get("title", ctx.topic)
        summary = ctx.script.get("summary", "")
        try:
            bgm_path = select_bgm(summary, title, bgm_dir)
            if bgm_path:
                logger.info(f"BGM 선택 완료: {bgm_path}")
        except Exception as e:
            logger.warning(f"BGM 선택 실패 (BGM 없이 진행): {e}")

        output_path = f"{ctx.output_dir}/video.mp4"

        composer.compose(
            segments=segments,
            audio_path=ctx.audio_path,
            subtitle_path=ctx.srt_path,
            output_path=output_path,
            bgm_path=bgm_path,
        )

        ctx.video_path = output_path
        return ctx
