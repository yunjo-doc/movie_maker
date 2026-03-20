# 영상자동화 코드 변경 이력 (CHANGELOG)

## 2026-03-18 — 초기 개발 + 디버깅

### 1. 프로젝트 인프라
- `config.py`: pydantic-settings → **dotenv 직접 로드**로 변경 (한글 경로에서 pydantic-settings가 .env를 못 읽는 문제)
- `config.py`: `pixabay_api_key` property 누락 → 추가
- `requirements.txt`: pip install 시 한글 경로 인코딩 오류 → **직접 pip install 명령어로 설치**

### 2. 대본 생성 (step1_script.py)
- **JSON 파싱 실패 문제**: Claude가 긴 대본을 하나의 JSON으로 생성하면 구조가 깨짐
- **해결**: 하나의 거대 JSON 대신 **챕터별 개별 API 호출**로 분리
  - 제목/요약 1회 + 챕터별 1회씩 = 총 6회 호출
  - 각 응답이 작은 JSON이므로 파싱 안정적
- JSON 추출 시 마크다운 코드블록(```json) 처리 추가
- 정규식 기반 3차 JSON 파싱 폴백 추가

### 3. TTS + SRT 생성 (step2_tts.py)
- **Edge TTS 하드코딩 문제**: config.yaml의 `primary` 설정을 무시하고 항상 Edge TTS 사용
- **해결**: `config["tts"]["primary"]` 값에 따라 엔진 선택하는 `_run_tts()` 메서드로 리팩토링
- ElevenLabs / Edge TTS 양방향 폴백 지원

### 4. Edge TTS Provider (edge_tts_provider.py)
- **SubMaker API 변경 (v7.x)**: `create_sub()` → `feed()`, `generate_subs()` → `get_srt()`
- **WordBoundary 이벤트 제거**: v7.x에서 `WordBoundary` 대신 `SentenceBoundary`만 전송
- **해결**: SubMaker 의존 제거, `SentenceBoundary` 이벤트에서 직접 srt.Subtitle 생성
- 타임스탬프 단위: 100나노초(ticks) → 초 변환 (`TICKS_PER_SEC = 10_000_000`)
- 긴 문장 분할: `_split_long_sentence()` — **어절(띄어쓰기) 단위로만 분할**, 단어 중간 절대 자르지 않음
- 사용자 추가: `LEAD_IN_MS = 500` (시작 무음), `CHAPTER_GAP_MS = 300` (챕터 간 무음)

### 5. ElevenLabs Provider (elevenlabs_provider.py)
- **자막 단어 잘림 문제**: alignment의 글자별 타임스탬프에서 max_chars로 자르면 단어 중간에서 잘림
- **1차 수정**: 어절 단위로 그룹핑 후 max_chars 이내로 묶기
- **2차 수정 (최종)**: **원본 텍스트의 문장 구조를 기준으로 자막 생성**
  - 원본 텍스트를 문장부호(`.!?。`)에서 먼저 분리
  - 긴 문장만 어절 단위로 추가 분할
  - alignment 타이밍은 글자 위치 매핑으로만 사용
  - `original_text` 파라미터 추가하여 원본 텍스트 전달
- 사용자 추가: `LEAD_IN_MS = 500`, `CHAPTER_GAP_MS = 300`

### 6. 이미지 생성 (gemini_provider.py + config.yaml)
- **Gemini 모델 변경**: `gemini-2.0-flash-exp` → `gemini-2.5-flash-image` → **`imagen-4.0-generate-001`**
  - `gemini-2.0-flash-exp`: 404 NOT_FOUND (삭제됨)
  - `gemini-2.5-flash-image`: 작동하지만 정방형(1024x1024)만 생성
  - `imagen-4.0-generate-001`: **16:9 (1408x768) 지원**, `aspect_ratio` 파라미터 직접 지정
- **Provider 이중 구조**: Imagen 모델은 `generate_images()` API, Gemini 모델은 `generate_content()` API 사용
- 프롬프트에 `"Generate a wide landscape image in 16:9 aspect ratio"` 접두사 추가 (Gemini Flash용)

### 7. 스타일 일관성 (config.yaml + step3_storyboard.py)
- `config.yaml`에 스타일 프리셋 시스템 추가:
  - `style_preset`: 프리셋 이름
  - `style_description`: 한국어 설명 (Claude에게 전달)
  - `style_suffix`: 영어 접미사 (Imagen에 추가)
  - `character_sheet`: 고정 캐릭터 묘사 (선택)
- `step3_storyboard.py`: Claude에게 `style_description` + `character_sheet` 전달하여 일관된 프롬프트 생성

### 8. 스토리보드 챕터별 생성 (step3_storyboard.py)
- **이미지-내용 불일치 문제**: 전체 대본을 한번에 보내면 Claude가 씬 순서를 뒤바꿈
- **해결**: **챕터별 개별 씬 생성** (`_generate_for_chapter()`)
  - 각 챕터의 대본 텍스트만 전달 → 해당 내용에 맞는 3~5개 씬만 생성
  - 다른 챕터 내용 혼입 방지
  - 전체 씬 → duration 합계를 오디오 길이에 맞춤

### 9. FFmpeg 영상 합성 (ffmpeg_composer.py)
- **Windows 한글 경로 문제**: subtitles 필터에서 한글/콜론 경로 실패
- **1차 시도**: 슬래시 변환 + 콜론 이스케이프 → 실패
- **2차 시도**: 영문 임시 디렉토리에서 상대 경로 사용 → 실패 (FFmpeg가 cwd의 상대경로를 못 찾음)
- **최종 해결**: `cwd=work_dir`로 FFmpeg 실행 + 파일명만 전달 (절대 경로 없이)
- **빈 SRT 처리**: 자막 파일이 비어있으면 `_final_compose_no_subs()` 호출 (자막 없이 합성)
- SRT 인코딩: `utf-8-sig` (BOM 포함) 필수

### 10. 체크포인트 (checkpoint.py)
- **완료 단계 누적 안 되는 버그**: `asdict(ctx)`에 `_completed_steps`가 없어서 매번 빈 리스트로 리셋
- **해결**: `self._completed_steps` 인스턴스 변수로 메모리에 누적 관리, `load()` 시 복원

### 11. CapCut 드래프트 자동 생성 (capcut_draft.py)
- **신규 기능**: 이미지 + 오디오 + 자막 → CapCut 프로젝트 JSON 자동 생성
- **프로젝트 인식 문제**: CapCut에서 프로젝트가 안 보임
  - 원인: `draft_meta_info.json`의 타임스탬프가 초 단위 (CapCut은 마이크로초 필요)
  - 해결: `tm_draft_create`, `tm_draft_modified`를 마이크로초로 변경
- **프로젝트 열리지 않는 문제**:
  - 원인: 루트 `draft_content.json`이 빈 파일 (CapCut은 루트 파일을 직접 로드)
  - 해결: 루트와 Timelines 양쪽에 동일한 draft_content.json 저장
- **root_meta_info.json 자동 등록**: `_register_in_root_meta()` 메서드 추가
  - CapCut 재시작 시 프로젝트 목록에 자동 표시
  - `draft_ids` 타입 검사 (int일 수 있음)
- **자막 트랙 추가**: `_make_text_material()`, `_make_text_segment()` 함수 추가
  - SRT 파싱 → 텍스트 material + segment 생성 → text 트랙에 배치
- **자막 content 형식**: 리치텍스트 JSON 구조 → **단순 텍스트**로 변경 (JSON 전체가 화면에 표시되는 문제)
- **자막 크기**: `font_size: 8.0` 유지 (CapCut에서 한번 클릭하면 정상 적용됨)

### 12. CLI (cli.py)
- `--capcut` 옵션 추가: CapCut 드래프트 동시 생성
- `GenerateCapCutDraftStep` import 추가
- steps 배열에서 capcut → thumbnail → metadata → upload 순서

### 13. TTS 음성 변경
- **기본 엔진**: Edge TTS → **ElevenLabs** (`config.yaml: primary: "elevenlabs"`)
- **음성**: `SangHo` (상호, `OEaq3WGNtNvFJ5co9mJE`) — 남성, 내레이션/스토리
- **ElevenLabs API 키**: `.env` 파일의 키 교체 (권한 문제 해결)

### 14. 기존 영상 수정
- 시작 끊김: FFmpeg로 기존 MP4 앞에 500ms 무음 추가
- 자막 재생성: 원본 대본에서 문장/어절 단위로 SRT 재생성 후 FFmpeg로 재합성
- 이중 자막 문제: 하드코딩된 자막 위에 덮어씌움 → **이미지+오디오로 처음부터 재합성**으로 해결
