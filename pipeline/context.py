"""파이프라인 전체에서 공유되는 상태 객체"""

from dataclasses import dataclass, field


@dataclass
class PipelineContext:
    project_id: str
    topic: str
    output_dir: str = ""
    work_dir: str = ""

    # Step 0: 기획서 (plan 명령으로 생성)
    brief: dict = field(default_factory=dict)

    # Step 1: 대본
    script: dict = field(default_factory=dict)

    # Step 2: TTS + SRT
    audio_path: str = ""
    srt_path: str = ""

    # Step 3: 스토리보드
    scenes: list = field(default_factory=list)

    # Step 4: 이미지
    image_paths: list = field(default_factory=list)

    # Step 4b: I2V 비디오 클립 (인덱스별, 빈 문자열이면 해당 씬은 Ken Burns)
    video_clips: list = field(default_factory=list)

    # Step 5: 영상
    video_path: str = ""

    # Step 6: 썸네일 + 메타데이터
    thumbnail_path: str = ""
    metadata: dict = field(default_factory=dict)

    # Step 7: 업로드
    video_id: str = ""
    video_url: str = ""
