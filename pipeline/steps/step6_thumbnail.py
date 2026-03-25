"""Step 6: YTN 뉴스 스타일 썸네일 생성 (아이작TV 기본 템플릿)

핵심 스타일:
- 사실적 배경 (첫 번째 씬 이미지 + 약한 블러 + 어두운 그라데이션)
- 좌측 정렬 3줄 텍스트 (한 줄씩 아래로)
  - Line 1: 주제 키워드 (흰색)
  - Line 2: 핵심 인용문 (흰색)
  - Line 3: 출처/서브 (노란색 #FFE500)
- 좌측 상단: 빨간 뱃지 (긴급 보고서 등)
- 우측 상단: 아이작TV 로고
- 우측 하단: 타임코드
- 폰트: malgunbd.ttf 105px, stroke 3 동색, 자간 -10
"""

import json
import logging
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
from pipeline.base import Step
from pipeline.context import PipelineContext
from config import config

logger = logging.getLogger(__name__)

# 기본 썸네일 설정
THUMB_STYLE = {
    "font_size": 105,         # 메인 텍스트 크기
    "stroke_thickness": 3,    # 동색 stroke로 글자 굵기 보강
    "letter_spacing": -10,    # 자간 (좁게)
    "line_gap": 125,          # 줄 간격
    "left_margin": 45,        # 좌측 여백
    "text_y_start": 280,      # 첫 줄 Y 위치
    "badge_font_size": 36,    # 뱃지 폰트 크기
    "logo_font_size": 38,     # 로고 폰트 크기
    "logo_text": "아이작TV",   # 채널명
    "line1_color": "#FFFFFF",  # 1줄 색상
    "line2_color": "#FFFFFF",  # 2줄 색상
    "line3_color": "#FFE500",  # 3줄 색상 (노란 강조)
    "badge_color": (215, 35, 25, 245),  # 뱃지 배경색
    "blur_radius": 4,         # 배경 블러
    "gradient_strength": 220,  # 그라데이션 강도
}


class GenerateThumbnailStep(Step):
    name = "generate_thumbnail"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        cfg = config["thumbnail"]
        w, h = cfg["width"], cfg["height"]

        # 텍스트 3줄 추출 (brief 기반 또는 제목 기반)
        lines = self._extract_three_lines(ctx)

        # 배경 이미지 (첫 번째 씬)
        bg_path = self._pick_best_background(ctx.image_paths)

        # 뱃지 텍스트 결정
        badge_text = self._get_badge_text(ctx)

        # 썸네일 생성
        output = f"{ctx.output_dir}/thumbnail.jpg"
        self._create_thumbnail(bg_path, output, lines, badge_text, w, h, cfg)
        logger.info(f"  썸네일 생성: {output}")

        ctx.thumbnail_path = output
        logger.info("썸네일 생성 완료")
        return ctx

    def _extract_three_lines(self, ctx) -> list:
        """brief 또는 제목에서 3줄 텍스트 추출

        Returns: [("텍스트", "색상"), ...]
        """
        s = THUMB_STYLE
        title = ctx.script.get("title", ctx.topic)

        # brief가 있으면 구조화된 정보 활용
        if ctx.brief:
            angle = ctx.brief.get("angle", "")
            # 챕터 제목에서 키워드 추출
            chapters = ctx.brief.get("chapters", [])
            first_ch = chapters[0].get("chapter_title", "") if chapters else ""

            # Line 1: 첫 챕터 제목 또는 앵글의 핵심 키워드
            line1 = first_ch if len(first_ch) <= 12 else first_ch[:12]
            # Line 2: 제목을 인용문으로
            line2 = self._make_quote(title)
            # Line 3: 출처 + 강조
            line3 = self._make_subtitle(title)

            return [
                (line1, s["line1_color"]),
                (line2, s["line2_color"]),
                (line3, s["line3_color"]),
            ]

        # brief 없으면 제목 기반 분리
        return self._split_title_to_lines(title)

    def _make_quote(self, title: str) -> str:
        """제목에서 핵심 인용문 추출"""
        # 괄호 안 내용 제거
        clean = title.split("(")[0].split("（")[0].strip()

        # ! 또는 , 기준으로 앞부분
        for sep in ["!", ",", "–", "-"]:
            if sep in clean:
                clean = clean.split(sep)[0].strip()
                break

        # 너무 길면 자르기
        if len(clean) > 15:
            clean = clean[:15]

        return f'"{clean}"'

    def _make_subtitle(self, title: str) -> str:
        """제목에서 출처/서브 텍스트 추출"""
        # 괄호 안 내용이 있으면 활용
        if "(" in title:
            sub = title.split("(")[1].split(")")[0]
            if len(sub) <= 15:
                return sub

        # 뒷부분 활용
        for sep in ["!", ",", "–", "-"]:
            if sep in title:
                parts = title.split(sep, 1)
                if len(parts) > 1 and parts[1].strip():
                    sub = parts[1].strip().split("(")[0].strip()
                    if len(sub) <= 15:
                        return sub

        return ""

    def _split_title_to_lines(self, title: str) -> list:
        """제목만으로 3줄 분리 (brief 없을 때)"""
        s = THUMB_STYLE
        lines = []

        # 구분자로 분리 시도
        for sep in ["!", "?", ",", "|", "–", "-", ":"]:
            if sep in title:
                parts = title.split(sep, 1)
                p1 = parts[0].strip() + (sep if sep in "!?" else "")
                p2 = parts[1].strip() if len(parts) > 1 else ""

                if len(p1) <= 8:
                    lines.append((p1, s["line1_color"]))
                    if p2:
                        quote = f'"{p2[:15]}"' if len(p2) > 15 else f'"{p2}"'
                        lines.append((quote, s["line2_color"]))
                else:
                    lines.append((f'"{p1[:15]}"', s["line2_color"]))

                break

        if not lines:
            lines.append((f'"{title[:15]}"', s["line2_color"]))

        # 3줄 미만이면 빈 줄로 채우기
        while len(lines) < 3:
            lines.append(("", s["line3_color"]))

        return lines[:3]

    def _get_badge_text(self, ctx) -> str:
        """뱃지 텍스트 결정"""
        if ctx.brief:
            # brief의 seo_keywords나 differentiation에서 추출
            keywords = ctx.brief.get("seo_keywords", [])
            if keywords:
                return "긴급 보고서"
        return "긴급 보고서"

    def _pick_best_background(self, image_paths: list) -> str | None:
        """배경 이미지 선택 (첫 번째 씬 — 보통 가장 임팩트 있음)"""
        if not image_paths:
            return None
        return image_paths[0]

    def _create_thumbnail(
        self, bg_path: str | None, output: str,
        lines: list, badge_text: str, w: int, h: int, cfg: dict
    ):
        """YTN 뉴스 스타일 썸네일 생성"""
        s = THUMB_STYLE
        font_path = cfg.get("font_path", "C:/Windows/Fonts/malgunbd.ttf")

        # --- 1. 배경 ---
        if bg_path and Path(bg_path).exists():
            canvas = Image.open(bg_path).resize((w, h)).convert("RGBA")
            canvas = canvas.filter(
                ImageFilter.GaussianBlur(radius=s["blur_radius"])
            )
        else:
            canvas = Image.new("RGBA", (w, h), (15, 15, 30, 255))

        # --- 2. 어두운 그라데이션 (상단 15%부터) ---
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for y in range(int(h * 0.15), h):
            progress = (y - h * 0.15) / (h * 0.85)
            alpha = int(s["gradient_strength"] * progress)
            gd.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, grad)
        draw = ImageDraw.Draw(canvas)

        # --- 3. 빨간 뱃지 (좌측 상단) ---
        try:
            f_badge = ImageFont.truetype(font_path, s["badge_font_size"])
        except (OSError, IOError):
            f_badge = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), badge_text, font=f_badge)
        tw, th_b = bbox[2] - bbox[0], bbox[3] - bbox[1]

        badge_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge_layer)
        bx, by = s["left_margin"] - 5, 28
        bd.rounded_rectangle(
            [bx, by, bx + tw + 36, by + th_b + 22],
            radius=6, fill=s["badge_color"]
        )
        canvas = Image.alpha_composite(canvas, badge_layer)
        draw = ImageDraw.Draw(canvas)
        draw.text((bx + 18, by + 10), badge_text, font=f_badge, fill="#FFFFFF")

        # --- 4. 채널 로고 (우측 상단) ---
        try:
            f_logo = ImageFont.truetype(font_path, s["logo_font_size"])
        except (OSError, IOError):
            f_logo = ImageFont.load_default()

        bbox_l = draw.textbbox((0, 0), s["logo_text"], font=f_logo)
        lw = bbox_l[2] - bbox_l[0]
        draw.text(
            (w - lw - 35 + 2, 32 + 2), s["logo_text"],
            font=f_logo, fill="#000000", stroke_width=4, stroke_fill="#000000"
        )
        draw.text(
            (w - lw - 35, 32), s["logo_text"],
            font=f_logo, fill="#FFFFFF", stroke_width=2, stroke_fill="#222222"
        )

        # --- 5. 3줄 텍스트 (좌측 정렬, 자간 좁게) ---
        try:
            f_text = ImageFont.truetype(font_path, s["font_size"])
        except (OSError, IOError):
            f_text = ImageFont.load_default()

        y = s["text_y_start"]
        for text, color in lines:
            if text:
                self._draw_tight_text(
                    draw, text, f_text, s["left_margin"], y,
                    fill=color,
                    spacing=s["letter_spacing"],
                    thickness=s["stroke_thickness"],
                )
            y += s["line_gap"]

        # --- 6. 타임코드 (우측 하단) ---
        duration = getattr(
            self, '_duration', 0
        ) or self._estimate_duration(lines)
        time_text = self._format_duration(duration)

        try:
            f_time = ImageFont.truetype(font_path, 22)
        except (OSError, IOError):
            f_time = ImageFont.load_default()

        time_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        td = ImageDraw.Draw(time_layer)
        bbox_t = td.textbbox((0, 0), time_text, font=f_time)
        ttw = bbox_t[2] - bbox_t[0]
        tth = bbox_t[3] - bbox_t[1]
        tx, ty = w - ttw - 22, h - tth - 16
        td.rounded_rectangle(
            [tx - 8, ty - 5, tx + ttw + 8, ty + tth + 5],
            radius=4, fill=(0, 0, 0, 200)
        )
        canvas = Image.alpha_composite(canvas, time_layer)
        draw = ImageDraw.Draw(canvas)
        draw.text((tx, ty), time_text, font=f_time, fill="#FFFFFF")

        # --- 저장 (YouTube 썸네일 2MB 제한 준수) ---
        rgb = canvas.convert("RGB")
        max_bytes = 2 * 1024 * 1024
        for q in [95, 90, 85, 80, 75]:
            rgb.save(output, "JPEG", quality=q, optimize=True)
            if Path(output).stat().st_size <= max_bytes:
                break

    @staticmethod
    def _draw_tight_text(
        draw, text, font, x, y, fill,
        spacing=-10, thickness=3
    ):
        """자간 조절 + 동색 stroke로 굵기 보강 텍스트 렌더링"""
        for char in text:
            bbox = draw.textbbox((0, 0), char, font=font)
            cw = bbox[2] - bbox[0]
            # 그림자
            draw.text(
                (x + 3, y + 3), char, font=font,
                fill="#000000",
                stroke_width=thickness, stroke_fill="#000000"
            )
            # 본문 (동색 stroke로 굵기 보강)
            draw.text(
                (x, y), char, font=font,
                fill=fill,
                stroke_width=thickness, stroke_fill=fill
            )
            x += cw + spacing

    @staticmethod
    def _estimate_duration(lines) -> int:
        """텍스트 길이 기반 대략적 영상 길이 추정 (초)"""
        return 480  # 기본 8분

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """초를 M:SS 형식으로 변환"""
        m, s = divmod(seconds, 60)
        return f"{m}:{s:02d}"
