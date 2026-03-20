"""Step 6b: YouTube 메타데이터 + 챕터 마커 자동 생성 (Claude API)"""

import json
import logging
import anthropic
from pipeline.base import Step
from pipeline.context import PipelineContext
from utils.retry import api_retry
from config import settings, config

logger = logging.getLogger(__name__)


class GenerateMetadataStep(Step):
    name = "generate_metadata"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        summary = ctx.script.get("summary", ctx.topic)
        title_hint = ctx.script.get("title", "")

        # 챕터 타임스탬프 생성
        chapters_text = self._build_chapter_timestamps(ctx)

        metadata = self._generate(ctx.topic, summary, title_hint, chapters_text)

        with open(f"{ctx.output_dir}/metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"메타데이터 생성: {metadata.get('title', '')}")
        ctx.metadata = metadata
        return ctx

    def _build_chapter_timestamps(self, ctx: PipelineContext) -> str:
        """스토리보드 씬 + 스크립트 챕터에서 타임스탬프 계산"""
        chapters = ctx.script.get("chapters", [])
        scenes = ctx.scenes or []

        if not chapters or not scenes:
            return ""

        # 챕터별 시작 시간 계산
        num_chapters = len(chapters)
        total_scenes = len(scenes)
        scenes_per_chapter = max(1, total_scenes // num_chapters)

        timestamps = []
        current_time = 0.0

        for i, ch in enumerate(chapters):
            # 시간을 MM:SS 형식으로
            minutes = int(current_time // 60)
            seconds = int(current_time % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"

            ch_title = ch.get("chapter_title", f"챕터 {i+1}")
            timestamps.append(f"{timestamp} {ch_title}")

            # 이 챕터에 속하는 씬들의 duration 합산
            start_idx = i * scenes_per_chapter
            end_idx = min(start_idx + scenes_per_chapter, total_scenes)
            if i == num_chapters - 1:
                end_idx = total_scenes  # 마지막 챕터는 나머지 전부

            for j in range(start_idx, end_idx):
                if j < len(scenes):
                    current_time += scenes[j].get("duration", 5.0)

        return "\n".join(timestamps)

    @api_retry
    def _generate(self, topic: str, summary: str,
                  title_hint: str, chapters_text: str) -> dict:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        chapters_instruction = ""
        if chapters_text:
            chapters_instruction = f"""
아래 챕터 타임스탬프를 description에 반드시 포함하세요:

{chapters_text}
"""

        message = client.messages.create(
            model=config["script"]["model"],
            max_tokens=1024,
            messages=[{"role": "user", "content": f"""YouTube SEO 전문가로서 메타데이터를 생성해줘.

주제: {topic}
내용 요약: {summary}
참고 제목: {title_hint}
{chapters_instruction}
반드시 아래 JSON으로만 응답:
{{
  "title": "SEO 최적화 제목 (100자 이내, 핵심 키워드 앞쪽 배치, 감정적 표현 포함)",
  "description": "처음 2줄에 핵심 내용 요약. 그 다음 빈 줄. 그 다음 챕터별 타임스탬프. 마지막에 해시태그 3~5개. 총 5000자 이내.",
  "tags": ["메인키워드", "관련키워드1", "관련키워드2", "영어키워드1"],
  "category_id": "22"
}}

규칙:
- 제목에 숫자, 질문형, 감성 단어 활용
- 태그는 10~20개, 한국어+영어 병행
- description 구조: 요약 → 빈줄 → 타임스탬프 → 빈줄 → 해시태그
- 첫 번째 타임스탬프는 반드시 00:00 으로 시작 (YouTube 챕터 필수 조건)
- description에 #해시태그 포함
"""}]
        )

        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find("{")
        end = text.rfind("}") + 1
        return json.loads(text[start:end])
