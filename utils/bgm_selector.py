"""BGM 자동 선택 — 챕터별 분위기 분석 → 곡 매칭

bgm/ 폴더에 있는 곡들의 파일명을 분석하여
각 챕터의 분위기에 맞는 BGM을 선택한다.
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
                "name": f.stem,
            })
    return files


@api_retry
def select_bgm(script_summary: str, title: str,
               bgm_dir: str = "bgm") -> str | None:
    """영상 전체에 어울리는 BGM 1곡 선택 (하위 호환용)"""
    result = select_bgm_per_chapter(
        [{"chapter_title": title, "tone": script_summary}],
        bgm_dir,
    )
    return result[0] if result else None


@api_retry
def select_bgm_per_chapter(chapters: list[dict],
                           bgm_dir: str = "bgm") -> list[str]:
    """챕터별로 분위기에 맞는 BGM을 선택

    Args:
        chapters: [{"chapter_title": str, "tone": str}, ...]
        bgm_dir: BGM 폴더 경로

    Returns:
        챕터별 BGM 파일 경로 리스트
    """
    files = list_bgm_files(bgm_dir)
    if not files:
        logger.info("BGM 폴더에 곡이 없습니다")
        return []

    if len(files) == 1:
        logger.info(f"BGM 1곡만 있어 모든 챕터에 동일 곡: {files[0]['name']}")
        return [files[0]["path"]] * len(chapters)

    file_list = "\n".join(
        f"[{i+1}] {f['name']}" for i, f in enumerate(files)
    )

    chapter_list = "\n".join(
        f"챕터 {i+1}: {ch.get('chapter_title', '')} (톤: {ch.get('tone', '')})"
        for i, ch in enumerate(chapters)
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=config["script"]["model"],
        max_tokens=128,
        messages=[{"role": "user", "content": f"""각 챕터에 가장 어울리는 배경 음악을 골라줘.

챕터 목록:
{chapter_list}

사용 가능한 BGM:
{file_list}

규칙:
- 각 챕터의 감정, 톤에 맞는 곡을 선택
- 연속 챕터에 같은 곡이 올 수 있지만, 가능하면 변화를 줘
- 반드시 챕터 수만큼 번호를 쉼표로 구분해서 응답 (예: 3,1,5,2,6)
- 다른 텍스트 없이 숫자와 쉼표만"""}]
    )

    try:
        text = message.content[0].text.strip()
        nums = [int(n.strip()) for n in text.split(",") if n.strip().isdigit()]

        result = []
        for num in nums[:len(chapters)]:
            idx = num - 1
            if 0 <= idx < len(files):
                result.append(files[idx]["path"])
            else:
                result.append(files[0]["path"])

        # 부족하면 마지막 곡으로 채움
        while len(result) < len(chapters):
            result.append(result[-1] if result else files[0]["path"])

        for i, path in enumerate(result):
            name = Path(path).stem
            logger.info(f"  챕터 {i+1} BGM: {name}")
        return result

    except (ValueError, IndexError):
        logger.warning("BGM 챕터별 선택 파싱 실패, 첫 번째 곡으로 통일")
        return [files[0]["path"]] * len(chapters)
