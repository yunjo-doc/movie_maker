"""유튜브 롱폼 영상 자동화 파이프라인 CLI"""

import json
import sys
import os
import logging

# Windows 콘솔 UTF-8 출력 강제
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from pathlib import Path

import click

from config import config
from pipeline.context import PipelineContext
from pipeline.base import Pipeline
from pipeline.checkpoint import CheckpointManager
from pipeline.steps.step1_script import GenerateScriptStep
from pipeline.steps.step2_tts import GenerateTTSStep
from pipeline.steps.step3_storyboard import GenerateStoryboardStep
from pipeline.steps.step4_images import GenerateImagesStep
from pipeline.steps.step5_video import ComposeVideoStep
from pipeline.steps.step6_thumbnail import GenerateThumbnailStep
from pipeline.steps.step6b_metadata import GenerateMetadataStep
from pipeline.steps.step7_upload import UploadYouTubeStep
from pipeline.steps.step0_plan import InteractivePlanner
from pipeline.steps.step4b_i2v import GenerateI2VClipsStep
from pipeline.steps.step5b_capcut import GenerateCapCutDraftStep
from utils.logging_config import setup_logging


@click.group()
@click.option("--debug", is_flag=True, help="디버그 로깅")
def cli(debug):
    """유튜브 롱폼 영상 자동화 파이프라인"""
    setup_logging(level="DEBUG" if debug else config["pipeline"]["log_level"])


@cli.command()
@click.argument("topic")
@click.option("-p", "--project-id", default=None, help="프로젝트 ID")
def plan(topic, project_id):
    """인터랙티브 영상 기획 — 100만 구독자 유튜버처럼

    \b
    예시:
      python cli.py plan "AI가 바꿀 미래"
      python cli.py plan "주식 투자 전략" -p my_project
    """
    project_id = project_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = str(Path(config["pipeline"]["output_dir"]) / project_id)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    planner = InteractivePlanner()

    click.echo("")
    click.echo(f"{'='*60}")
    click.echo(f"  영상 기획 세션")
    click.echo(f"  주제: {topic}")
    click.echo(f"  프로젝트: {project_id}")
    click.echo(f"{'='*60}")

    # 0단계: 비주얼 스타일 선택
    click.echo(planner.show_style_menu())
    click.echo("")
    click.echo("AI 추천을 받으려면 'r' 입력")

    while True:
        style_input = click.prompt("\n스타일 번호", default="", show_default=False)
        if style_input.strip().lower() == "r":
            click.echo("\n스타일 추천 분석 중...\n")
            recommendation = planner.recommend_style(topic)
            click.echo(recommendation)
            click.echo("\n번호를 입력하세요 (1~8):")
            continue

        preset = planner.select_style(style_input)
        if preset:
            click.echo(f"\n  선택: [{style_input}] {preset['name']}")
            click.echo(f"  {preset['description']}")
            if click.confirm("  이 스타일로 진행할까요?", default=True):
                break
        else:
            click.echo("  1~8 사이 번호를 입력하세요.")

    click.echo("")

    # 1단계: 리서치 + 기획안 제안
    click.echo("리서치 중... (트렌드 분석 + 기획안 3개 생성)\n")
    result = planner.research_topic(topic)
    click.echo(result)
    click.echo("")

    # 2단계: 인터랙티브 대화
    click.echo(f"{'─'*60}")
    click.echo("피드백을 입력하세요. (완료: 'ok' 또는 '확정', 종료: 'quit')")
    click.echo(f"{'─'*60}")

    while True:
        feedback = click.prompt("\n당신", default="", show_default=False)
        if not feedback.strip():
            continue
        if feedback.strip().lower() in ("quit", "q", "종료"):
            click.echo("기획 세션 종료.")
            return
        if feedback.strip().lower() in ("ok", "확정", "완료", "done"):
            break

        click.echo("")
        response = planner.refine(feedback)
        click.echo(response)

    # 3단계: 최종 기획서 생성
    click.echo(f"\n{'─'*60}")
    click.echo("최종 기획서 생성 중...")
    click.echo(f"{'─'*60}\n")

    brief_text = planner.finalize_brief()

    try:
        brief_path = planner.save_brief(brief_text, output_dir)
        planner.save_conversation(output_dir)

        click.echo(brief_text)
        click.echo(f"\n{'='*60}")
        click.echo(f"  기획서 저장 완료: {brief_path}")
        click.echo(f"")
        click.echo(f"  영상 제작 명령어:")
        click.echo(f'    python cli.py run "{topic}" -p {project_id} --brief')
        click.echo(f"{'='*60}")
    except (json.JSONDecodeError, ValueError) as e:
        click.echo(f"\n기획서 JSON 파싱 실패: {e}")
        click.echo("대화 내용은 저장됩니다. 다시 시도해주세요.")
        planner.save_conversation(output_dir)


@cli.command()
@click.argument("topic")
@click.option("-p", "--project-id", default=None, help="프로젝트 ID")
@click.option("-r", "--resume", is_flag=True, help="체크포인트에서 재개")
@click.option("--skip-upload", is_flag=True, help="업로드 단계 건너뛰기")
@click.option("--capcut", is_flag=True, help="CapCut 드래프트도 함께 생성")
@click.option("--brief", is_flag=True, help="기획서(brief.json) 기반으로 대본 생성")
@click.option("--schedule", default=None, help="예약 발행 시각 (예: 18:00, KST 기준)")
def run(topic, project_id, resume, skip_upload, capcut, brief, schedule):
    """전체 파이프라인 실행

    \b
    예시:
      python cli.py run "AI 기술 트렌드 2026"
      python cli.py run "우주의 신비" --capcut
      python cli.py run "건강 상식" --skip-upload --capcut
    """
    logger = logging.getLogger(__name__)

    project_id = project_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = str(Path(config["pipeline"]["output_dir"]) / project_id)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 기획서 로드
    brief_data = {}
    if brief:
        brief_path = Path(output_dir) / "brief.json"
        if brief_path.exists():
            brief_data = json.loads(brief_path.read_text(encoding="utf-8"))
            click.echo(f"  기획서 로드: {brief_path}")
        else:
            click.echo(f"기획서 없음: {brief_path}")
            click.echo(f'먼저 실행: python cli.py plan "{topic}" -p {project_id}')
            sys.exit(1)

    # 예약 발행 설정
    if schedule:
        config["youtube"]["schedule_time"] = schedule

    ctx = PipelineContext(
        project_id=project_id,
        topic=topic,
        output_dir=output_dir,
        brief=brief_data,
    )

    steps = [
        GenerateScriptStep(),
        GenerateTTSStep(),
        GenerateStoryboardStep(),
        GenerateImagesStep(),
        GenerateI2VClipsStep(),
        ComposeVideoStep(),
    ]
    if capcut:
        steps.append(GenerateCapCutDraftStep())
    steps.append(GenerateThumbnailStep())
    steps.append(GenerateMetadataStep())
    if not skip_upload:
        steps.append(UploadYouTubeStep())

    checkpoint = CheckpointManager(output_dir)
    pipeline = Pipeline(steps, checkpoint)

    click.echo(f"")
    click.echo(f"{'='*60}")
    click.echo(f"  영상 자동화 파이프라인")
    click.echo(f"  주제: {topic}")
    click.echo(f"  프로젝트: {project_id}")
    click.echo(f"  출력: {output_dir}")
    click.echo(f"{'='*60}")
    click.echo(f"")

    try:
        result = pipeline.run(ctx, resume=resume)
        click.echo(f"")
        click.echo(f"{'='*60}")
        click.echo(f"  완료!")
        click.echo(f"  영상: {result.video_path}")
        click.echo(f"  썸네일: {result.thumbnail_path}")
        if result.video_url:
            click.echo(f"  YouTube: {result.video_url}")
        click.echo(f"{'='*60}")

    except KeyboardInterrupt:
        click.echo(f"\n중단됨. 재개 명령어:")
        click.echo(f'  python cli.py run "{topic}" -p {project_id} --resume')
        sys.exit(1)

    except Exception as e:
        logger.exception(f"파이프라인 실패: {e}")
        click.echo(f"\n실패: {e}")
        click.echo(f'재개: python cli.py run "{topic}" -p {project_id} --resume')
        sys.exit(1)


@cli.command()
@click.argument("project_id")
def status(project_id):
    """프로젝트 진행 상태 확인"""
    output_dir = str(Path(config["pipeline"]["output_dir"]) / project_id)
    checkpoint = CheckpointManager(output_dir)
    ctx, completed = checkpoint.load()

    if not ctx:
        click.echo("체크포인트 없음.")
        return

    click.echo(f"주제: {ctx.topic}")
    click.echo(f"프로젝트: {ctx.project_id}")
    click.echo(f"")

    all_steps = [
        "generate_script", "generate_tts", "generate_storyboard",
        "generate_images", "generate_i2v_clips", "compose_video",
        "generate_thumbnail", "generate_metadata", "upload_youtube",
    ]
    for s in all_steps:
        mark = "done" if s in completed else "    "
        click.echo(f"  [{mark}] {s}")

    click.echo(f"")
    if ctx.video_path:
        click.echo(f"영상: {ctx.video_path}")
    if ctx.video_url:
        click.echo(f"YouTube: {ctx.video_url}")


@cli.command()
def auth():
    """YouTube OAuth 인증 (최초 1회)"""
    from utils.youtube_auth import get_youtube_service
    get_youtube_service()
    click.echo("YouTube 인증 성공!")


if __name__ == "__main__":
    cli()
