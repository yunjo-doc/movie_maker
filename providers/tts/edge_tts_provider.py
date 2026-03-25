"""Edge TTS Provider — 무료 한국어 TTS + SRT 자막 생성 (v7.x 호환)"""

import os
import logging
import edge_tts
from pydub import AudioSegment
from utils.korean_number import convert_numbers_for_tts
from datetime import timedelta
import srt as srt_lib
from utils.srt_converter import save_srt

logger = logging.getLogger(__name__)

# Edge TTS v7.x 타임스탬프 단위: 100나노초 (ticks)
TICKS_PER_SEC = 10_000_000


class EdgeTTSProvider:
    def __init__(self, cfg: dict):
        self.voice = cfg.get("voice", "ko-KR-SunHiNeural")
        self.rate = cfg.get("rate", "+0%")

    async def generate_single(self, text: str, audio_path: str) -> list:
        """단일 텍스트 → MP3 + srt.Subtitle 리스트 반환"""
        text = convert_numbers_for_tts(text)
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate)
        subs = []
        idx = 1

        with open(audio_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    # offset, duration: 100나노초 단위
                    offset_sec = chunk["offset"] / TICKS_PER_SEC
                    duration_sec = chunk["duration"] / TICKS_PER_SEC
                    sentence_text = chunk.get("text", "")

                    if sentence_text.strip():
                        # 긴 문장은 분할 (30자 초과 시)
                        parts = self._split_long_sentence(
                            sentence_text, offset_sec, duration_sec
                        )
                        for start, end, part_text in parts:
                            subs.append(srt_lib.Subtitle(
                                index=idx,
                                start=timedelta(seconds=start),
                                end=timedelta(seconds=end),
                                content=part_text,
                            ))
                            idx += 1

        logger.debug(f"  문장 {len(subs)}개 자막 생성")
        return subs

    def _split_long_sentence(self, text: str, start: float, duration: float,
                              max_chars: int = 30) -> list:
        """긴 문장을 어절(띄어쓰기) 단위로 분할 — 단어 중간에서 절대 자르지 않음"""
        text = text.strip()
        if len(text) <= max_chars:
            return [(start, start + duration, text)]

        # 어절(띄어쓰기) 단위로 분리
        words = text.split()
        if not words:
            return [(start, start + duration, text)]

        # 어절들을 max_chars 이내로 묶기
        segments = []
        current_line = []
        current_len = 0

        for word in words:
            new_len = current_len + len(word) + (1 if current_line else 0)
            if new_len > max_chars and current_line:
                segments.append(" ".join(current_line))
                current_line = [word]
                current_len = len(word)
            else:
                current_line.append(word)
                current_len = new_len

        if current_line:
            segments.append(" ".join(current_line))

        total_chars = sum(len(s) for s in segments)
        current_time = start
        parts = []

        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            seg_duration = duration * (len(seg) / total_chars) if total_chars > 0 else 0
            parts.append((current_time, current_time + seg_duration, seg))
            current_time += seg_duration

        return parts

    async def generate_chapters(self, chapters: list,
                                 final_audio_path: str,
                                 final_srt_path: str):
        """챕터별 TTS 생성 → 오디오 concat + SRT 합산"""
        LEAD_IN_MS = 500
        CHAPTER_GAP_MS = 300

        all_audio = AudioSegment.silent(duration=LEAD_IN_MS)
        all_subs = []
        cumulative_ms = LEAD_IN_MS
        sub_index = 1

        for i, chapter in enumerate(chapters):
            script_text = chapter.get("script", "")
            if not script_text.strip():
                continue

            logger.info(f"  TTS 챕터 {i+1}/{len(chapters)} ({len(script_text)}자)")

            if i > 0:
                all_audio += AudioSegment.silent(duration=CHAPTER_GAP_MS)
                cumulative_ms += CHAPTER_GAP_MS

            tmp_audio = f"{final_audio_path}.ch{i}.mp3"
            chapter_subs = await self.generate_single(script_text, tmp_audio)

            # 오디오 합치기
            seg = AudioSegment.from_mp3(tmp_audio)
            all_audio += seg

            # 시간 오프셋 적용
            offset = timedelta(milliseconds=cumulative_ms)
            for sub in chapter_subs:
                sub.index = sub_index
                sub.start += offset
                sub.end += offset
                all_subs.append(sub)
                sub_index += 1

            cumulative_ms += len(seg)

            # 임시 파일 정리
            try:
                os.remove(tmp_audio)
            except OSError:
                pass

        # 최종 저장
        all_audio.export(final_audio_path, format="mp3")
        save_srt(all_subs, final_srt_path)

        total_sec = cumulative_ms / 1000
        logger.info(f"  TTS 완료: {total_sec:.1f}초, {len(all_subs)}개 자막")
