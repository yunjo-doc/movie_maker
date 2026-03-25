"""FFmpeg 기반 롱폼 영상 합성기 — 검증된 3-Phase 파이프라인"""

import subprocess
import shutil
import logging
from pathlib import Path
from utils.path_safety import SafeWorkDir

logger = logging.getLogger(__name__)


class FFmpegComposer:
    def __init__(self, cfg: dict):
        w, h = cfg["resolution"].split("x")
        self.width = int(w)
        self.height = int(h)
        self.fps = cfg.get("fps", 30)
        self.crf = cfg.get("crf", 18)
        self.crf_intermediate = cfg.get("crf_intermediate", 12)
        self.min_bitrate = cfg.get("min_bitrate", "4M")
        self.max_bitrate = cfg.get("max_bitrate", "12M")
        self.bufsize = cfg.get("bufsize", "16M")
        self.preset = cfg.get("preset", "medium")
        self.font_name = cfg.get("font_name", "Malgun Gothic")
        self.font_size = cfg.get("font_size", 24)
        self.margin_v = cfg.get("subtitle_margin_v", 40)
        self.transition_dur = cfg.get("transition_duration", 0.5)
        self.bgm_dir = cfg.get("bgm_dir", "bgm")
        self.bgm_volume = cfg.get("bgm_volume", 0.08)

    def compose(
        self,
        segments: list,  # [{"image": path, "duration": float, "effect": str}]
        audio_path: str,
        subtitle_path: str,
        output_path: str,
        bgm_path: str = None,
        bgm_paths: list = None,
        chapters: list = None,
    ):
        """4-Phase 영상 합성 파이프라인"""
        safe = SafeWorkDir()
        work = safe.create()
        logger.info(f"작업 디렉토리: {work}")

        try:
            # Phase A: 이미지 전처리
            logger.info("  Phase A: 이미지 전처리 (해상도 통일)")
            processed = []
            for i, seg in enumerate(segments):
                out = f"{work}/img_{i:04d}.jpg"
                self._preprocess_image(seg["image"], out)
                processed.append(out)

            # Phase B: 클립 생성 (I2V 비디오 클립 또는 Ken Burns) + 트랜지션
            logger.info("  Phase B: 클립 생성 + 트랜지션")
            clips = []
            for i, (img, seg) in enumerate(zip(processed, segments)):
                clip = f"{work}/clip_{i:04d}.mp4"
                dur = seg["duration"]
                effect = seg.get("effect", "zoom_in")
                video_clip = seg.get("video_clip", "")

                if video_clip and Path(video_clip).exists():
                    self._adapt_video_clip(video_clip, clip, dur)
                    logger.info(f"    클립 {i+1}/{len(segments)} ({dur}초, I2V)")
                else:
                    self._create_ken_burns_clip(img, clip, dur, effect)
                    logger.info(f"    클립 {i+1}/{len(segments)} ({dur}초, {effect})")

                # 트랜지션: 각 클립에 fade-in/fade-out 적용
                if self.transition_dur > 0:
                    faded = f"{work}/faded_{i:04d}.mp4"
                    try:
                        self._add_fade(clip, faded, dur)
                        clips.append(faded)
                    except Exception as e:
                        logger.warning(f"    fade 실패, 원본 사용: {e}")
                        clips.append(clip)
                else:
                    clips.append(clip)

            logger.info("  Phase B: 클립 concat")
            video_only = f"{work}/video_only.mp4"
            self._concat_clips(clips, video_only)

            # Phase C: BGM 준비 (챕터별 또는 단일)
            safe_bgm = None
            if bgm_paths and chapters and len(bgm_paths) > 1:
                logger.info(f"  Phase C: 챕터별 BGM 합성 ({len(bgm_paths)}곡)")
                total_dur = sum(s["duration"] for s in segments)
                safe_bgm = self._build_chapter_bgm(
                    bgm_paths, chapters, segments, total_dur, work
                )
            else:
                resolved_bgm = bgm_path or self._find_bgm()
                if resolved_bgm:
                    logger.info(f"  Phase C: BGM 믹싱 ({Path(resolved_bgm).name})")
                    safe_bgm = f"{work}/bgm.mp3"
                    shutil.copy2(resolved_bgm, safe_bgm)

            # Phase D: 오디오 + 자막 + BGM 합성
            logger.info("  Phase D: 최종 합성 (오디오 + 자막 + BGM)")
            safe_audio = f"{work}/audio.mp3"
            shutil.copy2(audio_path, safe_audio)

            srt_has_content = False
            if subtitle_path and Path(subtitle_path).exists():
                srt_size = Path(subtitle_path).stat().st_size
                if srt_size > 10:
                    srt_has_content = True

            final = f"{work}/final.mp4"
            if srt_has_content:
                safe_srt = f"{work}/subs.srt"
                shutil.copy2(subtitle_path, safe_srt)
                self._final_compose(video_only, safe_audio, safe_srt, final, safe_bgm)
            else:
                logger.warning("  자막 파일이 비어있어 자막 없이 합성합니다")
                self._final_compose_no_subs(video_only, safe_audio, final, safe_bgm)

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final, output_path)
            logger.info(f"  영상 생성 완료: {output_path}")

        finally:
            safe.cleanup()

    def _build_chapter_bgm(self, bgm_paths: list, chapters: list,
                           segments: list, total_dur: float, work: str) -> str:
        """챕터별 BGM을 하나의 연속 트랙으로 합성 (크로스페이드 포함)"""
        num_chapters = len(chapters)
        segs_per_ch = len(segments) / num_chapters if num_chapters else len(segments)
        crossfade = 2.0  # 챕터 전환 크로스페이드 (초)

        # 챕터별 duration 계산
        ch_durations = []
        for ch_idx in range(num_chapters):
            start_seg = int(ch_idx * segs_per_ch)
            end_seg = int((ch_idx + 1) * segs_per_ch)
            dur = sum(segments[i]["duration"] for i in range(start_seg, min(end_seg, len(segments))))
            ch_durations.append(dur)

        # 챕터별 BGM 클립 생성 (trim + fade)
        ch_bgm_clips = []
        for i, (bgm_path, dur) in enumerate(zip(bgm_paths, ch_durations)):
            ch_bgm = f"{work}/ch_bgm_{i:02d}.mp3"
            fade_out_start = max(0, dur - crossfade)
            self._run_ffmpeg([
                "-i", bgm_path,
                "-t", str(dur),
                "-af", (
                    f"afade=t=in:st=0:d={crossfade},"
                    f"afade=t=out:st={fade_out_start}:d={crossfade}"
                ),
                "-ar", "48000", "-ac", "2",
                ch_bgm
            ])
            ch_bgm_clips.append(ch_bgm)
            logger.info(f"    챕터 {i+1} BGM: {Path(bgm_path).stem} ({dur:.0f}초)")

        # 챕터 BGM들을 concat
        concat_file = f"{work}/bgm_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for c in ch_bgm_clips:
                safe_path = c.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        composite_bgm = f"{work}/bgm.mp3"
        self._run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-ar", "48000", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "192k",
            composite_bgm
        ])
        return composite_bgm

    def _run_ffmpeg(self, args: list, timeout: int = 600):
        """FFmpeg 실행 래퍼"""
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[:500]}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )

    def _preprocess_image(self, input_path: str, output_path: str):
        """이미지를 target 해상도로 통일 (비율 유지 + 패딩)"""
        self._run_ffmpeg([
            "-i", input_path,
            "-vf", (
                f"scale={self.width}:{self.height}"
                ":force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black"
            ),
            "-q:v", "2", output_path
        ])

    def _create_ken_burns_clip(self, image: str, output: str,
                                duration: float, effect: str):
        """Ken Burns 효과 적용 클립 생성"""
        d = int(duration * self.fps)
        w, h, fps = self.width, self.height, self.fps

        filters = {
            "zoom_in": (
                f"zoompan=z='min(zoom+0.001,1.3)'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={d}:s={w}x{h}:fps={fps}"
            ),
            "zoom_out": (
                f"zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.001))'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={d}:s={w}x{h}:fps={fps}"
            ),
            "pan_right": (
                f"zoompan=z='1.2'"
                f":x='if(lte(on,1),0,min(x+1,(iw-iw/zoom)))'"
                f":y='ih/2-(ih/zoom/2)'"
                f":d={d}:s={w}x{h}:fps={fps}"
            ),
            "pan_left": (
                f"zoompan=z='1.2'"
                f":x='if(lte(on,1),(iw-iw/zoom),max(0,x-1))'"
                f":y='ih/2-(ih/zoom/2)'"
                f":d={d}:s={w}x{h}:fps={fps}"
            ),
            "static": (
                f"zoompan=z='1'"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={d}:s={w}x{h}:fps={fps}"
            ),
        }

        vf = filters.get(effect, filters["zoom_in"])

        self._run_ffmpeg([
            "-loop", "1", "-i", image,
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf_intermediate),
            "-pix_fmt", "yuv420p", "-r", str(self.fps),
            output
        ])

    def _add_fade(self, input_clip: str, output: str, duration: float):
        """클립에 fade-in/fade-out 트랜지션 적용"""
        fd = self.transition_dur
        fade_out_start = max(0, duration - fd)
        self._run_ffmpeg([
            "-i", input_clip,
            "-vf", (
                f"fade=t=in:st=0:d={fd},"
                f"fade=t=out:st={fade_out_start}:d={fd}"
            ),
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf_intermediate),
            "-pix_fmt", "yuv420p",
            output
        ])

    def _find_bgm(self) -> str | None:
        """bgm 폴더에서 BGM 파일 찾기 (첫 번째 mp3/wav)"""
        bgm_dir = Path(self.bgm_dir)
        if not bgm_dir.exists():
            return None
        for ext in ("*.mp3", "*.wav", "*.m4a"):
            files = sorted(bgm_dir.glob(ext))
            if files:
                return str(files[0])
        return None

    def _get_duration(self, input_path: str) -> float:
        """ffprobe로 영상 길이 조회"""
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        try:
            return float(result.stdout.strip())
        except (ValueError, AttributeError):
            return 5.0  # 기본값

    def _adapt_video_clip(self, input_clip: str, output: str, target_duration: float):
        """I2V 비디오 클립을 target 해상도/duration에 맞춤

        - 해상도 통일 (비율 유지 + 패딩)
        - duration이 짧으면 속도 조절, 길면 trim
        """
        w, h, fps = self.width, self.height, self.fps

        clip_dur = self._get_duration(input_clip)
        speed_factor = clip_dur / target_duration if target_duration > 0 else 1.0

        self._run_ffmpeg([
            "-i", input_clip,
            "-vf", (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setpts=PTS/{speed_factor}"
            ),
            "-t", str(target_duration),
            "-an",  # I2V 클립의 오디오 제거 (나레이션 사용)
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
            "-pix_fmt", "yuv420p", "-r", str(fps),
            output
        ], timeout=120)

    def _concat_clips(self, clips: list, output: str):
        """클립들을 concat demuxer로 합치기"""
        concat_file = f"{Path(output).parent}/concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for c in clips:
                # 경로를 forward slash로 통일
                safe_path = c.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        self._run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output
        ])

    def _final_compose(self, video: str, audio: str,
                       subtitle: str, output: str, bgm: str = None):
        """비디오 + 오디오 + 자막 + BGM 최종 합성"""
        work_dir = str(Path(video).parent)
        sub_name = Path(subtitle).name
        vid_name = Path(video).name
        aud_name = Path(audio).name
        out_name = Path(output).name

        inputs = ["-i", vid_name, "-i", aud_name]
        if bgm:
            bgm_name = Path(bgm).name
            inputs += ["-i", bgm_name]
            # 나레이션 원본 + BGM 볼륨 조절 후 믹스
            # normalize=0: amix 자동 정규화 비활성 (볼륨 반감 방지)
            # dynaudnorm: 동적 오디오 정규화 (YouTube 볼륨 수준)
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={self.bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
                f"[narr][bgm]amix=inputs=2:duration=shortest:normalize=0,"
                f"dynaudnorm=p=0.9:s=5[aout]"
            )
            audio_map = ["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"]
        else:
            audio_map = ["-map", "0:v", "-map", "1:a"]

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            *inputs,
            "-vf", (
                f"subtitles={sub_name}"
                f":force_style='FontName={self.font_name},"
                f"FontSize={self.font_size},"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "Outline=2,Shadow=1,Alignment=2,"
                f"MarginV={self.margin_v}'"
            ),
            *audio_map,
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
            "-maxrate", self.max_bitrate, "-bufsize", self.bufsize,
            "-profile:v", "high", "-level", "4.2",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            "-max_muxing_queue_size", "1024",
            out_name
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=600, encoding="utf-8", errors="replace",
            cwd=work_dir,
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[:500]}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )

    def _final_compose_no_subs(self, video: str, audio: str,
                                output: str, bgm: str = None):
        """자막 없이 비디오 + 오디오 + BGM 합성"""
        work_dir = str(Path(video).parent)
        vid_name = Path(video).name
        aud_name = Path(audio).name
        out_name = Path(output).name

        inputs = ["-i", vid_name, "-i", aud_name]
        if bgm:
            bgm_name = Path(bgm).name
            inputs += ["-i", bgm_name]
            audio_filter = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={self.bgm_volume},aloop=loop=-1:size=2e+09[bgm];"
                f"[narr][bgm]amix=inputs=2:duration=shortest:normalize=0,"
                f"dynaudnorm=p=0.9:s=5[aout]"
            )
            audio_map = ["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"]
        else:
            # BGM 없을 때도 동적 정규화 적용
            audio_filter = "[1:a]dynaudnorm=p=0.9:s=5[aout]"
            audio_map = ["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"]

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            *inputs,
            *audio_map,
            "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
            "-maxrate", self.max_bitrate, "-bufsize", self.bufsize,
            "-profile:v", "high", "-level", "4.2",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            out_name
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=600, encoding="utf-8", errors="replace",
            cwd=work_dir,
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[:500]}")
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
