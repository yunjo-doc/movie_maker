@echo off
chcp 65001 >nul <nul
cd /d "%~dp0"
title Movie Maker Web UI
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [설치] 처음 실행이라 가상환경을 만듭니다. 몇 분 걸릴 수 있어요...
    python -m venv .venv || (echo Python을 찾을 수 없습니다. Python 3.11 이상을 설치하세요. & pause & exit /b 1)
    "%PY%" -m pip install -q --upgrade pip
)

"%PY%" -c "import fastapi, uvicorn, anthropic, edge_tts" >nul 2>&1 || (
    echo [설치] 필요한 패키지를 설치합니다...
    "%PY%" -m pip install -q anthropic google-genai google-api-python-client google-auth-oauthlib edge-tts elevenlabs Pillow requests PyJWT srt pydub mutagen tenacity pydantic-settings python-dotenv pyyaml click fastapi "uvicorn[standard]"
)

echo 브라우저가 자동으로 열립니다. 이 창을 닫으면 프로그램이 종료됩니다.
"%PY%" -m webui.server
pause
