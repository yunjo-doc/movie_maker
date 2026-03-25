"""Step 1: Claude API 대본 생성"""

import json
import re
import logging
import anthropic
from pipeline.base import Step
from pipeline.context import PipelineContext
from utils.retry import api_retry
from config import settings, config

logger = logging.getLogger(__name__)


class GenerateScriptStep(Step):
    name = "generate_script"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info(f"주제: {ctx.topic}")
        if ctx.brief:
            logger.info("기획서 기반 대본 생성")
            script = self._generate_from_brief(ctx.topic, ctx.brief)
        else:
            script = self._generate(ctx.topic)

        script_path = f"{ctx.output_dir}/script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        logger.info(f"대본 생성 완료: {len(script.get('chapters', []))}개 챕터")
        ctx.script = script
        return ctx

    @api_retry
    def _generate(self, topic: str) -> dict:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        cfg = config["script"]
        num_chapters = cfg["chapters"]
        chars = cfg["chars_per_chapter"]

        # 챕터별로 개별 요청하여 JSON 파싱 안정성 확보
        title_msg = client.messages.create(
            model=cfg["model"],
            max_tokens=256,
            messages=[{"role": "user", "content": f"""유튜브 영상 제목과 요약을 만들어줘.
주제: {topic}
JSON으로만 응답: {{"title": "제목", "summary": "100자 요약"}}"""}]
        )
        title_text = title_msg.content[0].text
        title_json = self._parse_json(title_text)
        title = title_json.get("title", topic)
        summary = title_json.get("summary", "")

        chapters = []
        for i in range(1, num_chapters + 1):
            logger.info(f"  챕터 {i}/{num_chapters} 생성 중...")
            ch_msg = client.messages.create(
                model=cfg["model"],
                max_tokens=4096,
                messages=[{"role": "user", "content": f"""유튜브 영상 대본의 챕터 {i}/{num_chapters}을 작성해줘.

영상 제목: {title}
주제: {topic}
이 챕터 위치: {i}번째 (총 {num_chapters}개 중)
분량: 약 {chars}자 (엄격히 준수, 초과 금지)
전체 영상 목표: 약 {cfg.get('target_duration_minutes', 18)}분
스타일: {cfg['style']}

{'도입부: 시청자를 끌어당기는 강렬한 시작' if i == 1 else ''}
{'마무리: 감동적인 결론과 시청 감사 인사' if i == num_chapters else ''}

챕터 제목과 나레이션 대본만 작성해.
JSON 형식: {{"chapter_title": "제목", "script": "대본 텍스트"}}

중요: script 값 안에 큰따옴표(")를 사용하지 말고 작은따옴표(')만 사용해."""}]
            )
            ch_text = ch_msg.content[0].text
            ch_json = self._parse_json(ch_text)
            chapters.append({
                "chapter_number": i,
                "chapter_title": ch_json.get("chapter_title", f"챕터 {i}"),
                "script": ch_json.get("script", ""),
            })

        return {
            "title": title,
            "summary": summary,
            "chapters": chapters,
        }

    @api_retry
    def _generate_from_brief(self, topic: str, brief: dict) -> dict:
        """기획서를 기반으로 대본 생성 — 100만 구독자 수준"""
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        cfg = config["script"]

        title = brief.get("title", topic)
        angle = brief.get("angle", "")
        hook = brief.get("hook", "")
        emotion_flow = brief.get("emotion_flow", "")
        style_notes = brief.get("style_notes", "")
        chapters_plan = brief.get("chapters", [])
        num_chapters = len(chapters_plan) if chapters_plan else cfg["chapters"]
        chars = cfg["chars_per_chapter"]

        chapters = []
        for i, ch_plan in enumerate(chapters_plan, 1):
            ch_title = ch_plan.get("chapter_title", f"챕터 {i}")
            key_points = ch_plan.get("key_points", [])
            tone = ch_plan.get("tone", "")
            points_text = "\n".join(f"- {p}" for p in key_points)

            logger.info(f"  챕터 {i}/{num_chapters} 생성 중... ({ch_title})")
            ch_msg = client.messages.create(
                model=cfg["model"],
                max_tokens=4096,
                messages=[{"role": "user", "content": f"""당신은 구독자 100만 명의 유튜브 채널 전속 작가입니다.
아래 기획서에 따라 챕터 {i}의 나레이션 대본을 작성하세요.

영상 제목: {title}
핵심 앵글: {angle}
감정선: {emotion_flow}
영상 스타일: {style_notes}

이 챕터 정보:
- 제목: {ch_title}
- 핵심 포인트:
{points_text}
- 톤/분위기: {tone}
- 위치: {i}번째 (총 {num_chapters}개 중)

{'후킹 전략: ' + hook if i == 1 else ''}
{'마무리: 감동적 결론 + 구독/좋아요 유도 + 댓글 참여 유도' if i == num_chapters else ''}

작성 규칙:
- 분량: 약 {chars}자 (엄격히 준수, 초과 금지)
- 전체 영상 목표 길이: 약 {cfg.get('target_duration_minutes', 18)}분
- 스타일: {cfg['style']}
- 시청자에게 말하듯 자연스러운 구어체
- 구체적 사례, 숫자, 에피소드를 넣어 몰입감 강화
- 한 문단이 너무 길지 않게, 호흡 조절
- 핵심 포인트를 빠짐없이 포함

JSON 형식: {{"chapter_title": "제목", "script": "대본 텍스트"}}
중요: script 값 안에 큰따옴표(")를 사용하지 말고 작은따옴표(')만 사용해."""}]
            )
            ch_text = ch_msg.content[0].text
            ch_json = self._parse_json(ch_text)
            chapters.append({
                "chapter_number": i,
                "chapter_title": ch_json.get("chapter_title", ch_title),
                "script": ch_json.get("script", ""),
            })

        summary_msg = client.messages.create(
            model=cfg["model"],
            max_tokens=256,
            messages=[{"role": "user", "content": f"이 영상의 100자 요약을 작성해. 제목: {title}, 앵글: {angle}\nJSON: {{\"summary\": \"요약\"}}"}]
        )
        summary = self._parse_json(summary_msg.content[0].text).get("summary", "")

        return {
            "title": title,
            "summary": summary,
            "chapters": chapters,
        }

    def _parse_json(self, text: str) -> dict:
        """다양한 형식의 LLM 출력에서 JSON 추출"""
        # 코드블록 제거
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"JSON을 찾을 수 없습니다: {text[:200]}")

        json_str = text[start:end]

        # 1차 시도: 그대로 파싱
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 2차 시도: 제어 문자 제거 후 파싱
        cleaned = json_str.replace("\n", "\\n").replace("\r", "").replace("\t", "\\t")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 3차 시도: 정규식으로 key-value 추출
        result = {}
        for match in re.finditer(r'"(\w+)"\s*:\s*"((?:[^"\\]|\\.)*)?"', json_str, re.DOTALL):
            key = match.group(1)
            val = match.group(2) or ""
            val = val.replace("\\n", "\n").replace('\\"', '"')
            result[key] = val

        if result:
            return result

        raise ValueError(f"JSON 파싱 실패: {json_str[:300]}")
