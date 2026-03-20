"""SRT/VTT 변환 유틸리티"""

import srt as srt_lib
from datetime import timedelta


def vtt_to_srt_subs(vtt_content: str) -> list:
    """VTT 텍스트를 srt.Subtitle 리스트로 변환"""
    content = vtt_content
    # WEBVTT 헤더 제거
    if content.startswith("WEBVTT"):
        content = content.split("\n\n", 1)[-1] if "\n\n" in content else ""

    subs = []
    blocks = [b.strip() for b in content.strip().split("\n\n") if b.strip()]

    for i, block in enumerate(blocks, 1):
        lines = block.split("\n")
        time_line = None
        text_lines = []

        for line in lines:
            if "-->" in line:
                time_line = line
            elif time_line is not None:
                text_lines.append(line)

        if not time_line or not text_lines:
            continue

        parts = time_line.split(" --> ")
        if len(parts) != 2:
            continue

        start = _parse_vtt_time(parts[0].strip())
        end = _parse_vtt_time(parts[1].strip())
        text = "\n".join(text_lines)

        subs.append(srt_lib.Subtitle(index=i, start=start, end=end, content=text))

    return subs


def _parse_vtt_time(ts: str) -> timedelta:
    """VTT 타임스탬프 파싱 (HH:MM:SS.mmm 또는 MM:SS.mmm)"""
    parts = ts.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, rest = parts
    elif len(parts) == 2:
        h = "0"
        m, rest = parts
    else:
        return timedelta()

    s_parts = rest.split(".")
    s = s_parts[0]
    ms = s_parts[1] if len(s_parts) > 1 else "0"
    ms = ms.ljust(3, "0")[:3]

    return timedelta(
        hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms)
    )


def save_srt(subs: list, path: str):
    """SRT 파일 저장 (utf-8-sig BOM 포함)"""
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(srt_lib.compose(subs))


def format_srt_time(seconds: float) -> str:
    """초를 SRT 타임스탬프 형식으로 변환"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
