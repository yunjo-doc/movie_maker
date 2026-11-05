"""웹 브라우저용 영상 제작 UI 서버

실행: python -m webui.server  (또는 웹UI실행.bat)
기존 파이프라인 코드는 수정하지 않고 그대로 호출한다.
"""

import copy
import json
import logging
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # output/, bgm/ 등 상대경로 기준
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from config import config, settings  # noqa: E402
from pipeline.base import Pipeline, Step  # noqa: E402
from pipeline.checkpoint import CheckpointManager  # noqa: E402
from pipeline.context import PipelineContext  # noqa: E402
from pipeline.steps.step0_plan import STYLE_PRESETS, InteractivePlanner  # noqa: E402
from pipeline.steps.step1_script import GenerateScriptStep  # noqa: E402
from pipeline.steps.step2_tts import GenerateTTSStep  # noqa: E402
from pipeline.steps.step3_storyboard import GenerateStoryboardStep  # noqa: E402
from pipeline.steps.step4_images import GenerateImagesStep  # noqa: E402
from pipeline.steps.step4b_i2v import GenerateI2VClipsStep  # noqa: E402
from pipeline.steps.step5_video import ComposeVideoStep  # noqa: E402
from pipeline.steps.step5b_capcut import GenerateCapCutDraftStep  # noqa: E402
from pipeline.steps.step6_thumbnail import GenerateThumbnailStep  # noqa: E402
from pipeline.steps.step6b_metadata import GenerateMetadataStep  # noqa: E402
from pipeline.steps.step7_upload import UploadYouTubeStep  # noqa: E402
from utils.logging_config import setup_logging  # noqa: E402

logger = logging.getLogger("webui")

OUTPUT_DIR = ROOT / config["pipeline"]["output_dir"]
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).resolve().parent / "static"
ENV_PATH = ROOT / ".env"
JOB_FILE = "webui_job.json"

ORIGINAL_CONFIG = copy.deepcopy(config)

STEP_LABELS = {
    "generate_script": "대본 작성",
    "generate_tts": "음성 생성",
    "generate_storyboard": "스토리보드",
    "generate_images": "이미지 생성",
    "generate_i2v_clips": "AI 영상 클립",
    "compose_video": "영상 합성",
    "generate_capcut_draft": "CapCut 프로젝트",
    "generate_thumbnail": "썸네일",
    "generate_metadata": "제목·설명",
    "upload_youtube": "YouTube 업로드",
}

LENGTH_CHAPTERS = {"short": 3, "normal": 6, "long": 9}

API_KEYS = [
    ("ANTHROPIC_API_KEY", "Anthropic (Claude)", "대본·기획·스토리보드", True),
    ("GEMINI_API_KEY", "Google Gemini", "이미지 생성", True),
    ("OPENAI_API_KEY", "OpenAI", "고품질 음성 (TTS)", False),
    ("ELEVENLABS_API_KEY", "ElevenLabs", "고품질 음성 (TTS)", False),
    ("PEXELS_API_KEY", "Pexels", "스톡 이미지 폴백", False),
    ("PIXABAY_API_KEY", "Pixabay", "스톡 이미지 폴백", False),
    ("KLING_ACCESS_KEY", "Kling Access Key", "AI 영상 클립", False),
    ("KLING_SECRET_KEY", "Kling Secret Key", "AI 영상 클립", False),
    ("YOUTUBE_CLIENT_ID", "YouTube Client ID", "자동 업로드", False),
    ("YOUTUBE_CLIENT_SECRET", "YouTube Client Secret", "자동 업로드", False),
]


# ───────────────────────── 작업 관리 ─────────────────────────

class JobCancelled(Exception):
    pass


class GuardedStep(Step):
    """취소 요청을 단계 사이에서 확인하는 래퍼"""

    def __init__(self, inner: Step, job: dict):
        self.inner = inner
        self.name = inner.name
        self.job = job

    def run(self, ctx):
        if self.job.get("cancel"):
            raise JobCancelled("사용자가 취소했습니다")
        return self.inner.run(ctx)


class JobManager:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.order: list[str] = []
        self.q: "queue.Queue[str]" = queue.Queue()
        self.current: dict | None = None
        self.lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    # ---- 생성 ----
    def add(self, kind: str, topic: str, project_id: str, options: dict) -> dict:
        job = {
            "id": uuid.uuid4().hex[:10],
            "kind": kind,  # new | resume | upload
            "topic": topic,
            "project_id": project_id,
            "options": options,
            "status": "queued",
            "steps": [],
            "logs": deque(maxlen=400),
            "current": "대기 중",
            "error": "",
            "created": time.time(),
            "started": None,
            "finished": None,
            "cancel": False,
        }
        job["steps"] = [
            {"name": s.name, "label": STEP_LABELS.get(s.name, s.name), "state": "pending"}
            for s in build_steps(kind, options)
        ]
        with self.lock:
            self.jobs[job["id"]] = job
            self.order.append(job["id"])
        self.q.put(job["id"])
        return job

    def cancel(self, job_id: str):
        job = self.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "작업 없음")
        job["cancel"] = True
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["current"] = "취소됨"

    def remove(self, job_id: str):
        job = self.jobs.get(job_id)
        if job and job["status"] in ("done", "failed", "cancelled"):
            with self.lock:
                self.jobs.pop(job_id, None)
                self.order.remove(job_id)

    def active_project_ids(self) -> set:
        return {j["project_id"] for j in self.jobs.values() if j["status"] in ("queued", "running")}

    def snapshot(self) -> list:
        out = []
        for jid in self.order:
            j = self.jobs[jid]
            d = {k: v for k, v in j.items() if k not in ("logs", "cancel")}
            d["logs"] = list(j["logs"])[-120:]
            out.append(d)
        return out

    # ---- 로그 → 진행상황 ----
    def on_log(self, record: logging.LogRecord):
        job = self.current
        if not job:
            return
        msg = record.getMessage()
        if set(msg.strip()) == {"="}:
            return
        job["logs"].append(f"{time.strftime('%H:%M:%S')} {record.levelname[0]} {msg}")
        for tag, state in (("[START] ", "running"), ("[DONE] ", "done"),
                           ("[SKIP] ", "skipped"), ("[FAIL] ", "failed")):
            if msg.startswith(tag):
                name = msg[len(tag):].split(":")[0].strip()
                for s in job["steps"]:
                    if s["name"] == name:
                        s["state"] = state
                if state == "running":
                    job["current"] = f"{STEP_LABELS.get(name, name)} 시작"
                return
        if record.levelno >= logging.INFO:
            job["current"] = msg[:160]

    # ---- 실행 ----
    def _worker(self):
        while True:
            jid = self.q.get()
            job = self.jobs.get(jid)
            if not job or job["status"] != "queued":
                continue
            self.current = job
            job["status"] = "running"
            job["started"] = time.time()
            try:
                run_job(job)
                job["status"] = "done"
                job["current"] = "완료"
            except JobCancelled:
                job["status"] = "cancelled"
                job["current"] = "취소됨"
            except Exception as e:  # noqa: BLE001
                logging.getLogger("webui").exception("작업 실패")
                job["status"] = "failed"
                job["error"] = str(e)
                job["current"] = f"실패: {e}"[:200]
                for s in job["steps"]:
                    if s["state"] == "running":
                        s["state"] = "failed"
            finally:
                job["finished"] = time.time()
                self.current = None
                restore_config()


class JobLogHandler(logging.Handler):
    def __init__(self, manager: JobManager):
        super().__init__(level=logging.INFO)
        self.manager = manager

    def emit(self, record):
        if record.name.startswith(("uvicorn", "webui", "watchfiles", "asyncio")):
            return
        try:
            self.manager.on_log(record)
        except Exception:  # noqa: BLE001
            pass


def restore_config():
    # 키 단위 교체 → 다른 스레드에서 읽는 중에도 KeyError 없음
    for key, val in ORIGINAL_CONFIG.items():
        config[key] = copy.deepcopy(val)


def apply_options(opts: dict):
    restore_config()
    style = STYLE_PRESETS.get(str(opts.get("style", "")))
    if style:
        config["images"]["style_suffix"] = style["style_suffix"]
        config["images"]["style_description"] = f"{style['name']} — {style['description']}"
    chapters = LENGTH_CHAPTERS.get(opts.get("length", "normal"))
    if chapters:
        config["script"]["chapters"] = chapters
        config["script"]["target_duration_minutes"] = round(chapters * 10 / 6)
    tts = opts.get("tts")
    if tts in ("openai", "edge", "elevenlabs"):
        config["tts"]["primary"] = tts
        voice = opts.get("voice")
        if voice:
            key = "voice_id" if tts == "elevenlabs" else "voice"
            config["tts"][tts][key] = voice
    if opts.get("privacy") in ("private", "unlisted", "public"):
        config["youtube"]["privacy_status"] = opts["privacy"]
    config["youtube"]["schedule_time"] = (opts.get("schedule") or "").strip()


def build_steps(kind: str, opts: dict) -> list:
    if kind == "upload":
        return [UploadYouTubeStep()]
    steps = [GenerateScriptStep(), GenerateTTSStep(), GenerateStoryboardStep(), GenerateImagesStep()]
    if opts.get("i2v"):
        steps.append(GenerateI2VClipsStep())
    steps.append(ComposeVideoStep())
    if opts.get("capcut"):
        steps.append(GenerateCapCutDraftStep())
    steps += [GenerateThumbnailStep(), GenerateMetadataStep()]
    if opts.get("upload"):
        steps.append(UploadYouTubeStep())
    return steps


def project_dir(pid: str) -> Path:
    if not pid or any(c in pid for c in '\\/:*?"<>|') or pid.startswith("."):
        raise HTTPException(400, "잘못된 프로젝트 ID")
    return OUTPUT_DIR / pid


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_job_info(job: dict, **extra):
    d = project_dir(job["project_id"])
    d.mkdir(parents=True, exist_ok=True)
    info = read_json(d / JOB_FILE)
    info.update({"topic": job["topic"], "options": job["options"]})
    info.setdefault("created", datetime.now().isoformat(timespec="seconds"))
    info.update(extra)
    (d / JOB_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def run_job(job: dict):
    opts = job["options"]
    apply_options(opts)
    out_dir = project_dir(job["project_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    out = str(Path(config["pipeline"]["output_dir"]) / job["project_id"])

    if job["kind"] == "upload":
        ctx = PipelineContext(
            project_id=job["project_id"], topic=job["topic"], output_dir=out,
            video_path=str(out_dir / "video.mp4"),
            thumbnail_path=str(out_dir / "thumbnail.jpg") if (out_dir / "thumbnail.jpg").exists() else "",
            metadata=read_json(out_dir / "metadata.json"),
        )
        s = job["steps"][0]
        s["state"] = "running"
        job["current"] = "YouTube 업로드 중"
        ctx = UploadYouTubeStep().run(ctx)
        s["state"] = "done"
        save_job_info(job, video_url=ctx.video_url, uploaded_at=datetime.now().isoformat(timespec="seconds"))
        return

    save_job_info(job)
    brief = read_json(out_dir / "brief.json") if opts.get("use_brief") else {}
    ctx = PipelineContext(project_id=job["project_id"], topic=job["topic"], output_dir=out, brief=brief)
    steps = [GuardedStep(s, job) for s in build_steps(job["kind"], opts)]
    pipeline = Pipeline(steps, CheckpointManager(out))
    result = pipeline.run(ctx, resume=(job["kind"] == "resume"))
    extra = {"completed": datetime.now().isoformat(timespec="seconds")}
    if result.video_url:
        extra["video_url"] = result.video_url
        extra["uploaded_at"] = extra["completed"]
    save_job_info(job, **extra)


def new_project_id() -> str:
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid, n = base, 1
    taken = manager.active_project_ids()
    while (OUTPUT_DIR / pid).exists() or pid in taken:
        n += 1
        pid = f"{base}_{n}"
    return pid


manager = JobManager()


# ───────────────────────── .env ─────────────────────────

def write_env(updates: dict):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in updates:
            lines[i] = f"{k}={updates[k]}"
            seen.add(k)
    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in updates.items():
        os.environ[k] = v


def mask(v: str) -> str:
    if not v:
        return ""
    return v[:4] + "••••" + v[-4:] if len(v) > 10 else "••••"


# ───────────────────────── API ─────────────────────────

app = FastAPI(title="Movie Maker")

# 데스크톱 앱(Wails)에서 실행될 때: 실행마다 새로 만든 토큰으로만 API 호출 허용
API_TOKEN = os.getenv("WEBUI_TOKEN", "")


@app.middleware("http")
async def check_token(request: Request, call_next):
    if API_TOKEN and request.url.path.startswith("/api/") and request.method != "OPTIONS":
        if request.headers.get("X-Token") != API_TOKEN:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://wails.localhost", "wails://wails", "http://localhost:34115",
                   "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


class JobRequest(BaseModel):
    topics: list[str] = []
    options: dict = {}
    project_id: str | None = None  # 기획서 기반 제작 시


class PlanStart(BaseModel):
    topic: str
    style: str = ""


class PlanMessage(BaseModel):
    text: str


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/meta")
def meta():
    return {
        "styles": [{"id": k, **{f: v[f] for f in ("name", "description", "best_for")}}
                   for k, v in STYLE_PRESETS.items()],
        "default_style": ORIGINAL_CONFIG["images"].get("style_description", ""),
        "tts_default": ORIGINAL_CONFIG["tts"].get("primary", "edge"),
        "voices": {
            "edge": [["ko-KR-HyunsuNeural", "현수 (남성)"], ["ko-KR-InJoonNeural", "인준 (남성)"],
                     ["ko-KR-SunHiNeural", "선희 (여성)"]],
            "openai": [["onyx", "Onyx (남성, 깊은)"], ["echo", "Echo (남성)"], ["fable", "Fable (중성)"],
                       ["alloy", "Alloy (중성)"], ["nova", "Nova (여성)"], ["shimmer", "Shimmer (여성)"]],
            "elevenlabs": [[ORIGINAL_CONFIG["tts"]["elevenlabs"].get("voice_id", ""), "config.yaml 기본 음성"]],
        },
        "voice_default": {
            "edge": ORIGINAL_CONFIG["tts"]["edge"].get("voice"),
            "openai": ORIGINAL_CONFIG["tts"]["openai"].get("voice"),
            "elevenlabs": ORIGINAL_CONFIG["tts"]["elevenlabs"].get("voice_id"),
        },
    }


@app.get("/api/status")
def status():
    return {
        "keys": {k: bool(os.getenv(k)) for k, *_ in API_KEYS},
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "youtube_token": (ROOT / "secrets" / "youtube_token.json").exists(),
        "model": config["script"]["model"],
    }


@app.get("/api/jobs")
def list_jobs():
    return manager.snapshot()


@app.post("/api/jobs")
def create_jobs(req: JobRequest):
    opts = dict(req.options)
    created = []
    if req.project_id:  # 기획서 기반
        d = project_dir(req.project_id)
        brief = read_json(d / "brief.json")
        if not brief:
            raise HTTPException(400, "기획서(brief.json)가 없습니다")
        opts["use_brief"] = True
        topic = (req.topics[0].strip() if req.topics else "") or brief.get("title", req.project_id)
        created.append(manager.add("new", topic, req.project_id, opts))
    else:
        topics = [t.strip() for t in req.topics if t.strip()]
        if not topics:
            raise HTTPException(400, "주제를 입력하세요")
        for t in topics:
            created.append(manager.add("new", t, new_project_id(), opts))
    return {"created": [j["id"] for j in created]}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    manager.cancel(job_id)
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: str):
    manager.remove(job_id)
    return {"ok": True}


@app.get("/api/projects")
def list_projects():
    active = manager.active_project_ids()
    items = []
    for d in OUTPUT_DIR.iterdir():
        if not d.is_dir():
            continue
        info = read_json(d / JOB_FILE)
        ck = read_json(d / "checkpoint.json")
        md = read_json(d / "metadata.json")
        brief = read_json(d / "brief.json")
        video = d / "video.mp4"
        thumb = d / "thumbnail.jpg"
        if d.name in active:
            state = "running"
        elif ck.get("_failed_step"):
            state = "failed"
        elif ck:
            state = "incomplete"
        elif video.exists():
            state = "done"
        elif brief:
            state = "planned"
        else:
            state = "empty"
        if state == "empty":
            continue
        ver = int(video.stat().st_mtime) if video.exists() else 0
        items.append({
            "id": d.name,
            "topic": info.get("topic") or ck.get("topic") or brief.get("title") or d.name,
            "title": md.get("title") or brief.get("title") or "",
            "description": md.get("description", ""),
            "tags": md.get("tags", []),
            "state": state,
            "failed_step": STEP_LABELS.get(ck.get("_failed_step", "").replace("FAILED:", ""), ""),
            "completed_steps": [STEP_LABELS.get(s, s) for s in ck.get("_completed_steps", [])],
            "video": f"/files/{d.name}/video.mp4?v={ver}" if video.exists() else "",
            "thumbnail": f"/files/{d.name}/thumbnail.jpg?v={int(thumb.stat().st_mtime)}" if thumb.exists() else "",
            "video_url": info.get("video_url", ""),
            "has_brief": bool(brief),
            "brief": brief,
            "options": info.get("options", {}),
            "mtime": d.stat().st_mtime,
            "size_mb": round(video.stat().st_size / 1048576, 1) if video.exists() else 0,
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


@app.post("/api/projects/{pid}/resume")
def resume_project(pid: str):
    d = project_dir(pid)
    if not d.exists():
        raise HTTPException(404, "프로젝트 없음")
    if pid in manager.active_project_ids():
        raise HTTPException(409, "이미 진행 중입니다")
    info = read_json(d / JOB_FILE)
    ck = read_json(d / "checkpoint.json")
    opts = info.get("options") or {"use_brief": (d / "brief.json").exists()}
    topic = info.get("topic") or ck.get("topic") or pid
    job = manager.add("resume", topic, pid, opts)
    return {"created": [job["id"]]}


class UploadRequest(BaseModel):
    privacy: str = "private"
    schedule: str = ""


@app.post("/api/projects/{pid}/upload")
def upload_project(pid: str, req: UploadRequest):
    d = project_dir(pid)
    if not (d / "video.mp4").exists():
        raise HTTPException(400, "완성된 영상이 없습니다")
    if pid in manager.active_project_ids():
        raise HTTPException(409, "이미 진행 중입니다")
    info = read_json(d / JOB_FILE)
    topic = info.get("topic") or read_json(d / "brief.json").get("title") or pid
    opts = dict(info.get("options") or {})
    opts.update({"privacy": req.privacy, "schedule": req.schedule})
    job = manager.add("upload", topic, pid, opts)
    return {"created": [job["id"]]}


@app.post("/api/projects/{pid}/open")
def open_folder(pid: str):
    d = project_dir(pid)
    if not d.exists():
        raise HTTPException(404, "프로젝트 없음")
    if hasattr(os, "startfile"):
        os.startfile(str(d))  # noqa: S606 — 로컬 전용 앱
    return {"ok": True}


# ---- 설정 ----

@app.get("/api/settings")
def get_settings():
    return [{"key": k, "label": label, "usage": usage, "required": req,
             "set": bool(os.getenv(k)), "masked": mask(os.getenv(k, ""))}
            for k, label, usage, req in API_KEYS]


@app.post("/api/settings")
def save_settings(values: dict):
    allowed = {k for k, *_ in API_KEYS}
    updates = {k: str(v).strip() for k, v in values.items() if k in allowed and v is not None}
    updates = {k: v for k, v in updates.items() if v or values.get("_clear_" + k)}
    if updates:
        write_env(updates)
    return {"ok": True, "updated": list(updates)}


@app.post("/api/youtube/auth")
def youtube_auth():
    from utils.youtube_auth import get_youtube_service
    try:
        get_youtube_service()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"인증 실패: {e}")
    return {"ok": True}


# ---- AI 기획 ----

plan_sessions: dict[str, dict] = {}


def _planner(sid: str) -> dict:
    s = plan_sessions.get(sid)
    if not s:
        raise HTTPException(404, "기획 세션이 만료되었습니다. 새로 시작하세요.")
    return s


@app.post("/api/plan/start")
def plan_start(req: PlanStart):
    if not settings.anthropic_api_key:
        raise HTTPException(400, "Anthropic API 키를 먼저 설정하세요")
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(400, "주제를 입력하세요")
    planner = InteractivePlanner()
    if req.style:
        planner.select_style(req.style)
    try:
        reply = planner.research_topic(topic)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"AI 호출 실패: {e}")
    sid = uuid.uuid4().hex[:12]
    plan_sessions[sid] = {"planner": planner, "topic": topic, "project_id": None}
    return {"sid": sid, "reply": reply}


@app.post("/api/plan/{sid}/message")
def plan_message(sid: str, req: PlanMessage):
    s = _planner(sid)
    try:
        return {"reply": s["planner"].refine(req.text)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"AI 호출 실패: {e}")


@app.post("/api/plan/{sid}/finalize")
def plan_finalize(sid: str):
    s = _planner(sid)
    planner = s["planner"]
    pid = s["project_id"] or new_project_id()
    out = str(project_dir(pid))
    try:
        text = planner.finalize_brief()
        planner.save_brief(text, out)
    except Exception as e:  # noqa: BLE001
        planner.save_conversation(out) if Path(out).exists() else None
        raise HTTPException(500, f"기획서 생성 실패: {e}")
    planner.save_conversation(out)
    s["project_id"] = pid
    info = {"topic": s["topic"], "options": {}, "created": datetime.now().isoformat(timespec="seconds")}
    (Path(out) / JOB_FILE).write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"project_id": pid, "brief": read_json(Path(out) / "brief.json")}


app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main():
    import uvicorn
    import webbrowser

    setup_logging(level=config["pipeline"]["log_level"])
    logging.getLogger().addHandler(JobLogHandler(manager))
    port = int(os.getenv("WEBUI_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Movie Maker 웹 UI: {url}\n  종료하려면 이 창을 닫거나 Ctrl+C\n")
    if os.getenv("WEBUI_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
