"""Step 0: 인터랙티브 영상 기획 -100만 구독자 유튜버처럼 생각하기

흐름:
  1. 비주얼 스타일 선택 -영상의 그림체 확정
  2. 주제 리서치 -웹 검색으로 트렌드·인기 콘텐츠 분석
  3. 기획안 제안 -3가지 앵글 제시
  4. 사용자와 대화 -피드백 반영하며 기획 구체화
  5. 최종 기획서(brief) 저장
"""

import json
import logging
import anthropic
from pathlib import Path
from config import settings, config
from utils.retry import api_retry

logger = logging.getLogger(__name__)

# 비주얼 스타일 프리셋
STYLE_PRESETS = {
    "1": {
        "name": "시네마틱 다큐",
        "description": "영화 같은 조명, 사실적 분위기, 다큐멘터리 느낌",
        "style_suffix": ", cinematic documentary style, warm color grading, dramatic lighting, shallow depth of field, photorealistic, high detail",
        "best_for": "과학, 역사, 시사, 자기계발",
    },
    "2": {
        "name": "디지털 일러스트",
        "description": "깔끔한 디지털 그림, 따뜻한 색감, 정보 유튜브 인기 스타일",
        "style_suffix": ", clean digital illustration, warm color palette, soft lighting, modern infographic style, flat design elements",
        "best_for": "IT, 경제, 교육, 정보 전달",
    },
    "3": {
        "name": "지브리 애니",
        "description": "스튜디오 지브리풍 수채화 애니메이션, 파스텔톤",
        "style_suffix": ", studio ghibli anime style, pastel colors, watercolor texture, soft dreamy atmosphere, hand-drawn feeling",
        "best_for": "감성, 힐링, 에세이, 동화",
    },
    "4": {
        "name": "웹툰",
        "description": "한국 웹툰 스타일, 깔끔한 선화, 밝은 색감",
        "style_suffix": ", korean webtoon style, clean line art, vibrant colors, manhwa illustration, expressive characters",
        "best_for": "스토리텔링, 유머, MZ세대 타겟",
    },
    "5": {
        "name": "졸라맨/심플",
        "description": "미니멀 스틱맨, 단순한 도형, 화이트보드 애니메이션 느낌",
        "style_suffix": ", minimalist stick figure art, simple shapes, whiteboard animation style, clean white background, bold outlines",
        "best_for": "설명, 요약, 가벼운 정보 전달",
    },
    "6": {
        "name": "3D 렌더링",
        "description": "입체감 있는 3D 캐릭터와 배경, 모던한 느낌",
        "style_suffix": ", 3D rendered illustration, soft ambient lighting, modern clean aesthetic, isometric perspective, blender style",
        "best_for": "테크, 미래, 제품 소개",
    },
    "7": {
        "name": "포토리얼",
        "description": "실사 사진처럼 사실적, 8K 고화질",
        "style_suffix": ", photorealistic, 8K ultra high detail, professional photography, natural lighting, sharp focus",
        "best_for": "뉴스, 사건사고, 리뷰",
    },
    "8": {
        "name": "수채화",
        "description": "부드러운 수채화 질감, 몽환적 분위기",
        "style_suffix": ", watercolor painting style, soft brush strokes, dreamy atmosphere, gentle color bleeding, artistic texture",
        "best_for": "여행, 감성, 명상, 자연",
    },
}

SYSTEM_PROMPT = """당신은 구독자 100만 명의 한국 유튜브 채널을 운영하는 수석 PD이자 크리에이티브 디렉터입니다.

당신의 역할:
- 트렌디하면서도 깊이 있는 영상 주제를 기획합니다
- 시청자의 클릭을 유도하는 강력한 앵글을 찾습니다
- 조회수뿐 아니라 시청 지속률까지 고려한 구성을 설계합니다
- 사용자의 아이디어를 존중하되, 더 나은 방향이 있으면 제안합니다

기획 시 고려사항:
1. 후킹(Hook): 처음 30초에 시청자를 사로잡을 포인트
2. 차별화: 이미 있는 영상들과 어떻게 다를 것인지
3. 감정선: 시청자가 느낄 감정의 흐름 (호기심->놀라움->감동 등)
4. 공유성: 시청 후 공유하고 싶게 만드는 요소
5. SEO: 검색에 잡히는 키워드와 제목 구조

답변은 항상 한국어로, 실무적이고 구체적으로 합니다."""


class InteractivePlanner:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = config["script"]["model"]
        self.messages = []
        self.selected_style = None

    @staticmethod
    def show_style_menu() -> str:
        """비주얼 스타일 선택 메뉴 출력"""
        lines = [
            "",
            "  비주얼 스타일을 선택하세요:",
            "  " + "─" * 50,
        ]
        for key, preset in STYLE_PRESETS.items():
            lines.append(
                f"  [{key}] {preset['name']}"
                f"  -{preset['description']}"
            )
            lines.append(
                f"      추천: {preset['best_for']}"
            )
        lines.append("  " + "─" * 50)
        lines.append("  번호를 입력하세요 (1~8):")
        return "\n".join(lines)

    def select_style(self, choice: str) -> dict:
        """사용자 선택에 따라 스타일 프리셋 반환"""
        preset = STYLE_PRESETS.get(choice.strip())
        if not preset:
            return None
        self.selected_style = preset
        return preset

    def recommend_style(self, topic: str) -> str:
        """주제에 맞는 스타일을 AI가 추천"""
        styles_desc = "\n".join(
            f"[{k}] {v['name']}: {v['description']} (추천: {v['best_for']})"
            for k, v in STYLE_PRESETS.items()
        )
        prompt = f"""이 주제에 가장 어울리는 비주얼 스타일을 추천해주세요.

주제: "{topic}"

사용 가능한 스타일:
{styles_desc}

가장 적합한 스타일 번호와 이유를 간단히 설명해주세요.
2026년 유튜브 정보 채널 트렌드를 고려해서 추천해주세요."""

        return self._chat(prompt)

    def research_topic(self, topic: str) -> str:
        """주제에 대한 트렌드 리서치 + 경쟁 분석"""
        prompt = f"""새 영상을 기획합니다. 주제: "{topic}"

다음을 분석해주세요:

1. **트렌드 분석**: 이 주제가 지금 왜 핫한지, 최근 이슈나 트리거가 있는지
2. **경쟁 분석**: 유튜브에서 이 주제로 이미 잘된 영상들은 어떤 앵글을 썼는지 (예상)
3. **기회 포인트**: 아직 다뤄지지 않았거나, 새로운 관점으로 접근할 수 있는 빈틈
4. **타겟 시청자**: 이 영상을 볼 핵심 시청자층과 그들의 관심사

그 다음, 이 분석을 바탕으로 **3가지 기획안**을 제안하세요:

각 기획안에 포함할 것:
- **앵글**: 한 문장으로 영상의 핵심 관점
- **제목 후보**: 클릭을 유도하는 제목 2개
- **후킹 전략**: 처음 30초를 어떻게 시작할지
- **챕터 구성**: 대략적인 흐름 (5개 챕터)
- **차별화 포인트**: 기존 영상들과 다른 점
- **예상 반응**: 댓글에 어떤 반응이 올지"""

        return self._chat(prompt)

    def refine(self, user_feedback: str) -> str:
        """사용자 피드백을 반영하여 기획 수정"""
        return self._chat(user_feedback)

    def finalize_brief(self) -> str:
        """최종 기획서를 구조화된 JSON으로 정리"""
        style_block = ""
        if self.selected_style:
            style_block = f"""
"visual_style": {{
    "name": "{self.selected_style['name']}",
    "style_suffix": "{self.selected_style['style_suffix']}"
  }},"""

        prompt = f"""지금까지의 논의를 바탕으로 최종 기획서를 작성해주세요.

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "title": "최종 확정 제목",
  "angle": "핵심 앵글 한 문장",
  "hook": "처음 30초 후킹 전략 상세",
  "target_audience": "핵심 타겟 시청자",
  "emotion_flow": "감정선 흐름 설명",{style_block}
  "chapters": [
    {{
      "chapter_number": 1,
      "chapter_title": "챕터 제목",
      "key_points": ["핵심 포인트 1", "핵심 포인트 2"],
      "tone": "이 챕터의 톤/분위기"
    }}
  ],
  "differentiation": "기존 영상 대비 차별점",
  "seo_keywords": ["키워드1", "키워드2", "키워드3"],
  "style_notes": "영상 스타일/분위기 지시사항"
}}"""
        return self._chat(prompt)

    def _chat(self, user_message: str) -> str:
        """대화 컨텍스트를 유지하며 메시지 전송"""
        self.messages.append({"role": "user", "content": user_message})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        )

        assistant_text = response.content[0].text
        self.messages.append({"role": "assistant", "content": assistant_text})
        return assistant_text

    def save_brief(self, brief_json: str, output_dir: str) -> str:
        """기획서를 JSON 파일로 저장"""
        path = Path(output_dir) / "brief.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # JSON 추출
        text = brief_json
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find("{")
        end = text.rfind("}") + 1
        brief = json.loads(text[start:end])

        path.write_text(
            json.dumps(brief, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"기획서 저장: {path}")
        return str(path)

    def save_conversation(self, output_dir: str):
        """기획 대화 전체를 기록으로 저장"""
        path = Path(output_dir) / "planning_log.json"
        path.write_text(
            json.dumps(self.messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
