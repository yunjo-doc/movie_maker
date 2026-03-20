"""Step 6: 프로급 썸네일 생성 (슈퍼휴먼X 스타일 참고)

핵심 스타일:
- 초대형 텍스트가 프레임 대부분을 차지
- 3단계 텍스트 계층: 후킹(소) -> 핵심 키워드(대) -> 액션(강조색)
- 두꺼운 검정 외곽선 (stroke 8~10)
- 어두운 배경 + 강한 블러
- 색상: 흰색(메인) + 노란색(강조)
- 3장 생성 (A/B 테스트용)
"""

import logging
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
from pipeline.base import Step
from pipeline.context import PipelineContext
from config import config

logger = logging.getLogger(__name__)

# 색상 프리셋 (고대비 조합)
COLOR_SCHEMES = [
    {  # 노랑 강조 (가장 인기)
        "hook": "#FFFFFF",
        "main": "#FFFFFF",
        "accent": "#FFE500",
        "stroke": "#000000",
        "overlay_alpha": 160,
    },
    {  # 빨강 강조
        "hook": "#FFFFFF",
        "main": "#FFFFFF",
        "accent": "#FF4444",
        "stroke": "#000000",
        "overlay_alpha": 170,
    },
    {  # 초록 강조
        "hook": "#FFFFFF",
        "main": "#FFFFFF",
        "accent": "#00FF88",
        "stroke": "#000000",
        "overlay_alpha": 160,
    },
]


class GenerateThumbnailStep(Step):
    name = "generate_thumbnail"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        cfg = config["thumbnail"]
        title = ctx.script.get("title", ctx.topic)
        w, h = cfg["width"], cfg["height"]

        # 3단계 텍스트 계층 추출
        layers = self._extract_text_layers(title)

        # 배경 이미지 선택 (가장 임팩트 있는 씬)
        bg_path = self._pick_best_background(ctx.image_paths)

        # 3가지 변형 생성 (A/B 테스트)
        output_paths = []
        for i, scheme in enumerate(COLOR_SCHEMES):
            output = f"{ctx.output_dir}/thumbnail_{i+1}.jpg"
            self._create_thumbnail(bg_path, output, layers, w, h, cfg, scheme)
            output_paths.append(output)
            logger.info(f"  썸네일 {i+1}/3 생성: {output}")

        # 첫 번째를 기본 썸네일로
        main_output = f"{ctx.output_dir}/thumbnail.jpg"
        Image.open(output_paths[0]).save(main_output, quality=95)

        ctx.thumbnail_path = main_output
        logger.info("썸네일 생성 완료 (3장, A/B 테스트용)")
        return ctx

    def _extract_text_layers(self, title: str) -> dict:
        """제목에서 3단계 텍스트 계층 추출

        Returns: {"hook": "후킹 문구", "main": ["핵심", "키워드"], "accent": "강조 문구"}
        """
        hook = ""
        main_lines = []
        accent = ""

        # 1) ?나 ! 기준으로 분리 시도
        for sep in ["?", "!"]:
            if sep in title:
                parts = title.split(sep, 1)
                hook_part = parts[0].strip() + sep
                rest = parts[1].strip()

                # 후킹 부분이 너무 길면 줄바꿈
                hook_lines = self._wrap_text(hook_part, 12)
                if len(hook_lines) <= 2:
                    hook = "\n".join(hook_lines)
                else:
                    hook = "\n".join(hook_lines[:2])

                # 나머지를 main + accent로 분리
                if rest:
                    rest_words = self._wrap_text(rest, 10)
                    if len(rest_words) >= 2:
                        main_lines = rest_words[:-1][:2]  # 최대 2줄
                        accent = rest_words[-1]
                    else:
                        main_lines = rest_words[:1]
                        accent = ""
                return {"hook": hook, "main": main_lines, "accent": accent}

        # 2) 구분자(|, -, :)로 분리 시도
        for sep in ["|", " - ", ":", "—"]:
            if sep in title:
                parts = title.split(sep, 1)
                hook = parts[0].strip()
                rest = parts[1].strip()
                rest_lines = self._wrap_text(rest, 10)
                if len(rest_lines) >= 2:
                    main_lines = rest_lines[:-1][:2]
                    accent = rest_lines[-1]
                else:
                    main_lines = rest_lines
                return {"hook": hook, "main": main_lines, "accent": accent}

        # 3) 구분자 없으면 길이 기반 분리
        all_lines = self._wrap_text(title, 9)
        if len(all_lines) >= 3:
            hook = all_lines[0]
            main_lines = all_lines[1:-1][:2]
            accent = all_lines[-1]
        elif len(all_lines) == 2:
            hook = ""
            main_lines = [all_lines[0]]
            accent = all_lines[1]
        else:
            main_lines = all_lines

        return {"hook": hook, "main": main_lines, "accent": accent}

    def _pick_best_background(self, image_paths: list) -> str | None:
        """가장 임팩트 있는 배경 이미지 선택 (중간 씬)"""
        if not image_paths:
            return None
        mid = len(image_paths) // 2
        return image_paths[mid]

    def _create_thumbnail(
        self, bg_path: str | None, output: str,
        layers: dict, w: int, h: int, cfg: dict, scheme: dict
    ):
        """프로급 썸네일 한 장 생성 (슈퍼휴먼X 스타일)"""

        # --- 1. 배경 ---
        if bg_path and Path(bg_path).exists():
            canvas = Image.open(bg_path).resize((w, h))
            canvas = canvas.convert("RGBA")
            # 강한 블러 (텍스트 가독성 극대화)
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius=8))
        else:
            canvas = Image.new("RGBA", (w, h), (15, 15, 30, 255))

        # --- 2. 어두운 오버레이 (전체) ---
        overlay = Image.new("RGBA", (w, h),
                            (0, 0, 0, scheme["overlay_alpha"]))
        canvas = Image.alpha_composite(canvas, overlay)

        # --- 3. 하단 추가 그라데이션 ---
        gradient = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(gradient)
        for y in range(h // 2, h):
            progress = (y - h // 2) / (h / 2)
            alpha = int(100 * progress)
            gdraw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, gradient)

        draw = ImageDraw.Draw(canvas)

        # --- 4. 폰트 로드 ---
        font_path = cfg.get("font_path", "C:/Windows/Fonts/malgunbd.ttf")
        base_size = cfg.get("font_size", 64)

        # 텍스트 크기 설계 (프레임 대부분을 차지하도록)
        hook_size = int(base_size * 0.75)    # 48px
        main_size = int(base_size * 1.35)    # 86px
        accent_size = int(base_size * 1.25)  # 80px

        try:
            hook_font = ImageFont.truetype(font_path, hook_size)
            main_font = ImageFont.truetype(font_path, main_size)
            accent_font = ImageFont.truetype(font_path, accent_size)
        except (OSError, IOError):
            logger.warning(f"폰트 로드 실패: {font_path}")
            hook_font = main_font = accent_font = ImageFont.load_default()

        # --- 5. 텍스트 배치 (중앙 정렬, 세로 중심) ---
        hook_text = layers.get("hook", "")
        main_lines = layers.get("main", [])
        accent_text = layers.get("accent", "")

        # 전체 텍스트 높이 계산
        line_gap = 12
        block_gap = 20
        total_h = 0

        hook_lines_split = hook_text.split("\n") if hook_text else []
        if hook_lines_split:
            total_h += len(hook_lines_split) * (hook_size + line_gap)
            total_h += block_gap

        if main_lines:
            total_h += len(main_lines) * (main_size + line_gap)
            total_h += block_gap

        if accent_text:
            total_h += accent_size + line_gap

        # 세로 중심 시작점 (약간 위로 치우침)
        y = max(40, (h - total_h) // 2 - 20)
        x_center = w // 2

        # --- 후킹 텍스트 (작고 흰색) ---
        if hook_lines_split:
            for line in hook_lines_split:
                self._draw_outlined_text(
                    draw, line, hook_font, x_center, y,
                    fill=scheme["hook"], stroke=scheme["stroke"],
                    stroke_width=5, shadow_offset=3
                )
                y += hook_size + line_gap
            y += block_gap

        # --- 메인 키워드 (크고 굵게, 흰색) ---
        for line in main_lines:
            self._draw_outlined_text(
                draw, line, main_font, x_center, y,
                fill=scheme["main"], stroke=scheme["stroke"],
                stroke_width=8, shadow_offset=4
            )
            y += main_size + line_gap

        if main_lines:
            y += block_gap

        # --- 강조 텍스트 (크고 노란색/빨간색) ---
        if accent_text:
            self._draw_outlined_text(
                draw, accent_text, accent_font, x_center, y,
                fill=scheme["accent"], stroke=scheme["stroke"],
                stroke_width=8, shadow_offset=4
            )

        # --- 6. 상단 얇은 컬러 라인 (브랜드 느낌) ---
        accent_bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(accent_bar)
        bar_draw.rectangle([0, 0, w, 5], fill=scheme["accent"])
        canvas = Image.alpha_composite(canvas, accent_bar)

        canvas.convert("RGB").save(output, quality=95)

    def _draw_outlined_text(
        self, draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
        x_center: int, y: int, fill: str, stroke: str,
        stroke_width: int = 8, shadow_offset: int = 4
    ):
        """두꺼운 외곽선 + 그림자 텍스트 렌더링 (중앙 정렬)"""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        x = x_center - text_w // 2

        # 그림자 (검정, 오프셋)
        draw.text(
            (x + shadow_offset, y + shadow_offset), text,
            font=font, fill="#000000",
        )
        # 외곽선 + 텍스트
        draw.text(
            (x, y), text, font=font,
            fill=fill,
            stroke_width=stroke_width, stroke_fill=stroke,
        )

    @staticmethod
    def _wrap_text(text: str, max_chars: int) -> list:
        """텍스트를 자연스럽게 줄바꿈 (한국어 기준)"""
        if len(text) <= max_chars:
            return [text]

        lines = []
        current = ""
        for char in text:
            current += char
            if len(current) >= max_chars:
                # 공백이나 조사에서 자연스럽게 끊기
                last_space = current.rfind(" ")
                if last_space > max_chars // 2:
                    lines.append(current[:last_space].strip())
                    current = current[last_space:].strip()
                else:
                    lines.append(current)
                    current = ""
        if current.strip():
            lines.append(current.strip())
        return lines
