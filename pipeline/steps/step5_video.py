"""Step 5: FFmpeg 영상 합성 + 챕터별 BGM 자동 선택"""

import logging
from pipeline.base import Step
from pipeline.context import PipelineContext
from providers.video.ffmpeg_composer import FFmpegComposer
from utils.bgm_selector import select_bgm_per_chapter
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

        # 챕터별 BGM 선택
        bgm_paths = []
        bgm_dir = config["video"].get("bgm_dir", "bgm")
        chapters = ctx.script.get("chapters", [])
        try:
            chapter_info = [
                {"chapter_title": ch.get("chapter_title", ""),
                 "tone": ctx.brief.get("chapters", [{}])[i].get("tone", "")
                         if i < len(ctx.brief.get("chapters", [])) else ""}
                for i, ch in enumerate(chapters)
            ]
            bgm_paths = select_bgm_per_chapter(chapter_info, bgm_dir)
            if bgm_paths:
                logger.info(f"챕터별 BGM 선택 완료: {len(bgm_paths)}곡")
        except Exception as e:
            logger.warning(f"BGM 선택 실패 (BGM 없이 진행): {e}")

        output_path = f"{ctx.output_dir}/video.mp4"

        composer.compose(
            segments=segments,
            audio_path=ctx.audio_path,
            subtitle_path=ctx.srt_path,
            output_path=output_path,
            bgm_path=bgm_paths[0] if bgm_paths else None,
            bgm_paths=bgm_paths,
            chapters=chapters,
        )

        ctx.video_path = output_path
        return ctx
