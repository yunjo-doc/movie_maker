"""ElevenLabs TTS Provider — 유료 폴백"""

import io
import base64
import logging
import requests
from pydub import AudioSegment
from utils.retry import api_retry
from utils.srt_converter import format_srt_time, save_srt
from utils.korean_number import convert_numbers_for_tts
import srt as srt_lib
from datetime import timedelta

logger = logging.getLogger(__name__)


class ElevenLabsProvider:
    def __init__(self, api_key: str, cfg: dict):
        self.api_key = api_key
        self.voice_id = cfg.get("voice_id", "")
        self.model_id = cfg.get("model_id", "eleven_multilingual_v2")
        self.stability = cfg.get("stability", 0.5)
        self.similarity_boost = cfg.get("similarity_boost", 0.75)

    @api_retry
    def _call_api(self, text: str) -> dict:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/with-timestamps"
        response = requests.post(url, json={
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
            }
        }, headers={"xi-api-key": self.api_key}, timeout=120)
        response.raise_for_status()
        return response.json()

    def generate_chapters(self, chapters: list,
                           final_audio_path: str, final_srt_path: str):
        LEAD_IN_MS = 500
        CHAPTER_GAP_MS = 300

        all_audio = AudioSegment.silent(duration=LEAD_IN_MS)
        all_subs = []
        cumulative_sec = LEAD_IN_MS / 1000.0
        sub_index = 1

        for i, ch in enumerate(chapters):
            text = ch.get("script", "")
            if not text.strip():
                continue

            logger.info(f"  ElevenLabs 챕터 {i+1}/{len(chapters)} ({len(text)}자)")

            if i > 0:
                all_audio += AudioSegment.silent(duration=CHAPTER_GAP_MS)
                cumulative_sec += CHAPTER_GAP_MS / 1000.0

            # 한국어 숫자 전처리 (14,000명 → 1만 4천명)
            text = convert_numbers_for_tts(text)

            # 5000자 제한 분할
            chunks = [text[j:j + 4500] for j in range(0, len(text), 4500)]

            for chunk in chunks:
                result = self._call_api(chunk)
                audio_bytes = base64.b64decode(result["audio_base64"])
                seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                all_audio += seg

                # alignment → SRT (원본 텍스트 전달로 어절 분리 정확도 향상)
                alignment = result.get("alignment", {})
                if alignment:
                    subs = self._alignment_to_subs(
                        alignment, cumulative_sec, sub_index,
                        original_text=chunk
                    )
                    all_subs.extend(subs)
                    sub_index += len(subs)

                cumulative_sec += len(seg) / 1000.0

        all_audio.export(final_audio_path, format="mp3")
        save_srt(all_subs, final_srt_path)
        logger.info(f"  ElevenLabs 완료: {cumulative_sec:.1f}초")

    def _alignment_to_subs(self, alignment, offset, start_idx,
                            max_chars=25, original_text=""):
        """원본 텍스트의 문장/어절 구조를 기준으로 자막 생성 + alignment에서 타이밍 매핑

        핵심: alignment의 글자 순서가 아니라 원본 텍스트의 구두점/어절을 기준으로 분할.
        alignment는 타이밍 정보만 참조.
        """
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        if not chars or not starts:
            return []

        # 원본 텍스트가 없으면 alignment chars를 합쳐서 사용
        if not original_text:
            original_text = "".join(chars)

        # 1단계: 원본 텍스트를 문장 단위로 분리
        # 소수점(숫자.숫자) 뒤에서는 분리하지 않음
        import re
        sentences = re.split(r'(?<=[.!?。])(?!\d)\s*', original_text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 2단계: 긴 문장은 어절 단위로 추가 분할
        lines = []
        for sent in sentences:
            if len(sent) <= max_chars:
                lines.append(sent)
            else:
                # 어절 단위로 분할 (단어 중간에서 절대 자르지 않음)
                words = sent.split()
                current = []
                current_len = 0
                for w in words:
                    new_len = current_len + len(w) + (1 if current else 0)
                    if new_len > max_chars and current:
                        lines.append(" ".join(current))
                        current = [w]
                        current_len = len(w)
                    else:
                        current.append(w)
                        current_len = new_len
                if current:
                    lines.append(" ".join(current))

        # 3단계: 각 라인에 타이밍 매핑 (alignment 글자 위치 기반)
        subs = []
        idx = start_idx
        char_pos = 0  # alignment 내 현재 위치

        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            # 이 라인의 시작/끝 타이밍 찾기
            line_start_time = None
            line_end_time = None

            # alignment에서 이 라인에 해당하는 글자 범위 찾기
            chars_to_match = len(line_clean.replace(" ", ""))
            matched = 0

            for j in range(char_pos, len(chars)):
                ch = chars[j]
                if ch == " " or ch == "\n":
                    continue
                if line_start_time is None:
                    line_start_time = starts[j] + offset
                line_end_time = ends[j] + offset
                matched += 1
                if matched >= chars_to_match:
                    char_pos = j + 1
                    break

            if line_start_time is None:
                # 타이밍을 찾지 못하면 이전 자막 끝 기준
                if subs:
                    line_start_time = subs[-1].end.total_seconds()
                else:
                    line_start_time = offset
            if line_end_time is None:
                line_end_time = line_start_time + 2.0

            subs.append(srt_lib.Subtitle(
                index=idx,
                start=timedelta(seconds=line_start_time),
                end=timedelta(seconds=line_end_time),
                content=line_clean,
            ))
            idx += 1

        return subs
