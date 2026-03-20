"""Step 5b: CapCut 드래프트 자동 생성 (선택)

FFmpeg 영상 합성과 병행 가능.
CapCut에서 열어 트랜지션/효과 추가 후 렌더링.
"""

import logging
from pipeline.base import Step
from pipeline.context import PipelineContext
from providers.video.capcut_draft import CapCutDraftGenerator

logger = logging.getLogger(__name__)


class GenerateCapCutDraftStep(Step):
    name = "generate_capcut_draft"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.image_paths:
            raise ValueError("이미지가 없습니다.")
        if not ctx.audio_path:
            raise ValueError("오디오가 없습니다.")

        # 씬별 duration 추출
        durations = []
        for i, img in enumerate(ctx.image_paths):
            if i < len(ctx.scenes):
                durations.append(ctx.scenes[i].get("duration", 5.0))
            else:
                durations.append(5.0)

        title = ctx.script.get("title", ctx.topic)
        generator = CapCutDraftGenerator(project_name=title)

        project_dir = generator.generate(
            image_paths=ctx.image_paths,
            durations=durations,
            audio_path=ctx.audio_path,
            srt_path=ctx.srt_path,
            output_name=f"Auto_{ctx.project_id}",
        )

        logger.info(f"CapCut 프로젝트 생성 완료: {project_dir}")
        logger.info(f"CapCut을 열면 '{title}' 프로젝트가 나타납니다")
        logger.info("트랜지션, 효과, 자막 스타일을 추가한 후 내보내기 하세요")

        return ctx
