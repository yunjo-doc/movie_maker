"""CapCut 드래프트 자동 생성기

이미지 + 음성(MP3) + 자막(SRT) → CapCut 프로젝트 자동 생성
CapCut을 열면 프로젝트가 바로 나타남 → 렌더링만 클릭
"""

import json
import os
import shutil
import uuid
import logging
from pathlib import Path
from datetime import timedelta
from mutagen.mp3 import MP3
from PIL import Image
import srt as srt_lib

logger = logging.getLogger(__name__)

# CapCut 드래프트 기본 경로
CAPCUT_DRAFTS_DIR = Path.home() / "AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"

# 시간 단위: 마이크로초 (1초 = 1,000,000)
MICROSECOND = 1_000_000


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def _make_speed(speed_id: str) -> dict:
    return {
        "curve_speed": None,
        "id": speed_id,
        "mode": 0,
        "speed": 1.0,
        "type": "speed",
    }


def _make_canvas(canvas_id: str) -> dict:
    return {
        "album_image": "",
        "blur": 0.0,
        "color": "",
        "id": canvas_id,
        "image": "",
        "image_id": "",
        "image_name": "",
        "source_platform": 0,
        "team_id": "",
        "type": "canvas_color",
    }


def _make_sound_channel_mapping(scm_id: str) -> dict:
    return {
        "audio_channel_mapping": 0,
        "id": scm_id,
        "is_config_open": False,
        "type": "",
    }


def _make_vocal_separation(vs_id: str) -> dict:
    return {
        "choice": 0,
        "id": vs_id,
        "production_path": "",
        "removed_sounds": [],
        "time_range": None,
        "type": "vocal_separation",
    }


def _make_material_animation(ma_id: str) -> dict:
    return {
        "animations": [],
        "id": ma_id,
        "type": "sticker_animation",
    }


def _make_material_color(mc_id: str) -> dict:
    return {
        "color_space": 0,
        "id": mc_id,
        "value": {"highlights": 0, "shadows": 0, "temperature": 0, "tone": 0},
    }


def _make_video_material(mat_id: str, file_path: str,
                          width: int, height: int, duration_us: int) -> dict:
    """비디오/이미지 소재 정의"""
    return {
        "aigc_type": "none",
        "audio_fade": None,
        "cartoon_path": "",
        "category_id": "",
        "category_name": "local",
        "check_flag": 62978047,
        "content_feature_info": None,
        "corner_pin": None,
        "crop": {
            "lower_left_x": 0.0, "lower_left_y": 1.0,
            "lower_right_x": 1.0, "lower_right_y": 1.0,
            "upper_left_x": 0.0, "upper_left_y": 0.0,
            "upper_right_x": 1.0, "upper_right_y": 0.0,
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "duration": duration_us,
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": False,
        "height": height,
        "id": mat_id,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_unified_beauty_mode": False,
        "local_material_id": str(uuid.uuid4()),
        "material_name": Path(file_path).name,
        "matting": {"flag": 0, "has_use_quick_brush": False,
                    "has_use_quick_eraser": False, "path": "",
                    "strokes": []},
        "path": file_path.replace("\\", "/"),
        "picture_from": "none",
        "reverse_path": "",
        "smart_motion": None,
        "source": 0,
        "source_platform": 0,
        "stable": None,
        "team_id": "",
        "type": "photo",
        "video_algorithm": {"algorithms": [], "deflicker": None,
                            "motion_blur_config": None,
                            "quality_enhance": None},
        "width": width,
    }


def _make_audio_material(mat_id: str, file_path: str, duration_us: int) -> dict:
    """오디오 소재 정의"""
    return {
        "app_id": 0,
        "category_id": "",
        "category_name": "local",
        "check_flag": 62914561,
        "duration": duration_us,
        "effect_id": "",
        "formula_id": "",
        "id": mat_id,
        "intensifies_path": "",
        "is_ai_clone_tone": False,
        "is_ugc": False,
        "local_material_id": str(uuid.uuid4()),
        "music_id": "",
        "name": Path(file_path).name,
        "path": file_path.replace("\\", "/"),
        "request_id": "",
        "resource_id": "",
        "search_id": "",
        "source_from": "",
        "source_platform": 0,
        "team_id": "",
        "text_id": "",
        "tone_category_id": "",
        "tone_category_name": "",
        "tone_effect_id": "",
        "tone_effect_name": "",
        "tone_platform": "",
        "tone_second_category_id": "",
        "tone_second_category_name": "",
        "tone_speaker": "",
        "tone_type": "",
        "type": "extract_music",
        "video_id": "",
        "wave_points": [],
    }


def _make_video_segment(seg_id: str, material_id: str,
                         start_us: int, duration_us: int,
                         extra_refs: list) -> dict:
    """비디오 트랙 세그먼트"""
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        },
        "common_keyframes": [],
        "enable_adjust": True,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_wheels": True,
        "enable_hsl": False,
        "enable_lut": True,
        "enable_video_mask": True,
        "extra_material_refs": extra_refs,
        "group_id": "",
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "id": seg_id,
        "intensifies_audio": False,
        "is_placeholder": False,
        "keyframe_refs": [],
        "material_id": material_id,
        "render_index": 0,
        "reverse": False,
        "source_timerange": {"duration": duration_us, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": duration_us, "start": start_us},
        "track_attribute": 1,
        "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True,
        "volume": 0.0,
    }


def _make_audio_segment(seg_id: str, material_id: str,
                         start_us: int, duration_us: int,
                         extra_refs: list) -> dict:
    """오디오 트랙 세그먼트"""
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        },
        "common_keyframes": [],
        "enable_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_wheels": True,
        "enable_hsl": False,
        "enable_lut": True,
        "enable_video_mask": True,
        "extra_material_refs": extra_refs,
        "group_id": "",
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "id": seg_id,
        "intensifies_audio": False,
        "is_placeholder": False,
        "keyframe_refs": [],
        "material_id": material_id,
        "render_index": 0,
        "reverse": False,
        "source_timerange": {"duration": duration_us, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": duration_us, "start": start_us},
        "track_attribute": 0,
        "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True,
        "volume": 1.0,
    }


def _make_text_material(text_id: str, content: str,
                         font_name: str = "Malgun Gothic Bold") -> dict:
    """CapCut 텍스트(자막) 소재 정의"""
    # content = 자막 텍스트 그대로
    rich_text = content

    return {
        "add_type": 0,
        "alignment": 1,  # 0=left, 1=center, 2=right
        "background_alpha": 1.0,
        "background_color": "",
        "background_height": 0.14,
        "background_horizontal_offset": 0.0,
        "background_round_radius": 0.0,
        "background_style": 0,
        "background_vertical_offset": 0.0,
        "background_width": 0.14,
        "base_content": "",
        "bold_weight": 400,
        "border_alpha": 1.0,
        "border_color": "",
        "border_width": 0.08,
        "caption_template_info": {"category_id": "", "category_name": "",
                                   "effect_id": "", "is_new": False,
                                   "path": "", "request_id": "",
                                   "resource_id": "", "resource_name": ""},
        "check_flag": 7,
        "combo_info": {"text_templates": []},
        "content": rich_text,
        "fixed_height": -1.0,
        "fixed_width": -1.0,
        "font_category_id": "",
        "font_category_name": "",
        "font_id": "",
        "font_name": font_name,
        "font_path": "",
        "font_resource_id": "",
        "font_size": 4.0,
        "font_source_platform": 0,
        "font_team_id": "",
        "font_title": font_name,
        "font_url": "",
        "fonts": [],
        "force_apply_line_max_width": False,
        "global_alpha": 1.0,
        "group_id": "",
        "has_shadow": False,
        "id": text_id,
        "initial_scale": 1.0,
        "inner_padding": -1.0,
        "is_lyric_effect_template": False,
        "is_rich_text": False,
        "is_words_linear_effect": False,
        "italic_degree": 0,
        "ktv_color": "",
        "language": "",
        "layer_weight": 1,
        "letter_spacing": 0.0,
        "line_feed": 1,
        "line_max_width": 0.82,
        "line_spacing": 0.02,
        "multi_language_current": "none",
        "name": "",
        "original_size": [],
        "preset_category": "",
        "preset_category_id": "",
        "preset_has_set_alignment": False,
        "preset_id": "",
        "preset_index": 0,
        "preset_name": "",
        "recognize_task_id": "",
        "recognize_type": 0,
        "relevance_segment": [],
        "shadow_alpha": 0.9,
        "shadow_angle": -45.0,
        "shadow_color": "",
        "shadow_distance": 5.0,
        "shadow_point": {"x": 0.6363961031, "y": -0.6363961031},
        "shadow_smoothing": 0.45,
        "shape_clip_x": False,
        "shape_clip_y": False,
        "source_from": "",
        "style_name": "",
        "sub_type": 0,
        "subtitle_keywords": None,
        "text_alpha": 1.0,
        "text_color": "#FFFFFF",
        "text_curve": None,
        "text_preset_resource_id": "",
        "text_size": 15,
        "text_to_audio_ids": [],
        "tts_auto_update": False,
        "type": "subtitle",
        "typesetting": 0,
        "underline": False,
        "underline_offset": 0.22,
        "underline_width": 0.05,
        "use_effect_default_color": True,
        "words": {"end_time": [], "start_time": [], "text": []},
    }


def _make_text_segment(seg_id: str, material_id: str,
                        start_us: int, duration_us: int) -> dict:
    """텍스트 트랙 세그먼트"""
    return {
        "caption_info": None,
        "cartoon": False,
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.75},  # 하단 배치
        },
        "common_keyframes": [],
        "enable_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_wheels": True,
        "enable_hsl": False,
        "enable_lut": True,
        "enable_video_mask": True,
        "extra_material_refs": [],
        "group_id": "",
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "id": seg_id,
        "intensifies_audio": False,
        "is_placeholder": False,
        "keyframe_refs": [],
        "material_id": material_id,
        "render_index": 14000,
        "reverse": False,
        "source_timerange": {"duration": duration_us, "start": 0},
        "speed": 1.0,
        "target_timerange": {"duration": duration_us, "start": start_us},
        "track_attribute": 0,
        "track_render_index": 0,
        "uniform_scale": {"on": True, "value": 1.0},
        "visible": True,
        "volume": 1.0,
    }


class CapCutDraftGenerator:
    """CapCut 드래프트 프로젝트 자동 생성"""

    def __init__(self, project_name: str = "Auto Generated"):
        self.project_name = project_name
        self.draft_id = _uuid()
        self.timeline_id = _uuid()

    def generate(
        self,
        image_paths: list,
        durations: list,
        audio_path: str,
        srt_path: str = None,
        output_name: str = None,
    ) -> str:
        """
        CapCut 드래프트 프로젝트 생성

        Args:
            image_paths: 씬별 이미지 파일 경로 리스트
            durations: 씬별 표시 시간(초) 리스트
            audio_path: 나레이션 MP3 경로
            srt_path: SRT 자막 파일 경로 (선택)
            output_name: 프로젝트 폴더명 (기본: Auto_YYYYMMDD)

        Returns:
            생성된 프로젝트 폴더 경로
        """
        if not CAPCUT_DRAFTS_DIR.exists():
            raise FileNotFoundError(
                f"CapCut 드래프트 폴더를 찾을 수 없습니다: {CAPCUT_DRAFTS_DIR}\n"
                "CapCut 데스크톱이 설치되어 있는지 확인하세요."
            )

        # 프로젝트 폴더 생성
        if not output_name:
            from datetime import datetime
            output_name = f"Auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        project_dir = CAPCUT_DRAFTS_DIR / output_name
        timeline_dir = project_dir / "Timelines" / self.timeline_id
        timeline_dir.mkdir(parents=True, exist_ok=True)

        # 절대 경로로 변환
        image_paths = [str(Path(p).resolve()) for p in image_paths]
        audio_path = str(Path(audio_path).resolve())

        # 오디오 길이
        audio_info = MP3(audio_path)
        audio_duration_us = int(audio_info.info.length * MICROSECOND)

        # 드래프트 생성
        draft = self._build_draft(image_paths, durations, audio_path,
                                   audio_duration_us, srt_path)

        # 저장 — 루트와 Timelines 양쪽 모두에 동일한 내용 저장
        draft_json_str = json.dumps(draft, ensure_ascii=False)

        # Timelines 하위 (백업)
        draft_path = timeline_dir / "draft_content.json"
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft_json_str)

        # 루트 draft_content.json (CapCut이 실제로 로드하는 파일)
        root_draft = project_dir / "draft_content.json"
        with open(root_draft, "w", encoding="utf-8") as f:
            f.write(draft_json_str)

        # draft_meta_info.json — 실제 CapCut 형식에 맞춤
        import time as _time
        now_us = int(_time.time() * 1_000_000)  # 마이크로초
        total_duration_us = int(sum(durations) * MICROSECOND)

        # 소재 목록 (draft_materials)
        draft_mats = []
        for img_path in image_paths:
            draft_mats.append({
                "type": 0,
                "value": [{
                    "create_time": int(_time.time()),
                    "duration": 5000000,
                    "extra_info": "",
                    "file_Path": str(Path(img_path).resolve()).replace("\\", "/"),
                    "height": 1080,
                    "id": _uuid(),
                    "import_time": int(_time.time()),
                    "import_time_ms": now_us,
                    "item_source": 1,
                    "md5": "",
                    "metetype": "photo",
                    "roughcut_time_range": {"duration": -1, "start": -1},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": 1920,
                }]
            })

        meta = {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "cloud_package_completed_time": "",
            "draft_cloud_capcut_purchase_info": "",
            "draft_cloud_last_action_download": False,
            "draft_cloud_package_type": "",
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": "draft_cover.jpg",
            "draft_deeplink_url": "",
            "draft_enterprise_info": {
                "draft_enterprise_extra": "",
                "draft_enterprise_id": "",
                "draft_enterprise_name": "",
                "enterprise_material_obfuscate": False,
            },
            "draft_fold_path": str(project_dir).replace("\\", "/"),
            "draft_id": self.draft_id,
            "draft_is_ae_produce": False,
            "draft_is_ai_packaging_used": False,
            "draft_is_ai_shorts": False,
            "draft_is_ai_translate": False,
            "draft_is_article_video_draft": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_from_deeplink": "false",
            "draft_is_invisible": False,
            "draft_is_web_article_video": False,
            "draft_materials": draft_mats,
            "draft_materials_copied_info": [],
            "draft_name": output_name or self.project_name,
            "draft_need_rename_folder": False,
            "draft_new_version": "",
            "draft_removable_storage_device": "",
            "draft_root_path": str(CAPCUT_DRAFTS_DIR).replace("\\", "/"),
            "draft_segment_extra_info": [],
            "draft_timeline_materials_size_": 0,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": total_duration_us,
        }
        meta_path = project_dir / "draft_meta_info.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # root_meta_info.json에 프로젝트 등록 (CapCut 프로젝트 목록에 표시)
        self._register_in_root_meta(project_dir, output_name or self.project_name,
                                     now_us, total_duration_us, image_paths, audio_path)

        logger.info(f"CapCut 드래프트 생성 완료: {project_dir}")
        logger.info(f"  CapCut을 재시작하면 프로젝트가 나타납니다")
        return str(project_dir)

    def _register_in_root_meta(self, project_dir, draft_name,
                                now_us, duration_us, image_paths, audio_path):
        """root_meta_info.json에 프로젝트를 등록하여 CapCut 목록에 표시"""
        root_meta_path = CAPCUT_DRAFTS_DIR / "root_meta_info.json"
        if not root_meta_path.exists():
            logger.warning("root_meta_info.json이 없습니다. CapCut을 한 번 실행해주세요.")
            return

        with open(root_meta_path, "r", encoding="utf-8") as f:
            root = json.load(f)

        # 이미 등록되어 있으면 업데이트, 아니면 추가
        fold_path = str(project_dir).replace("\\", "/")
        existing = None
        for i, item in enumerate(root.get("all_draft_store", [])):
            if item.get("draft_fold_path") == fold_path:
                existing = i
                break

        # 소재 총 크기
        total_size = sum(os.path.getsize(p) for p in image_paths if os.path.exists(p))
        if os.path.exists(audio_path):
            total_size += os.path.getsize(audio_path)

        entry = {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": f"{fold_path}/draft_cover.jpg",
            "draft_fold_path": fold_path,
            "draft_id": self.draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_invisible": False,
            "draft_is_web_article_video": False,
            "draft_json_file": f"{fold_path}/draft_content.json",
            "draft_name": draft_name,
            "draft_new_version": "",
            "draft_root_path": str(CAPCUT_DRAFTS_DIR).replace("\\", "/"),
            "draft_timeline_materials_size": total_size,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": duration_us,
        }

        if existing is not None:
            root["all_draft_store"][existing] = entry
        else:
            root["all_draft_store"].append(entry)

        # draft_ids에도 추가 (리스트가 아닌 경우 무시)
        draft_ids = root.get("draft_ids", [])
        if isinstance(draft_ids, list) and self.draft_id not in draft_ids:
            draft_ids.append(self.draft_id)
            root["draft_ids"] = draft_ids

        with open(root_meta_path, "w", encoding="utf-8") as f:
            json.dump(root, f, ensure_ascii=False, indent=2)

        logger.debug("root_meta_info.json에 프로젝트 등록 완료")

    def _build_draft(self, image_paths, durations, audio_path,
                      audio_duration_us, srt_path) -> dict:
        """draft_content.json 구성"""

        video_segments = []
        video_materials = []
        audio_materials = []
        speeds = []
        canvases = []
        sound_mappings = []
        vocal_seps = []
        material_animations = []
        material_colors = []
        placeholder_infos = []

        current_time_us = 0

        # === 비디오 트랙: 이미지 슬라이드쇼 ===
        for i, (img_path, dur) in enumerate(zip(image_paths, durations)):
            duration_us = int(dur * MICROSECOND)

            # 이미지 크기
            try:
                img = Image.open(img_path)
                w, h = img.size
            except Exception:
                w, h = 1920, 1080

            mat_id = _uuid()
            speed_id = _uuid()
            canvas_id = _uuid()
            scm_id = _uuid()
            vs_id = _uuid()
            ma_id = _uuid()
            mc_id = _uuid()
            seg_id = _uuid()

            extra_refs = [speed_id, canvas_id, scm_id, vs_id, ma_id, mc_id]

            video_materials.append(
                _make_video_material(mat_id, img_path, w, h, duration_us)
            )
            speeds.append(_make_speed(speed_id))
            canvases.append(_make_canvas(canvas_id))
            sound_mappings.append(_make_sound_channel_mapping(scm_id))
            vocal_seps.append(_make_vocal_separation(vs_id))
            material_animations.append(_make_material_animation(ma_id))
            material_colors.append(_make_material_color(mc_id))
            placeholder_infos.append({"id": _uuid(), "type": "placeholder"})

            video_segments.append(
                _make_video_segment(seg_id, mat_id, current_time_us,
                                     duration_us, extra_refs)
            )

            current_time_us += duration_us

        total_duration_us = current_time_us

        # === 오디오 트랙: 나레이션 ===
        audio_mat_id = _uuid()
        audio_speed_id = _uuid()
        audio_scm_id = _uuid()
        audio_vs_id = _uuid()
        audio_seg_id = _uuid()

        audio_extra = [audio_speed_id, audio_scm_id, audio_vs_id]

        audio_materials.append(
            _make_audio_material(audio_mat_id, audio_path, audio_duration_us)
        )
        speeds.append(_make_speed(audio_speed_id))
        sound_mappings.append(_make_sound_channel_mapping(audio_scm_id))
        vocal_seps.append(_make_vocal_separation(audio_vs_id))
        placeholder_infos.append({"id": _uuid(), "type": "placeholder"})

        audio_segments = [
            _make_audio_segment(audio_seg_id, audio_mat_id, 0,
                                 audio_duration_us, audio_extra)
        ]

        # === 자막(텍스트) 트랙: SRT에서 생성 ===
        text_materials = []
        text_segments = []

        if srt_path and Path(srt_path).exists():
            srt_content = Path(srt_path).read_text(encoding="utf-8-sig")
            try:
                subs = list(srt_lib.parse(srt_content))
            except Exception:
                subs = []

            for sub in subs:
                text_mat_id = _uuid()
                text_seg_id = _uuid()
                sub_start_us = int(sub.start.total_seconds() * MICROSECOND)
                sub_dur_us = int((sub.end - sub.start).total_seconds() * MICROSECOND)
                if sub_dur_us <= 0:
                    sub_dur_us = 500000  # 최소 0.5초

                text_materials.append(
                    _make_text_material(text_mat_id, sub.content)
                )
                text_segments.append(
                    _make_text_segment(text_seg_id, text_mat_id,
                                       sub_start_us, sub_dur_us)
                )

            logger.info(f"  CapCut 자막 {len(text_segments)}개 추가")

        # === 트랙 구성 ===
        tracks = [
            {"attribute": 0, "flag": 0, "id": _uuid(),
             "is_default_name": True, "name": "", "segments": video_segments,
             "type": "video"},
            {"attribute": 0, "flag": 0, "id": _uuid(),
             "is_default_name": True, "name": "", "segments": audio_segments,
             "type": "audio"},
        ]
        if text_segments:
            tracks.append(
                {"attribute": 0, "flag": 0, "id": _uuid(),
                 "is_default_name": True, "name": "", "segments": text_segments,
                 "type": "text"}
            )

        # === materials 구성 ===
        materials = {
            "ai_translates": [],
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_pannings": [],
            "audio_pitch_shifts": [],
            "audio_track_indexes": [],
            "audios": audio_materials,
            "beats": audio_materials.copy(),
            "canvases": canvases,
            "chromas": [],
            "color_curves": [],
            "common_mask": [],
            "digital_humans": [],
            "drafts": [],
            "effects": [],
            "flowers": [],
            "green_screens": [],
            "handwrites": [],
            "hsl": [],
            "hsl_curves": [],
            "images": [],
            "log_color_wheels": [],
            "loudnesses": [],
            "manual_beautys": [],
            "manual_deformations": [],
            "material_animations": material_animations,
            "material_colors": material_colors,
            "multi_language_refs": [],
            "placeholder_infos": placeholder_infos,
            "placeholders": [],
            "plugin_effects": [],
            "primary_color_wheels": [],
            "realtime_denoises": [],
            "shapes": [],
            "smart_crops": [],
            "smart_relights": [],
            "sound_channel_mappings": sound_mappings,
            "speeds": speeds,
            "stickers": [],
            "tail_leaders": [],
            "text_templates": [],
            "texts": text_materials,
            "time_marks": [],
            "transitions": [],
            "video_effects": [],
            "video_radius": [],
            "video_shadows": [],
            "video_strokes": [],
            "video_trackings": [],
            "videos": video_materials,
            "vocal_beautifys": [],
            "vocal_separations": vocal_seps,
        }

        # === 최종 드래프트 ===
        return {
            "canvas_config": {
                "background": None,
                "height": 1080,
                "ratio": "original",
                "width": 1920,
            },
            "color_space": 0,
            "config": {"adjust_max_index": 1, "attachment_info": [],
                       "export_range": None, "extract_audio_last_index": 1,
                       "lyrics_recognition_id": "", "lyrics_sync": False,
                       "lyrics_taskinfo": [], "maintrack_adsorb": True,
                       "material_save_mode": 0, "multi_language_current": "none",
                       "multi_language_list": [],
                       "multi_language_main": "none",
                       "multi_language_mode": "none",
                       "original_sound_last_index": 2,
                       "record_audio_last_index": 1,
                       "sticker_max_index": 1, "subtitle_keywords_config": None,
                       "subtitle_recognition_id": "",
                       "subtitle_sync": True, "subtitle_taskinfo": [],
                       "system_font_list": [], "text_max_index": 1,
                       "video_mute": False, "zoom_info_params": None},
            "cover": None,
            "create_time": 0,
            "draft_type": "video",
            "duration": max(total_duration_us, audio_duration_us),
            "extra_info": None,
            "fps": 30.0,
            "free_render_index_mode_on": False,
            "id": self.timeline_id,
            "keyframe_graph_list": [],
            "keyframes": {"adjusts": [], "audios": [], "effects": [],
                          "filters": [], "handwrites": [], "stickers": [],
                          "texts": [], "videos": []},
            "last_modified_platform": {
                "app_id": 3704, "app_source": "cc",
                "app_version": "6.0.0", "device_id": "",
                "hard_disk_id": "", "mac_address": "",
                "os": "windows", "os_version": "10.0"},
            "materials": materials,
            "mutable_config": None,
            "name": "",
            "new_version": "159.0.0",
            "path": "",
            "platform": {
                "app_id": 3704, "app_source": "cc",
                "app_version": "6.0.0", "device_id": "",
                "hard_disk_id": "", "mac_address": "",
                "os": "windows", "os_version": "10.0"},
            "relationships": [],
            "render_index_track_mode_on": True,
            "source": "default",
            "static_cover_image_path": "",
            "tracks": tracks,
            "update_time": 0,
            "version": 360000,
        }
