@echo off
chcp 65001 >nul <nul
setlocal EnableExtensions
cd /d "%~dp0"
title YouTube Movie Maker
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [설치] 처음 실행이라 가상환경을 만듭니다. 몇 분 걸릴 수 있어요...
    python -m venv .venv || (echo Python을 찾을 수 없습니다. Python 3.11 이상을 설치하세요. & pause & exit /b 1)
    "%PY%" -m pip install -q --upgrade pip
    "%PY%" -m pip install -q anthropic google-genai google-api-python-client google-auth-oauthlib edge-tts elevenlabs Pillow requests PyJWT srt pydub mutagen tenacity pydantic-settings python-dotenv pyyaml click
)

where ffmpeg >nul 2>&1 || echo [경고] FFmpeg가 PATH에 없습니다. 영상 합성 단계에서 실패합니다.

findstr /r /c:"^ANTHROPIC_API_KEY=..*" .env >nul 2>&1 || echo [경고] .env 에 ANTHROPIC_API_KEY 가 비어 있습니다. 메뉴 8번으로 입력하세요.
findstr /r /c:"^GEMINI_API_KEY=..*" .env >nul 2>&1 || echo [경고] .env 에 GEMINI_API_KEY 가 비어 있습니다. 메뉴 8번으로 입력하세요.

:menu
echo.
echo ============================================
echo   YouTube 영상 자동 제작
echo ============================================
echo   1. 기획하기 (AI와 대화로 기획서 작성)
echo   2. 영상 만들기 (바로 제작, 업로드 안 함)
echo   3. 기획서로 영상 만들기 (1번 다음에)
echo   4. 중단된 작업 이어서 하기
echo   5. 진행 상태 보기
echo   6. 완성 영상 YouTube 업로드
echo   7. YouTube 계정 인증 (최초 1회)
echo   8. API 키 설정 (.env 열기)
echo   9. 결과 폴더 열기
echo   0. 종료
echo ============================================
set "SEL="
set /p "SEL=번호 선택: "

if "%SEL%"=="1" goto plan
if "%SEL%"=="2" goto run
if "%SEL%"=="3" goto brief
if "%SEL%"=="4" goto resume
if "%SEL%"=="5" goto status
if "%SEL%"=="6" goto upload
if "%SEL%"=="7" goto auth
if "%SEL%"=="8" goto env
if "%SEL%"=="9" goto output
if "%SEL%"=="0" exit /b 0
echo 잘못된 번호입니다.
goto menu

:ask_topic
set "TOPIC="
set /p "TOPIC=영상 주제: "
if "%TOPIC%"=="" goto ask_topic
exit /b 0

:ask_id
set "PID="
set /p "PID=프로젝트 ID: "
if "%PID%"=="" goto ask_id
exit /b 0

:ask_capcut
set "CAPCUT="
set "YN="
set /p "YN=CapCut 프로젝트도 만들까요? (y/N): "
if /i "%YN%"=="y" set "CAPCUT=--capcut"
exit /b 0

:plan
call :ask_topic
set "PID="
set /p "PID=프로젝트 ID (영문, 비우면 자동): "
if "%PID%"=="" (
    "%PY%" cli.py plan "%TOPIC%"
) else (
    "%PY%" cli.py plan "%TOPIC%" -p "%PID%"
)
goto done

:run
call :ask_topic
call :ask_capcut
"%PY%" cli.py run "%TOPIC%" --skip-upload %CAPCUT%
goto done

:brief
call :ask_topic
call :ask_id
call :ask_capcut
"%PY%" cli.py run "%TOPIC%" -p "%PID%" --brief --skip-upload %CAPCUT%
goto done

:resume
call :ask_topic
call :ask_id
"%PY%" cli.py run "%TOPIC%" -p "%PID%" --resume --skip-upload
goto done

:status
call :ask_id
"%PY%" cli.py status "%PID%"
goto done

:upload
call :ask_id
set "SCH="
set /p "SCH=예약 발행 시각 (예: 18:00, 비우면 설정값 사용): "
if "%SCH%"=="" (
    "%PY%" cli.py upload "%PID%"
) else (
    "%PY%" cli.py upload "%PID%" --schedule "%SCH%"
)
goto done

:auth
"%PY%" cli.py auth
goto done

:env
start "" notepad "%~dp0.env"
goto menu

:output
if not exist output mkdir output
start "" explorer "%~dp0output"
goto menu

:done
echo.
pause
goto menu
