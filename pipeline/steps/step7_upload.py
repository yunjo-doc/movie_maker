"""Step 7: YouTube 업로드 + 예약 발행"""

import logging
from datetime import datetime, timedelta
from pipeline.base import Step
from pipeline.context import PipelineContext
from utils.youtube_auth import get_youtube_service
from googleapiclient.http import MediaFileUpload
from config import config

logger = logging.getLogger(__name__)


class UploadYouTubeStep(Step):
    name = "upload_youtube"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        cfg = config["youtube"]

        logger.info("YouTube 인증 중...")
        youtube = get_youtube_service()

        # 예약 발행 시간 계산
        schedule_time = cfg.get("schedule_time", "")
        publish_at = None
        privacy = cfg["privacy_status"]

        if schedule_time:
            publish_at = self._calculate_publish_time(schedule_time)
            privacy = "private"  # 예약 발행은 private 필수
            logger.info(f"예약 발행: {publish_at}")

        body = {
            "snippet": {
                "title": ctx.metadata.get("title", ctx.topic)[:100],
                "description": ctx.metadata.get("description", "")[:5000],
                "tags": ctx.metadata.get("tags", []),
                "categoryId": cfg["category_id"],
                "defaultLanguage": cfg["default_language"],
                "defaultAudioLanguage": cfg["default_language"],
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        if publish_at:
            body["status"]["publishAt"] = publish_at

        logger.info(f"업로드 시작: {ctx.video_path}")
        media = MediaFileUpload(
            ctx.video_path, mimetype="video/mp4",
            resumable=True, chunksize=256 * 1024,
        )

        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct % 20 == 0:
                    logger.info(f"  업로드: {pct}%")

        video_id = response["id"]

        # 썸네일 설정
        if ctx.thumbnail_path:
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(ctx.thumbnail_path),
                ).execute()
                logger.info("  썸네일 설정 완료")
            except Exception as e:
                logger.warning(f"  썸네일 설정 실패 (채널 인증 필요?): {e}")

        ctx.video_id = video_id
        ctx.video_url = f"https://youtu.be/{video_id}"

        if publish_at:
            logger.info(f"업로드 완료 (예약): {ctx.video_url} → {publish_at}")
        else:
            logger.info(f"업로드 완료: {ctx.video_url}")
        return ctx

    @staticmethod
    def _calculate_publish_time(time_str: str) -> str:
        """다음 해당 시각을 ISO 8601 형식으로 반환

        예: "18:00" → 오늘 18시가 지났으면 내일 18시, 아니면 오늘 18시
        한국 시간(KST, UTC+9) 기준으로 계산
        """
        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            hour, minute = 18, 0

        now = datetime.utcnow()
        kst_now = now + timedelta(hours=9)

        target_kst = kst_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target_kst <= kst_now:
            target_kst += timedelta(days=1)

        # KST → UTC
        target_utc = target_kst - timedelta(hours=9)
        return target_utc.strftime("%Y-%m-%dT%H:%M:%S.0Z")
