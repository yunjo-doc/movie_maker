# PRD: 유튜브 롱폼 영상 자동화 시스템

## 1. 개요

### 1.1 프로젝트명
**유튜브 롱폼 영상 자동화 시스템 (YouTube Long-form Video Automation System)**

### 1.2 목적
키워드(문장) 하나를 입력하면 AI를 활용하여 유튜브 롱폼 영상을 자동으로 생성하고 업로드까지 완료하는 엔드투엔드 자동화 파이프라인을 구축한다.

### 1.3 목표
- 하루 4개의 롱폼 영상(10분 내외) 자동 생성
- 전체 파이프라인 E2E 성공률 95% 이상 (폴백 + 체크포인트 재개 포함)
- 영상 1개당 제작 비용 $0.3 이하 (Edge TTS 기준)
- 월 운영 비용 $15~35 범위 (무료 TTS) / $114~134 (프리미엄 TTS)

### 1.4 성공률 95% 달성 전제조건
> **중요**: 단일 경로만으로는 E2E 성공률이 55~60%에 불과하다.
> 95%를 달성하려면 다음 4가지 전략이 **모두** 구현되어야 한다.
>
> 1. **폴백(Fallback)**: 각 단계마다 대안 경로 준비
> 2. **체크포인트(Checkpoint)**: 단계별 중간 결과 저장, 실패 시 해당 단계부터 재개
> 3. **이중화(Redundancy)**: TTS, 이미지 생성 등 핵심 단계에 2개 이상 엔진 준비
> 4. **경로 안전(Path Safety)**: 영문 임시 디렉토리에서 작업하여 한글 경로 문제 회피

### 1.4 참고 영상
- **채널**: 뉴머니 (@newmoney_story)
- **영상**: "이게 진짜 자동화입니다." 문장하나 넣고 롱폼 4개씩 뽑아서 하루 50만원 버는 방법
- **URL**: https://youtu.be/YAjjNWLcl10

---

## 2. 시스템 아키텍처

### 2.1 전체 파이프라인

```
키워드 입력
  │
  ▼
[1단계] 벤치마킹 & 주제 선정 (수동/반자동)
  │
  ▼
[2단계] AI 대본 생성 (Claude API) ──────────────── 단독 95% → 재시도 포함 99%
  │
  ▼
[3단계] 음성(TTS) + 자막(SRT) 생성 ─────────────── 단독 90% → 이중화 포함 99%
  │    기본: Edge TTS (무료)
  │    폴백: ElevenLabs API (유료)
  │
  ▼
[4단계] 스토리보드 & 이미지 프롬프트 (Claude API) ── 단독 95% → 재시도 포함 99%
  │
  ▼
[5단계] AI 이미지/비디오 생성 (Gemini API) ──────── 단독 21%* → 폴백 포함 97%
  │    기본: Gemini API 이미지 생성
  │    폴백1: 프롬프트 수정 후 재시도 (3회)
  │    폴백2: Pexels/Pixabay 스톡 이미지 대체
  │    폴백3: 이전 씬 이미지 재사용 + 효과 변경
  │    * 15장 전체 성공 = 0.9^15 = 21% (개별 90%)
  │
  ▼
[6단계] 영상 합성 (FFmpeg) ─────────────────────── 단독 93% → 경로 안전 포함 97%
  │    영문 임시 디렉토리에서 작업 (한글 경로 회피)
  │  └─ 유튜브 메타데이터 생성 (Claude API) ──────── 99%
  │
  ▼
[7단계] 썸네일 생성 (Pillow) ───────────────────── 99%
  │
  ▼
[8단계] 유튜브 업로드 (YouTube Data API v3) ──────── 단독 90% → 토큰 관리 포함 95%
  │    OAuth 토큰 자동 갱신 + 프로덕션 앱 심사 통과

─── 전체 E2E 성공률 ───
단일 경로만: 55~60%
폴백 전략 적용: 75~80%
폴백 + 체크포인트 재개: 90~93%
폴백 + 체크포인트 + 이중화 + 경로 안전: 95%+
```

### 2.2 기술 스택

```
┌──────────────────────────────────────────────────────┐
│               영상 자동화 파이프라인                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│  [Python 메인 스크립트]                                │
│    │                                                 │
│    ├─ Claude API ──→ 대본 + 스토리보드 + 메타데이터     │
│    │                                                 │
│    ├─ Edge TTS (기본,무료) ──→ MP3 + VTT/SRT          │
│    │  └─ ElevenLabs API (폴백,유료) ──→ MP3 + SRT     │
│    │                                                 │
│    ├─ Gemini API ──→ AI 이미지 (+ Kling/Runway I2V)   │
│    │                                                 │
│    ├─ FFmpeg ──→ 최종 MP4 영상 합성                    │
│    │                                                 │
│    ├─ Pillow ──→ 썸네일 JPG (1280x720)               │
│    │                                                 │
│    └─ YouTube Data API v3 ──→ 업로드 + 메타 설정       │
│                                                      │
│  [선택: n8n 오케스트레이션]                              │
│    - 스케줄 실행, 에러 핸들링, 알림                      │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 3. 기능 요구사항 (Functional Requirements)

### 3.1 [1단계] 벤치마킹 & 주제 선정

| 항목 | 내용 |
|------|------|
| **유형** | 수동/반자동 |
| **설명** | 해외 유사 채널에서 조회수 높은 검증된 콘텐츠를 발굴 |
| **도구** | 유벤치(ubench.kr), VidIQ, 또는 수동 리서치 |
| **입력** | 없음 (크리에이터가 직접 수행) |
| **출력** | 주제 키워드 또는 참고 영상 URL |
| **자동화 수준** | 낮음 (향후 자동화 가능) |

### 3.2 [2단계] AI 대본 생성

| 항목 | 내용 |
|------|------|
| **API** | Anthropic Claude API (`claude-sonnet-4-20250514`) |
| **입력** | 주제 키워드 또는 참고 영상 스크립트 |
| **출력** | 5개 챕터 구조의 대본 (JSON 형식) |
| **대본 규격** | 챕터당 2,000~3,000자, 총 10,000~15,000자 |
| **스타일** | 감정적, 문학적 표현. 스토리텔링 형식 |
| **성공률** | 98% |

#### 출력 JSON 형식
```json
{
  "title": "영상 제목",
  "chapters": [
    {
      "chapter_number": 1,
      "chapter_title": "챕터 제목",
      "script": "나레이션 대본 텍스트...",
      "duration_estimate": "2분"
    }
  ],
  "total_estimated_duration": "10분"
}
```

#### 에러 처리
- JSON 파싱 실패 시: 최대 3회 재시도
- API 타임아웃: 30초 타임아웃, 지수 백오프 재시도

### 3.3 [3단계] 음성(TTS) + 자막(SRT) 생성 — 이중화 구조

| 항목 | 기본 (Edge TTS) | 폴백 (ElevenLabs) |
|------|----------------|-------------------|
| **비용** | **무료** | $22~99/월 |
| **한국어 품질** | 7~8/10 (충분) | 8~9/10 (최상) |
| **API 안정성** | ⚠️ 비공식 (MS 차단 가능) | ✅ 공식 API |
| **자막 생성** | SubMaker → VTT → SRT | with-timestamps → SRT |
| **감정 표현** | 제한적 | 풍부 |
| **텍스트 제한** | 사실상 없음 | 5,000자/요청 |

> **전략**: 기본으로 Edge TTS(무료)를 사용하고, 실패 시 ElevenLabs로 폴백.
> 이 이중화로 TTS 단계 성공률을 90% → 99%로 끌어올린다.

#### 기본 엔진: Edge TTS (무료)

```python
import edge_tts

communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural", rate="+5%")
submaker = edge_tts.SubMaker()
async for chunk in communicate.stream():
    if chunk["type"] == "audio":
        audio_file.write(chunk["data"])
    elif chunk["type"] == "WordBoundary":
        submaker.create_sub((chunk["offset"], chunk["duration"]), chunk["text"])
# VTT 자막 → SRT 변환 필요
```

**Edge TTS 한국어 음성 추천:**
| 음성 ID | 성별 | 추천 용도 |
|---------|------|----------|
| `ko-KR-SunHiNeural` | 여성 | 내레이션, 뉴스 (가장 추천) |
| `ko-KR-InJoonNeural` | 남성 | 다큐멘터리, 설명 |
| `ko-KR-BongJinNeural` | 남성 | 역사, 스토리텔링 |

#### 폴백 엔진: ElevenLabs (유료)

- 엔드포인트: `POST /v1/text-to-speech/{voice_id}/with-timestamps`
- 모델: `eleven_multilingual_v2` (한국어 필수)
- 응답: `audio_base64` (MP3) + `alignment` (문자별 타임스탬프)
- 텍스트 제한: 5,000자/요청 → 챕터별 분할 처리

#### 이중화 폴백 로직

```python
async def generate_tts(text, audio_path, srt_path):
    try:
        # 1차: Edge TTS (무료)
        await edge_tts_generate(text, audio_path, srt_path)
    except Exception:
        # 2차: ElevenLabs (유료 폴백)
        elevenlabs_generate(text, audio_path, srt_path)
```

#### ⚠️ Edge TTS 리스크 경고

| 리스크 | 상세 |
|--------|------|
| **비공식 API** | Microsoft가 언제든 차단 가능. SLA 없음 |
| **상업적 사용** | MS 이용약관 확인 필요 |
| **한국어 어절 분리** | WordBoundary가 부정확할 수 있음 → `words_in_cue=5` 설정으로 보완 |

→ Edge TTS가 장기적으로 차단될 경우 ElevenLabs 또는 Google Cloud TTS로 전환 계획 필요

#### 비용 비교

| 시나리오 | Edge TTS (기본) | ElevenLabs (폴백) |
|---------|----------------|-------------------|
| 월 120개 영상 (10분씩) | **$0** | $99/월 (Pro) |
| 연간 비용 | **$0** | $1,188 |

#### 에러 처리
- Edge TTS 실패 → ElevenLabs 폴백
- ElevenLabs 429 (Rate Limit) → 딜레이 후 재시도 (tenacity)
- 발음 오류 → 텍스트 전처리 (숫자→한글, 약어→풀어쓰기)
- SRT 인코딩 → `utf-8-sig` (BOM 포함) 필수 (한글 깨짐 방지)

### 3.4 [4단계] 스토리보드 & 이미지 프롬프트 생성

| 항목 | 내용 |
|------|------|
| **API** | Claude API |
| **입력** | 대본 (2단계 출력) + SRT 타임스탬프 (3단계 출력) |
| **출력** | 씬 구조 + 이미지 프롬프트 목록 (JSON) |
| **성공률** | 98% |

#### 출력 JSON 형식
```json
{
  "scenes": [
    {
      "scene_number": 1,
      "time_start": "00:00:00",
      "time_end": "00:00:25",
      "description": "씬 설명",
      "image_prompt": "영어 이미지 프롬프트 (Gemini용)",
      "style_keywords": "cinematic, warm lighting, korean setting",
      "motion": "zoom_in"
    }
  ]
}
```

#### 프롬프트 전략
- 캐릭터 일관성을 위한 **캐릭터 시트** 프롬프트 고정
- 모든 프롬프트에 동일한 스타일 접미사 추가
- 한국어 설명 → 영어 프롬프트 변환 (Gemini 이미지 생성 품질 향상)

### 3.5 [5단계] AI 이미지/비디오 생성

| 항목 | 내용 |
|------|------|
| **이미지 생성** | Google Gemini API (`gemini-2.0-flash-exp` 또는 `imagen-3.0`) |
| **비디오 생성** | Kling AI / Runway Gen-3 API (선택) |
| **입력** | 이미지 프롬프트 목록 (4단계 출력) |
| **출력** | 장면별 이미지 파일 (PNG/JPG) + 비디오 클립 (MP4, 선택) |
| **단일 이미지 성공률** | 90% |
| **15장 배치 전체 성공률** | ⚠️ 0.9^15 = **21%** (폴백 없이) |
| **폴백 적용 후 배치 성공률** | **97%** |

#### ⚠️ 핵심 리스크: 배치 이미지 성공률 계산

15장 모두 성공해야 영상 제작이 가능하므로, 개별 90% 성공률이라도
배치 전체 성공률은 0.9^15 = **21%** 로 급격히 하락한다.
이를 해결하기 위해 **3단계 폴백 전략이 필수**이다.

#### 이미지 생성 3단계 폴백 전략

```
시도 1: Gemini API로 이미지 생성
  ↓ 실패 시
시도 2: 프롬프트 수정(단순화) 후 재시도 (최대 3회)
  ↓ 여전히 실패 시
시도 3: Pexels/Pixabay API로 키워드 기반 스톡 이미지 대체
  ↓ 여전히 실패 시
시도 4: 이전 씬 이미지 재사용 + Ken Burns 효과 변경
```

이 폴백 체인을 적용하면 개별 이미지 실패 확률은 사실상 0%에 근접하여
배치 성공률이 **97%+** 로 상승한다.

#### 폴백 코드 구조
```python
async def generate_image_with_fallback(scene, output_path):
    # 1차: Gemini API
    for attempt in range(3):
        try:
            return await gemini_generate(scene["prompt_en"], output_path)
        except Exception:
            scene["prompt_en"] = simplify_prompt(scene["prompt_en"])

    # 2차: 스톡 이미지 (Pexels)
    try:
        keyword = extract_keyword(scene["prompt_en"])
        return await pexels_search(keyword, output_path)
    except Exception:
        pass

    # 3차: 이전 씬 이미지 재사용
    return reuse_previous_image(scene, output_path)
```

#### 스톡 이미지 폴백용 API 키 (무료)

| 서비스 | API 키 발급 | 월 제한 |
|--------|-----------|--------|
| **Pexels** | https://www.pexels.com/api/ | 200 요청/시간 |
| **Pixabay** | https://pixabay.com/api/docs/ | 5,000 요청/시간 |

#### 이미지 생성 (Gemini API)

```python
# Gemini 2.0 Flash 이미지 생성
from google import genai

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.0-flash-exp",
    contents=image_prompt,
    config=genai.types.GenerateContentConfig(
        response_modalities=["IMAGE", "TEXT"]
    )
)
```

| 설정 | 값 |
|------|-----|
| 해상도 | 최대 1024x1024, 16:9 비율 지원 |
| 한국어 프롬프트 | 완벽 지원 |
| 배치 생성 | API 반복 호출 (분당 15~60 요청) |
| 비용 | 무료 tier + 유료 시 이미지당 $0.02~0.04 |

#### 이미지 일관성 유지 전략
1. **캐릭터 시트 프롬프트**: 외모, 의상, 색상을 상세 기술한 고정 문구
2. **스타일 접미사**: 모든 프롬프트에 동일 스타일 지시어 추가
3. **참조 이미지**: Gemini 대화형 편집으로 기존 이미지 기반 변형
4. **일러스트/만화 스타일 권장**: 실사보다 일관성 유지가 쉬움

#### 비디오 생성 (선택사항)
- **권장 비율**: 이미지 80% + 비디오 클립 20% (하이브리드)
- **Ken Burns 효과**: FFmpeg로 정적 이미지에 줌/팬 동작 적용
- **I2V 도구**: Kling AI (품질 최고) 또는 Runway (API 안정적)

#### 에러 처리
- 콘텐츠 정책 거부 시: 프롬프트 수정 후 재시도
- 품질 불일치: 2~3장 생성 후 최적 선택 로직

### 3.6 [6단계] 영상 합성 + 유튜브 메타데이터 생성

#### 6a. 영상 합성 (FFmpeg)

| 항목 | 내용 |
|------|------|
| **도구** | FFmpeg (CLI) |
| **입력** | 이미지 파일들 + MP3 음성 + SRT 자막 |
| **출력** | 최종 MP4 영상 (1920x1080, H.264) |
| **비용** | 무료 |
| **성공률** | 99% |

##### FFmpeg 합성 명령어
```bash
ffmpeg -y \
  -f concat -safe 0 -i images.txt \
  -i narration.mp3 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,\
       pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,\
       subtitles=subtitles.srt:force_style=\
       'FontName=NanumGothicBold,FontSize=22,\
       PrimaryColour=&HFFFFFF,OutlineColour=&H000000,\
       Outline=2,Alignment=2,MarginV=50'" \
  -c:v libx264 -preset medium \
  -c:a aac -b:a 192k \
  -pix_fmt yuv420p -shortest \
  output.mp4
```

##### images.txt 형식 (FFmpeg concat)
```
file 'scene_01.png'
duration 5
file 'scene_02.png'
duration 8
file 'scene_03.png'
duration 6
```

##### Ken Burns 효과 (줌/팬)
```bash
# 줌인 효과
-vf "zoompan=z='min(zoom+0.0015,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1920x1080"
```

##### 영상 규격
| 항목 | 값 |
|------|-----|
| 해상도 | 1920x1080 (Full HD) |
| 코덱 | H.264 (libx264) |
| 오디오 코덱 | AAC, 192kbps |
| 프레임 | 24fps |
| 자막 | 하드코딩 (burn-in) |

##### ⚠️ Windows 경로 안전 전략 (한글 경로 문제 회피)

FFmpeg의 `subtitles` 필터는 Windows에서 한글 경로, 콜론(`:`) 등으로 인해
자주 실패한다. 이를 근본적으로 해결하기 위해 **영문 임시 디렉토리**에서 작업한다.

```python
import tempfile
# 영문 경로 강제: C:\Users\qwer1234\AppData\Local\Temp\vid_xxxxx
work_dir = tempfile.mkdtemp(prefix="vid_")
# 모든 중간 파일(이미지, 오디오, SRT)을 여기에 복사 후 작업
# 최종 결과물만 원래 output 디렉토리로 이동
```

**추가 주의:**
- SRT 파일은 `utf-8-sig` (BOM 포함 UTF-8)로 저장 → 한글 깨짐 방지
- FFmpeg subtitles 필터 경로: `\\:` 로 콜론 이스케이프 필수
- `fontsdir` 지정하여 한글 폰트 경로를 명시적으로 전달

##### CapCut 대신 FFmpeg를 선택한 이유
| 비교 항목 | CapCut | FFmpeg |
|----------|--------|--------|
| 공식 API | ❌ 없음 | ✅ CLI |
| 안정성 | 낮음 (버전 의존) | 최고 (99%) |
| 자동화 | 비공식 도구만 존재 | 완벽 지원 |
| 비용 | 무료 | 무료 |
| 자막 지원 | - | SRT 직접 지원 |
| 결론 | 수동 편집에만 적합 | **자동화에 최적** |

#### 6b. 유튜브 메타데이터 자동 생성

| 항목 | 내용 |
|------|------|
| **API** | Claude API |
| **입력** | 대본 요약 + 주제 |
| **출력** | 제목, 설명, 태그, 카테고리 (JSON) |
| **성공률** | 98% |

##### 출력 JSON 형식
```json
{
  "title": "SEO 최적화된 제목 (100자 이내)",
  "description": "처음 2줄에 핵심 내용. 챕터 타임스탬프 포함. 해시태그 3-5개. (5000자 이내)",
  "tags": ["메인키워드", "롱테일키워드", "관련키워드"],
  "category_id": "22"
}
```

##### SEO 최적화 규칙
1. 제목: 주요 키워드 앞쪽 배치, 감정적 트리거 단어, 숫자 활용
2. 설명: 처음 150자에 핵심 내용 (검색 미리보기)
3. 태그: 메인 + 롱테일 + 관련 키워드 조합 (총 500자 이내)
4. 한국어 + 영어 키워드 병행

### 3.7 [7단계] 썸네일 생성

| 항목 | 내용 |
|------|------|
| **도구** | Python Pillow 라이브러리 |
| **입력** | AI 생성 배경 이미지 + 영상 제목 |
| **출력** | 1280x720 JPG 파일 (2MB 이하) |
| **비용** | 무료 |
| **성공률** | 99% |

##### 구현 방식
```python
from PIL import Image, ImageDraw, ImageFont

canvas = Image.open("ai_background.jpg").resize((1280, 720))
draw = ImageDraw.Draw(canvas)
font = ImageFont.truetype("NanumGothicExtraBold.ttf", 68)
draw.text((60, 300), "영상 제목",
          font=font, fill='#FFD700',
          stroke_width=4, stroke_fill='black')
canvas.save("thumbnail.jpg", quality=95)
```

##### 고급 디자인 대안: HTML + Playwright
- HTML/CSS로 디자인 → Playwright 스크린샷으로 캡처
- 웹폰트, 그라데이션, 복잡한 레이아웃 지원
- Canva 수준의 디자인 자유도 확보

##### Canva API 대신 Pillow를 선택한 이유
| 비교 항목 | Canva API | Pillow |
|----------|-----------|--------|
| 비용 | Enterprise 전용 (고비용) | 무료 |
| 자동화 | Autofill API (제한적) | 완전 자동화 |
| 디자인 품질 | 높음 | 중~높음 (코드에 의존) |
| 결론 | 비용 대비 비효율 | **개인 프로젝트에 최적** |

### 3.8 [8단계] 유튜브 업로드

| 항목 | 내용 |
|------|------|
| **API** | YouTube Data API v3 |
| **입력** | MP4 영상 + 메타데이터 JSON + 썸네일 JPG |
| **출력** | 업로드된 영상 URL |
| **성공률** | 97% |

#### API 호출
```python
# 영상 업로드
video_id = youtube.videos().insert(
    part="snippet,status",
    body={
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata["category_id"],
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko"
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False
        }
    },
    media_body=MediaFileUpload("output.mp4", resumable=True)
).execute()

# 썸네일 설정
youtube.thumbnails().set(
    videoId=video_id["id"],
    media_body=MediaFileUpload("thumbnail.jpg")
).execute()
```

#### API 할당량

| API 호출 | 비용 (units) |
|----------|-------------|
| videos.insert (업로드) | 1,600 |
| thumbnails.set (썸네일) | 50 |
| videos.update (메타 수정) | 50 |
| **일일 기본 할당량** | **10,000 units** |
| **일일 업로드 가능 횟수** | **약 6회** |

#### 안전 업로드 규칙
1. 항상 `private`으로 먼저 업로드 → 검수 후 `public` 전환
2. 하루 최대 2~3개 권장 (스팸 판정 방지)
3. 업로드 간 30분~1시간 랜덤 간격
4. OAuth 토큰 자동 갱신 로직 필수 (`token.pickle` 활용)

#### ⚠️ OAuth 토큰 관리 리스크

| 리스크 | 상세 | 대응 |
|--------|------|------|
| **테스트 앱 토큰 만료** | "테스트" 상태 앱은 refresh token이 7일 후 만료 | 프로덕션으로 전환 (Google 심사 필요, 수주 소요) |
| **민감한 스코프** | `youtube.upload`는 민감한 스코프로 분류 → 추가 심사 | 앱 심사 문서 사전 준비 |
| **토큰 갱신 실패** | refresh token 무효화 시 수동 재인증 필요 | `Credentials.refresh(Request())` 자동 갱신 로직 + 실패 알림 |

> **프로덕션 앱 심사를 통과하지 않으면 7일마다 수동 재인증이 필요하다.**
> 이 심사가 95% 달성의 전제 조건 중 하나이다.
> 심사 통과 전까지는 업로드 단계를 수동으로 처리하는 것을 권장한다.

#### 사전 준비사항
- Google Cloud Console에서 프로젝트 생성
- YouTube Data API v3 활성화
- OAuth 2.0 클라이언트 ID 생성 (Desktop 앱 유형)
- 채널 전화번호 인증 (커스텀 썸네일 사용 요건)
- **Google OAuth 앱 프로덕션 심사 신청 (수주 소요, 조기 착수 필수)**

---

## 4. 비기능 요구사항 (Non-Functional Requirements)

### 4.1 안정성 & 에러 처리

| 요구사항 | 상세 |
|----------|------|
| 전체 E2E 성공률 | 95% 이상 (폴백 + 체크포인트 + 이중화 필수) |
| API 재시도 | 모든 외부 API 호출에 최대 3회 재시도 + 지수 백오프 (tenacity) |
| JSON 파싱 보호 | LLM 출력 JSON 파싱 실패 시 재요청 |
| 파일 URL 만료 방지 | 생성된 파일은 즉시 로컬 저장 (임시 URL 의존 금지) |
| 타임아웃 | API 호출 30초, 영상 렌더링 10분 |
| 롱폼 분할 처리 | 10분 이상 영상은 챕터별 분할 → concat |
| 경로 안전 | 영문 임시 디렉토리(`tempfile.mkdtemp`)에서 작업 |
| SRT 인코딩 | `utf-8-sig` (BOM 포함) 필수 |

#### 4.1.1 체크포인트/재개 시스템 (필수)

각 단계 완료 시 `checkpoint.json`에 상태를 저장하여, 실패 시 처음부터 다시 실행하지 않고 해당 단계부터 재개한다.

```python
# checkpoint.json 예시
{
  "project_id": "20260318_ai_trend",
  "completed_steps": ["generate_script", "generate_tts", "generate_images"],
  "failed_step": "compose_video",
  "context": { ... }  # 중간 결과물 경로 등
}
```

**재개 명령:**
```bash
python cli.py run "AI 트렌드" -p 20260318_ai_trend --resume
```

체크포인트가 없으면 1회 실패 = 전체 재실행이므로, E2E 성공률이 크게 하락한다.
체크포인트 재개를 적용하면 **2차 시도 포함 실질 성공률이 90~93%** 로 상승한다.

#### 4.1.2 폴백(Fallback) 전략 (필수)

| 단계 | 기본 | 폴백 1 | 폴백 2 |
|------|------|--------|--------|
| TTS | Edge TTS (무료) | ElevenLabs (유료) | Google Cloud TTS |
| 이미지 | Gemini API | 프롬프트 수정 재시도 | Pexels 스톡 이미지 |
| 대본/메타 | Claude API | GPT-4o | 로컬 템플릿 |

#### 4.1.3 성공률 수치 근거

| 항목 | 단일 경로 | 폴백 적용 | +체크포인트 | +이중화+경로안전 |
|------|----------|----------|-----------|----------------|
| 대본 | 95% | 99% | 99% | 99% |
| TTS | 90% | 99% | 99% | 99% |
| 스토리보드 | 95% | 99% | 99% | 99% |
| 이미지 (15장) | **21%** | **97%** | 97% | 97% |
| FFmpeg | 93% | 93% | 93% | **97%** |
| 썸네일 | 99% | 99% | 99% | 99% |
| 메타데이터 | 95% | 99% | 99% | 99% |
| 업로드 | 90% | 90% | 90% | **95%** |
| **E2E** | **~55%** | **~75%** | **~90%** | **~95%** |

### 4.2 비용 효율성

#### Option A: 최소 비용 구성 (Edge TTS 기본)

| 항목 | 도구 | 월 비용 |
|------|------|--------|
| 대본 + 스토리보드 + 메타 | Claude API | ~$15 |
| TTS + SRT | **Edge TTS (무료)** | **$0** |
| 이미지 생성 | Gemini API (무료 tier) | $0~20 |
| 이미지 폴백 | Pexels/Pixabay (무료) | $0 |
| 영상 합성 | FFmpeg | $0 |
| 썸네일 | Pillow | $0 |
| 업로드 | YouTube API | $0 |
| **합계** | | **$15~35/월** |
| **영상 1개당** | | **$0.12~0.29** |

#### Option B: 프리미엄 구성 (ElevenLabs)

| 항목 | 도구 | 월 비용 |
|------|------|--------|
| 대본 + 스토리보드 + 메타 | Claude API | ~$15 |
| TTS + SRT | ElevenLabs Pro | $99 |
| 이미지 생성 | Gemini API | $0~20 |
| 영상 합성 + 썸네일 + 업로드 | FFmpeg + Pillow + YouTube API | $0 |
| **합계** | | **$114~134/월** |
| **영상 1개당** | | **$0.95~1.12** |

### 4.3 성능

| 지표 | 목표 |
|------|------|
| 영상 1개 생성 시간 | 10~20분 (API 대기 포함) |
| 하루 생산량 | 4개 이상 |
| 배치 이미지 생성 | 10~15장/영상 |

### 4.4 품질

| 지표 | 목표 |
|------|------|
| 영상 해상도 | 1920x1080 (Full HD) |
| 오디오 품질 | AAC 192kbps |
| 자막 동기화 정확도 | 100ms 이내 |
| 이미지 스타일 일관성 | 70~80% (프롬프트 고정으로 향상) |
| 썸네일 해상도 | 1280x720 |

---

## 5. 데이터 흐름 (Data Flow)

```
[키워드] ─→ Claude API
              │
              ▼
         [대본 JSON]
              │
         ┌────┴────┐
         ▼         ▼
   ElevenLabs    Claude API
   API            │
   │              ▼
   ▼         [스토리보드 +
 [MP3]      이미지 프롬프트 JSON]
 [SRT]           │
   │             ▼
   │        Gemini API
   │             │
   │             ▼
   │        [이미지 파일들]
   │        [비디오 클립들 (선택)]
   │             │
   └──────┬──────┘
          ▼
       FFmpeg
          │
          ▼
      [MP4 영상]
          │
     ┌────┴────┐
     ▼         ▼
  Pillow    Claude API
     │         │
     ▼         ▼
 [썸네일]  [메타데이터 JSON]
     │         │
     └────┬────┘
          ▼
   YouTube Data API v3
          │
          ▼
    [업로드 완료]
```

---

## 6. 파일 구조 (Project Structure)

```
영상자동화/
├── PRD_영상자동화.md              # 본 문서
├── config/
│   ├── config.yaml               # API 키, 설정값
│   └── voice_settings.yaml       # ElevenLabs 음성 설정
├── src/
│   ├── main.py                   # 메인 파이프라인 오케스트레이터
│   ├── script_generator.py       # [2단계] 대본 생성 (Claude API)
│   ├── tts_generator.py          # [3단계] TTS + SRT 생성 (ElevenLabs)
│   ├── storyboard_generator.py   # [4단계] 스토리보드 + 프롬프트 생성
│   ├── image_generator.py        # [5단계] 이미지/비디오 생성 (Gemini)
│   ├── video_composer.py         # [6단계] FFmpeg 영상 합성
│   ├── metadata_generator.py     # [6b] 유튜브 메타 생성
│   ├── thumbnail_generator.py    # [7단계] 썸네일 생성 (Pillow)
│   ├── youtube_uploader.py       # [8단계] 유튜브 업로드
│   └── utils/
│       ├── srt_converter.py      # 타임스탬프 → SRT 변환
│       ├── retry_handler.py      # 재시도 로직
│       └── file_manager.py       # 파일 관리
├── templates/
│   ├── prompts/
│   │   ├── script_prompt.txt     # 대본 생성 프롬프트 템플릿
│   │   ├── storyboard_prompt.txt # 스토리보드 프롬프트 템플릿
│   │   ├── metadata_prompt.txt   # 메타데이터 프롬프트 템플릿
│   │   └── character_sheet.txt   # 캐릭터 일관성 프롬프트
│   └── thumbnail/
│       └── base_template.html    # 썸네일 HTML 템플릿 (Playwright용)
├── fonts/
│   └── NanumGothicExtraBold.ttf  # 한글 폰트
├── output/
│   └── {date}_{topic}/
│       ├── script.json
│       ├── narration.mp3
│       ├── subtitles.srt
│       ├── images/
│       ├── video.mp4
│       ├── thumbnail.jpg
│       └── metadata.json
├── requirements.txt
└── README.md
```

---

## 7. 외부 의존성 & API

### 7.1 필수 API 키

| API | 용도 | 발급처 |
|-----|------|--------|
| **Anthropic API Key** | 대본, 스토리보드, 메타데이터 생성 | https://console.anthropic.com |
| **ElevenLabs API Key** | TTS + SRT | https://elevenlabs.io |
| **Google AI API Key** | Gemini 이미지 생성 | https://ai.google.dev |
| **YouTube OAuth 2.0** | 영상 업로드 | https://console.cloud.google.com |

### 7.2 선택 API 키

| API | 용도 | 발급처 |
|-----|------|--------|
| Kling AI API | AI 비디오 생성 (I2V) | https://klingai.com |
| Runway API | AI 비디오 생성 (I2V) | https://runwayml.com |

### 7.3 필수 소프트웨어

| 소프트웨어 | 버전 | 용도 |
|-----------|------|------|
| Python | 3.10+ | 메인 런타임 |
| FFmpeg | 6.0+ | 영상 합성 |

### 7.4 Python 패키지

```
# 핵심 API
anthropic>=0.40.0          # Claude API
google-genai>=0.5.0        # Gemini API
google-api-python-client   # YouTube API
google-auth-oauthlib       # YouTube OAuth

# TTS (이중화)
edge-tts>=6.1.0            # Edge TTS (기본, 무료)
elevenlabs>=1.0.0          # ElevenLabs SDK (폴백, 유료)

# 이미지/영상
Pillow>=10.0               # 썸네일 생성 + 이미지 업스케일

# 자막/오디오
srt>=3.5                   # SRT 파싱
pydub>=0.25.0              # 오디오 concat (챕터 합치기)

# 파이프라인 인프라
tenacity>=9.0.0            # API 재시도 (지수 백오프)
pydantic-settings>=2.5.0   # 설정 관리 (.env + config)
python-dotenv>=1.0.0       # .env 파일 로드
pyyaml>=6.0                # config.yaml
click>=8.1.0               # CLI 도구

# 선택 (자막 정밀화)
# faster-whisper>=1.0.0    # Whisper 기반 SRT 보정 (GPU 권장)
```

---

## 8. 리스크 & 대응 전략

### 8.1 기술 리스크

| 리스크 | 수준 | 영향 | 대응 |
|--------|------|------|------|
| **이미지 배치 실패** | 🔴 높음 | 15장 중 1장만 실패해도 영상 제작 불가 | **3단계 폴백 필수**: Gemini→프롬프트수정→Pexels스톡→이전씬재사용 |
| **Edge TTS 차단** | 🔴 높음 | 무료 TTS 사용 불가 | **TTS 이중화**: Edge TTS→ElevenLabs→Google Cloud TTS |
| **Gemini 실험 모델 변경** | 🟡 중간 | 이미지 생성 코드 수정 필요 | 모델명을 config에서 관리, Imagen 3 대안 준비 |
| **Windows 한글 경로** | 🟡 중간 | FFmpeg 자막 필터 실패 | **영문 임시 디렉토리**에서 작업, SRT는 utf-8-sig |
| **YouTube OAuth 만료** | 🟡 중간 | 업로드 자동화 중단 | 프로덕션 앱 심사 통과 필수 (수주 소요) |
| AI 이미지 품질 편차 | 🟡 중간 | 영상 품질 저하 | 장면당 2~3장 생성 후 최적 선택, 스타일 프롬프트 고정 |
| API Rate Limit | 🟡 중간 | 파이프라인 중단 | 딜레이 삽입 (6초/이미지), tenacity 재시도 |
| FFmpeg 자막 폰트 렌더링 | 🟢 낮음 | 자막 깨짐 | fontsdir 명시, 한글 폰트 확인 |

### 8.2 비즈니스 리스크

| 리스크 | 수준 | 영향 | 대응 |
|--------|------|------|------|
| 유튜브 스팸 판정 | 중간 | 채널 페널티/삭제 | 하루 2~3개 제한, 랜덤 간격, private 먼저 업로드 |
| 저작권 이슈 | 중간 | 영상 삭제/저작권 경고 | 해외 콘텐츠 "재창작" 필수, 단순 번역 금지 |
| 유튜브 AI 콘텐츠 정책 변화 | 중간 | 수익화 제한 | AI 생성 콘텐츠 라벨링, 정책 모니터링 |
| 수익화 기간 | 낮음 | 초기 비용 발생 | 구독자 1,000 + 시청시간 4,000시간 달성 전략 필요 |

### 8.3 YouTube API 할당량 리스크

| 시나리오 | 소비량 | 대응 |
|----------|--------|------|
| 하루 4개 업로드 | 6,600 units | 기본 할당량(10,000) 내 |
| 하루 6개 업로드 | 9,900 units | 한계에 근접, 할당량 증가 신청 필요 |
| 할당량 초과 | - | 다음 날 자정(태평양 시간) 리셋까지 대기 |

---

## 9. 개발 로드맵

### Phase 1: MVP (1~2주)
- [ ] 프로젝트 셋업 (Python 환경, API 키 설정)
- [ ] 대본 생성 모듈 (`script_generator.py`)
- [ ] TTS + SRT 생성 모듈 (`tts_generator.py`)
- [ ] FFmpeg 영상 합성 모듈 (`video_composer.py`) — 이미지 슬라이드쇼 + 음성 + 자막
- [ ] 수동 이미지 입력으로 첫 영상 생성 테스트

### Phase 2: 이미지 자동화 (1~2주)
- [ ] 스토리보드 생성 모듈 (`storyboard_generator.py`)
- [ ] Gemini API 이미지 생성 모듈 (`image_generator.py`)
- [ ] 캐릭터 일관성 프롬프트 시스템
- [ ] Ken Burns 효과 (줌/팬) 적용
- [ ] 전체 파이프라인 통합 테스트

### Phase 3: 업로드 자동화 (1주)
- [ ] 메타데이터 자동 생성 모듈 (`metadata_generator.py`)
- [ ] 썸네일 생성 모듈 (`thumbnail_generator.py`)
- [ ] YouTube 업로드 모듈 (`youtube_uploader.py`)
- [ ] OAuth 토큰 자동 갱신 로직

### Phase 4: 안정화 & 최적화 (1~2주)
- [ ] 에러 핸들링 강화 (재시도, 로깅, 알림)
- [ ] 배치 처리 (하루 4개 자동 생성)
- [ ] 비용 최적화 (API 사용량 모니터링)
- [ ] 품질 검수 프로세스 (private 업로드 → 검토 → public 전환)

### Phase 5: 고도화 (선택)
- [ ] AI 비디오 생성 (Kling/Runway I2V) 통합
- [ ] n8n 오케스트레이션 (스케줄 자동 실행)
- [ ] 성과 분석 (YouTube Analytics API 연동)
- [ ] A/B 테스트 (제목/썸네일 변형)

---

## 10. 성공 지표 (KPIs)

| 지표 | 목표 | 전제 조건 |
|------|------|----------|
| 파이프라인 E2E 성공률 | 95% 이상 | 폴백+체크포인트+이중화+경로안전 모두 구현 |
| 영상 1개 생성 시간 | 20분 이내 | - |
| 영상 1개당 비용 | $0.3 이하 (Edge TTS) / $1 이하 (ElevenLabs) | - |
| 하루 생산량 | 4개 | - |
| 영상 품질 (주관 평가) | 수동 제작 대비 80% 이상 | - |
| 수익화 달성 기간 | 2~3개월 내 | - |

#### 95% 미달 시 단계별 확인 체크리스트

| 실제 성공률 | 원인 가능성 | 확인 사항 |
|-----------|-----------|----------|
| 90~95% | 이미지 폴백 미흡 | Pexels API 키 등록 여부, 폴백 체인 작동 확인 |
| 80~90% | 체크포인트 미구현 | checkpoint.json 저장/로드 확인 |
| 70~80% | TTS 이중화 미적용 | Edge TTS 실패 시 ElevenLabs 폴백 확인 |
| 55~70% | 폴백 전략 미적용 | 단일 경로만 구현된 상태 |

---

## 부록 A: 원래 계획(뉴머니 영상) vs 확정 계획 비교

| 단계 | 뉴머니 영상 (원래) | 확정 계획 | 변경 사유 |
|------|-------------------|----------|----------|
| 1. 주제 선정 | Publercity | 유벤치/VidIQ/수동 | Publercity 도구 확인 불가 |
| 2. 대본 | ChatGPT + Claude | Claude API | API 자동화에 최적 |
| 3. 음성+자막 | ElevenLabs (TTS→SRT) | ElevenLabs with-timestamps API | ✅ 동일 (API 구체화) |
| 4. 스토리보드 | 수동/AI | Claude API | 자동화 |
| 5. 이미지/영상 | Gemini AI | Gemini API | ✅ 동일 (API 구체화) |
| 6. 영상 편집 | **CapCut** | **FFmpeg** | CapCut 공식 API 없음, FFmpeg 성공률 99% |
| 6b. 메타 | 수동/AI | Claude API | 자동화 |
| 7. 썸네일 | **Canva** | **Pillow/Playwright** | Canva API는 Enterprise 전용, 고비용 |
| 8. 업로드 | 수동 | YouTube Data API v3 | 완전 자동화 |

---

## 부록 B: 필수 환경 설정 체크리스트

**필수 (없으면 파이프라인 실행 불가)**
- [ ] Python 3.10+ 설치
- [ ] FFmpeg 6.0+ 설치 및 PATH 등록
- [ ] 한글 폰트 설치 (NanumGothicExtraBold 등)
- [ ] Anthropic API 키 발급
- [ ] Google AI API 키 발급 (Gemini)
- [ ] pip install -r requirements.txt

**폴백/이중화용 (95% 달성에 필수)**
- [ ] ElevenLabs API 키 발급 (TTS 폴백용)
- [ ] Pexels API 키 발급 (이미지 폴백용, 무료)
- [ ] Pixabay API 키 발급 (이미지 폴백용, 무료)

**업로드 자동화용 (수동 업로드 시 불필요)**
- [ ] Google Cloud 프로젝트 생성 + YouTube Data API v3 활성화
- [ ] YouTube OAuth 2.0 클라이언트 ID 발급
- [ ] YouTube 채널 전화번호 인증 (커스텀 썸네일 요건)
- [ ] **Google OAuth 앱 프로덕션 심사 신청 (7일 토큰 만료 방지, 수주 소요)**

---

## 부록 C: 성공률 95% 달성 필수 구현 체크리스트

> 아래 항목이 모두 구현되지 않으면 95%에 도달할 수 없다.

- [ ] **체크포인트 시스템**: 단계별 checkpoint.json 저장/로드 + `--resume` CLI 옵션
- [ ] **TTS 이중화**: Edge TTS(기본) → ElevenLabs(폴백) 자동 전환
- [ ] **이미지 3단계 폴백**: Gemini → 프롬프트수정 재시도 → Pexels 스톡 → 이전씬 재사용
- [ ] **영문 임시 디렉토리**: `tempfile.mkdtemp()`에서 모든 FFmpeg 작업 수행
- [ ] **SRT 인코딩**: `utf-8-sig` (BOM 포함) 저장
- [ ] **tenacity 재시도**: 모든 외부 API에 `@retry(stop=stop_after_attempt(3), wait=wait_exponential())`
- [ ] **YouTube OAuth 관리**: `Credentials.refresh(Request())` 자동 갱신 + 프로덕션 앱 심사

---

*문서 버전: 2.0*
*작성일: 2026-03-18*
*갱신: v2.0 — 성공률 재평가 반영 (단일 경로 55% → 폴백+체크포인트+이중화 95%)*
*기반: 뉴머니(@newmoney_story) 영상 분석 + 12개 기술 검증 조사*
