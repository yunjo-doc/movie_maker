"""OpenAI TTS Provider — 자연스러운 한국어 음성 생성 + SRT 자막"""

import io
import re
import logging
import requests
from pydub import AudioSegment
from utils.retry import api_retry
from utils.srt_converter import save_srt
from utils.korean_number import convert_numbers_for_tts
import srt as srt_lib
from datetime import timedelta

logger = logging.getLogger(__name__)


class OpenAITTSProvider:
    def __init__(self, api_key: str, cfg: dict):
        self.api_key = api_key
        self.model = cfg.get("model", "tts-1-hd")
        self.voice = cfg.get("voice", "onyx")
        self.speed = cfg.get("speed", 1.15)

    @api_retry
    def _call_api(self, text: str) -> bytes:
        response = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "voice": self.voice,
                "input": text,
                "speed": self.speed,
                "response_format": "mp3",
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.content

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

            logger.info(f"  OpenAI TTS 챕터 {i+1}/{len(chapters)} ({len(text)}자)")

            if i > 0:
                all_audio += AudioSegment.silent(duration=CHAPTER_GAP_MS)
                cumulative_sec += CHAPTER_GAP_MS / 1000.0

            tts_text = convert_numbers_for_tts(text)

            # OpenAI TTS 4096자 제한 → 문장 단위 분할
            chunks = self._split_text(tts_text, max_chars=4000)

            for chunk in chunks:
                audio_bytes = self._call_api(chunk)
                seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                all_audio += seg

                chunk_duration_sec = len(seg) / 1000.0

                # 문장 기반 비례 타이밍 SRT
                subs = self._text_to_subs(
                    text=chunk,
                    offset=cumulative_sec,
                    duration=chunk_duration_sec,
                    start_idx=sub_index,
                )
                all_subs.extend(subs)
                sub_index += len(subs)

                cumulative_sec += chunk_duration_sec

        all_audio.export(final_audio_path, format="mp3")
        save_srt(all_subs, final_srt_path)
        logger.info(f"  OpenAI TTS 완료: {cumulative_sec:.1f}초, {len(all_subs)}개 자막")

    def _split_text(self, text: str, max_chars: int = 4000) -> list:
        """문장 단위로 분할하여 max_chars 이하 청크 생성"""
        if len(text) <= max_chars:
            return [text]

        sentences = re.split(r'(?<=[.!?。])\s+', text)
        chunks = []
        current = ""

        for sent in sentences:
            if len(current) + len(sent) + 1 > max_chars and current:
                chunks.append(current.strip())
                current = sent
            else:
                current = current + " " + sent if current else sent

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _text_to_subs(self, text: str, offset: float, duration: float,
                       start_idx: int, max_chars: int = 25) -> list:
        """텍스트를 문장/어절 단위로 분할 후 비례 타이밍으로 SRT 생성"""
        # 문장 분리 (소수점 뒤 숫자는 분리하지 않음)
        sentences = re.split(r'(?<=[.!?。])(?!\d)\s*', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 긴 문장 → 어절 단위 분할
        lines = []
        for sent in sentences:
            if len(sent) <= max_chars:
                lines.append(sent)
            else:
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

        if not lines:
            return []

        # 글자 수 비례 타이밍 배분
        total_chars = sum(len(line) for line in lines)
        subs = []
        current_time = offset

        for i, line in enumerate(lines):
            line_duration = duration * (len(line) / total_chars) if total_chars > 0 else 0
            subs.append(srt_lib.Subtitle(
                index=start_idx + i,
                start=timedelta(seconds=current_time),
                end=timedelta(seconds=current_time + line_duration),
                content=line,
            ))
            current_time += line_duration

        return subs
