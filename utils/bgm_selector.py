"""BGM 자동 선택 — 대본 내용 분석 → 가장 어울리는 곡 매칭

bgm/ 폴더에 있는 곡들의 파일명을 분석하여
대본의 분위기와 가장 잘 맞는 BGM을 선택한다.
"""

import logging
from pathlib import Path
import anthropic
from config import settings, config
from utils.retry import api_retry

logger = logging.getLogger(__name__)

BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def list_bgm_files(bgm_dir: str = "bgm") -> list[dict]:
    """BGM 폴더의 곡 목록을 반환"""
    bgm_path = Path(bgm_dir)
    if not bgm_path.exists():
        return []

    files = []
    for f in sorted(bgm_path.iterdir()):
        if f.suffix.lower() in BGM_EXTENSIONS:
            files.append({
                "path": str(f),
                "name": f.stem,  # 확장자 제외 파일명
            })
    return files


@api_retry
def select_bgm(script_summary: str, title: str,
               bgm_dir: str = "bgm") -> str | None:
    """대본 내용을 분석하여 가장 어울리는 BGM 선택

    Args:
        script_summary: 대본 요약 또는 전체 분위기
        title: 영상 제목
        bgm_dir: BGM 폴더 경로

    Returns:
        선택된 BGM 파일 경로, 없으면 None
    """
    files = list_bgm_files(bgm_dir)
    if not files:
        logger.info("BGM 폴더에 곡이 없습니다")
        return None

    if len(files) == 1:
        logger.info(f"BGM 1곡만 있어 자동 선택: {files[0]['name']}")
        return files[0]["path"]

    # 파일명 목록 생성
    file_list = "\n".join(
        f"[{i+1}] {f['name']}" for i, f in enumerate(files)
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=config["script"]["model"],
        max_tokens=64,
        messages=[{"role": "user", "content": f"""이 영상에 가장 어울리는 배경 음악을 골라줘.

영상 제목: {title}
영상 분위기: {script_summary[:500]}

사용 가능한 BGM:
{file_list}

규칙:
- 영상의 감정, 톤, 주제에 가장 잘 맞는 곡을 선택
- 반드시 번호만 응답 (예: 3)
- 다른 텍스트 없이 숫자만"""}]
    )

    try:
        text = message.content[0].text.strip()
        # 숫자만 추출
        num = int("".join(c for c in text if c.isdigit()))
        idx = num - 1
        if 0 <= idx < len(files):
            selected = files[idx]
            logger.info(f"BGM 선택: [{num}] {selected['name']}")
            return selected["path"]
    except (ValueError, IndexError):
        pass

    # 파싱 실패 시 첫 번째 곡
    logger.warning(f"BGM 선택 파싱 실패, 첫 번째 곡 사용: {files[0]['name']}")
    return files[0]["path"]
