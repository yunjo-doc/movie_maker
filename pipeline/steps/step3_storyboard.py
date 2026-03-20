"""Step 3: 스토리보드 + 이미지 프롬프트 생성 (Claude API)"""

import json
import logging
import anthropic
from pipeline.base import Step
from pipeline.context import PipelineContext
from utils.retry import api_retry
from config import settings, config

logger = logging.getLogger(__name__)


class GenerateStoryboardStep(Step):
    name = "generate_storyboard"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        from mutagen.mp3 import MP3
        audio = MP3(ctx.audio_path)
        total_duration = audio.info.length
        chapters = ctx.script.get("chapters", [])
        num_chapters = len(chapters)

        logger.info(f"총 오디오 길이: {total_duration:.1f}초, {num_chapters}개 챕터")

        # 챕터별로 개별 씬 생성 → 내용-이미지 매칭 보장
        all_scenes = []
        scene_id = 1
        chapter_duration = total_duration / num_chapters if num_chapters else total_duration

        for i, ch in enumerate(chapters):
            logger.info(f"  스토리보드 챕터 {i+1}/{num_chapters}...")
            ch_scenes = self._generate_for_chapter(
                ch, chapter_duration, scene_id, brief=ctx.brief
            )
            # LLM이 scene_id를 무시할 수 있으므로 강제 재번호 부여
            for j, sc in enumerate(ch_scenes):
                sc["scene_id"] = scene_id + j
            all_scenes.extend(ch_scenes)
            scene_id += len(ch_scenes)

        # I2V 대상 씬 선정 (config 비율에 따라)
        i2v_ratio = config.get("i2v", {}).get("i2v_ratio", 0.2)
        all_scenes = self._mark_i2v_scenes(all_scenes, i2v_ratio)

        # duration 합계 조정 (오디오 길이에 맞춤)
        all_scenes = self._adjust_durations(all_scenes, total_duration)

        with open(f"{ctx.output_dir}/storyboard.json", "w", encoding="utf-8") as f:
            json.dump(all_scenes, f, ensure_ascii=False, indent=2)

        logger.info(f"스토리보드 생성: {len(all_scenes)}개 씬")
        ctx.scenes = all_scenes
        return ctx

    def _adjust_durations(self, scenes: list, total_duration: float) -> list:
        """씬들의 duration 합계를 오디오 길이에 맞게 조정"""
        current_total = sum(s.get("duration", 5) for s in scenes)
        if current_total <= 0:
            return scenes

        ratio = total_duration / current_total
        for scene in scenes:
            scene["duration"] = round(scene.get("duration", 5) * ratio, 1)

        return scenes

    def _mark_i2v_scenes(self, scenes: list, ratio: float) -> list:
        """전체 씬 중 ratio 비율만큼 I2V 대상으로 선정

        시각적 임팩트가 큰 씬(움직임 효과가 있는 씬)을 균등 간격으로 선택.
        """
        total = len(scenes)
        i2v_count = max(1, round(total * ratio))

        # 균등 간격으로 선택 (첫 씬은 제외, 하이라이트 위주)
        if i2v_count >= total:
            indices = list(range(total))
        else:
            step = total / i2v_count
            indices = [int(step * i + step / 2) for i in range(i2v_count)]
            indices = [idx for idx in indices if idx < total]

        for i, scene in enumerate(scenes):
            if i in indices:
                scene["use_i2v"] = True
                scene["motion_prompt"] = self._derive_motion_prompt(scene)
            else:
                scene["use_i2v"] = False

        logger.info(f"I2V 대상: {len(indices)}/{total}개 씬")
        return scenes

    @staticmethod
    def _derive_motion_prompt(scene: dict) -> str:
        """이미지 프롬프트에서 움직임 프롬프트 생성"""
        prompt = scene.get("prompt_en", "")
        effect = scene.get("effect", "zoom_in")

        motion_map = {
            "zoom_in": "slow cinematic zoom in, subtle ambient motion",
            "zoom_out": "slow cinematic zoom out, gentle atmosphere movement",
            "pan_left": "smooth left pan, gentle scene movement",
            "pan_right": "smooth right pan, gentle scene movement",
            "static": "subtle ambient motion, gentle breathing effect",
        }
        base_motion = motion_map.get(effect, motion_map["zoom_in"])
        return f"{base_motion}, {prompt[:200]}"

    @api_retry
    def _generate_for_chapter(self, chapter: dict, chapter_duration: float,
                               start_scene_id: int, brief: dict = None) -> list:
        """단일 챕터에 대한 씬 생성 — 내용-이미지 매칭 보장"""
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        img_cfg = config.get("images", {})

        # brief에 visual_style이 있으면 우선 사용
        if brief and brief.get("visual_style"):
            vs = brief["visual_style"]
            style_desc = vs.get("name", "")
            style_suffix = vs.get("style_suffix", "")
        else:
            style_desc = img_cfg.get("style_description", "")
            style_suffix = img_cfg.get("style_suffix", "")

        character_sheet = img_cfg.get("character_sheet", "")

        style_block = ""
        if style_desc:
            style_block += f"\n그림 스타일: {style_desc}"
        if style_suffix:
            style_block += f"\n모든 프롬프트에 이 스타일을 반영: {style_suffix}"
        if character_sheet:
            style_block += f"\n고정 캐릭터: {character_sheet}"

        ch_title = chapter.get("chapter_title", "")
        ch_script = chapter.get("script", "")

        message = client.messages.create(
            model=config["script"]["model"],
            max_tokens=2048,
            messages=[{"role": "user", "content": f"""이 챕터의 내용에 맞는 씬별 이미지 프롬프트를 생성해.

챕터 제목: {ch_title}
챕터 내용:
{ch_script[:1500]}

이 챕터의 영상 길이: 약 {chapter_duration:.0f}초
{style_block}

반드시 JSON 배열로만 응답:
[
  {{
    "scene_id": {start_scene_id},
    "prompt_en": "이 챕터 내용에 정확히 맞는 영어 이미지 프롬프트",
    "duration": 5.0,
    "effect": "zoom_in",
    "search_keyword": "영어 키워드 1~2단어"
  }}
]

규칙:
- 씬 3~5개 (이 챕터 분량에 맞게)
- 이 챕터에서 설명하는 장면만 생성 (다른 챕터 내용 포함 금지)
- 대본에서 묘사하는 상황/장소/인물을 정확히 반영
- duration 합계 ≈ {chapter_duration:.0f}초
- effect: zoom_in, zoom_out, pan_left, pan_right, static 다양하게
- CRITICAL: prompt_en에 텍스트/글자/라벨/캡션/숫자 표기를 절대 포함하지 마. 이미지는 순수 시각 요소만 포함해야 함. 예: "newspaper headline showing..." 대신 "person reading newspaper with worried expression" 사용
"""}]
        )

        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])

    @api_retry
    def _generate(self, summary: str, total_duration: float) -> list:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # config에서 스타일 정보 로드
        img_cfg = config.get("images", {})
        style_preset = img_cfg.get("style_preset", "")
        style_desc = img_cfg.get("style_description", "")
        character_sheet = img_cfg.get("character_sheet", "")

        # 스타일 지시 블록
        style_block = ""
        if style_desc:
            style_block += f"\n그림 스타일: {style_desc}"
            style_block += f"\n모든 prompt_en에 이 스타일을 반드시 반영해. 모든 씬이 동일한 톤과 분위기를 유지해야 한다."
        if character_sheet:
            style_block += f"\n\n고정 캐릭터 묘사 (인물 등장 시 매번 이 묘사를 그대로 포함):\n{character_sheet}"

        message = client.messages.create(
            model=config["script"]["model"],
            max_tokens=4096,
            messages=[{"role": "user", "content": f"""다음 대본을 분석하여 씬별 이미지 프롬프트를 생성해.

대본 요약:
{summary}

총 영상 길이: 약 {total_duration:.0f}초
{style_block}

반드시 아래 JSON 배열로만 응답해. 다른 텍스트 없이:
[
  {{
    "scene_id": 1,
    "prompt_en": "구체적 영어 이미지 프롬프트 (지정된 스타일, 조명, 분위기, 구도 포함)",
    "duration": 5.0,
    "effect": "zoom_in",
    "search_keyword": "영어 키워드 1~2단어 (Pexels 검색용)"
  }}
]

규칙:
- 씬 수: 10~20개 (영상 길이에 비례)
- effect: zoom_in, zoom_out, pan_left, pan_right, static 중 선택 (다양하게 섞기)
- 각 씬은 3~10초
- duration 합계가 약 {total_duration:.0f}초가 되도록
- prompt_en은 영어로 구체적으로. 위에 지정된 그림 스타일을 모든 프롬프트에 일관되게 적용
- search_keyword는 Pexels에서 검색 가능한 간결한 영어 단어
- 인물이 등장하면 매번 동일한 외모 묘사 포함
- 모든 씬이 하나의 영상처럼 통일된 비주얼을 가져야 함
"""}]
        )

        text = message.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        start = text.find("[")
        end = text.rfind("]") + 1
        return json.loads(text[start:end])
