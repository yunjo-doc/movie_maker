import { useEffect, useRef, useState } from "react";
import { BrowserOpenURL, ClipboardSetText } from "../../wailsjs/runtime/runtime";
import { api, fileUrl, store } from "../api";
import { Icon, PlayIcon } from "../Icon";
import { isActive, useStore } from "../store";
import type { Job, Project } from "../types";

export default function MakePage() {
  const { tab, setTab, projects, refreshProjects } = useStore();
  useEffect(() => {
    if (tab === "list") refreshProjects();
  }, [tab, refreshProjects]);

  return (
    <div className="wrap">
      <div className="head">
        <div>
          <h1>영상 생성</h1>
          <p>주제를 한 줄에 하나씩 입력하면 주제마다 유튜브 영상을 자동으로 만듭니다.</p>
        </div>
        <div className="tabs">
          <button className={tab === "new" ? "on" : ""} onClick={() => setTab("new")}>새 영상</button>
          <button className={tab === "list" ? "on" : ""} onClick={() => setTab("list")}>
            생성된 영상 {projects.length || ""}
          </button>
        </div>
      </div>
      {tab === "new" ? (
        <div className="grid">
          <NewVideoForm />
          <div className="stack">
            <div className="card"><h3>진행 상황</h3><JobList /></div>
            <ReadyCard />
          </div>
        </div>
      ) : (
        <ProjectGrid />
      )}
    </div>
  );
}

/* ───────────── 입력 폼 ───────────── */

function Seg({ value, onChange, items }: { value: string; onChange: (v: string) => void; items: [string, string, string][] }) {
  return (
    <div className="seg">
      {items.map(([v, label, sub]) => (
        <button key={v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {label}<small>{sub}</small>
        </button>
      ))}
    </div>
  );
}

function Toggle({ title, desc, checked, disabled, onChange }: { title: string; desc: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="toggle">
      <div><b>{title}</b><small>{desc}</small></div>
      <label className="sw">
        <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <i />
      </label>
    </div>
  );
}

function NewVideoForm() {
  const { meta, status, form, setForm, toast, go, refreshJobs } = useStore();
  const [topics, setTopics] = useState<string>(store<string>("topics") || "");
  const lines = topics.split("\n").map((s) => s.trim()).filter(Boolean);
  const k = status?.keys || {};
  const klingOk = !!(k.KLING_ACCESS_KEY && k.KLING_SECRET_KEY);
  const style = meta.styles.find((s) => s.id === form.style);
  const voices = meta.voices[form.tts] || [];
  const needKey = ({ openai: "OPENAI_API_KEY", elevenlabs: "ELEVENLABS_API_KEY" } as Record<string, string>)[form.tts];

  useEffect(() => {
    store("topics", topics);
  }, [topics]);
  useEffect(() => {
    if (status && !klingOk && form.i2v) setForm({ i2v: false });
  }, [status, klingOk, form.i2v, setForm]);

  const setTts = (tts: string) => setForm({ tts, voice: meta.voice_default[tts] || meta.voices[tts]?.[0]?.[0] || "" });

  const start = async () => {
    if (!lines.length) return toast("주제를 입력하세요", true);
    if (!k.ANTHROPIC_API_KEY || !k.GEMINI_API_KEY) {
      toast("설정에서 Anthropic·Gemini API 키를 먼저 입력하세요", true);
      return go("settings");
    }
    try {
      await api("/api/jobs", { body: { topics: lines, options: form } });
      setTopics("");
      toast(`${lines.length}개 영상 제작을 시작합니다`);
      refreshJobs();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  return (
    <div className="card">
      <div className="field">
        <div className="lbl">주제 <span>{lines.length}개</span></div>
        <textarea
          value={topics}
          onChange={(e) => setTopics(e.target.value)}
          placeholder={"AI가 바꿀 10년 후 직업\n초보를 위한 ETF 투자 입문\n잠 잘 자는 과학적인 방법"}
        />
      </div>
      <div className="field">
        <div className="lbl">그림 스타일</div>
        <select value={form.style} onChange={(e) => setForm({ style: e.target.value })}>
          <option value="">기본 (config.yaml)</option>
          {meta.styles.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <div className="hint">{style ? `${style.description} · 추천: ${style.best_for}` : `config.yaml 기본값: ${meta.default_style}`}</div>
      </div>
      <div className="field">
        <div className="lbl">분량</div>
        <Seg value={form.length} onChange={(length) => setForm({ length })}
          items={[["short", "짧게", "약 5분"], ["normal", "보통", "약 10분"], ["long", "길게", "약 15분"]]} />
      </div>
      <div className="field">
        <div className="lbl">음성 엔진</div>
        <Seg value={form.tts} onChange={setTts}
          items={[["edge", "Edge", "무료"], ["openai", "OpenAI", "고품질"], ["elevenlabs", "ElevenLabs", "최고품질"]]} />
        <select style={{ marginTop: 10 }} value={form.voice} onChange={(e) => setForm({ voice: e.target.value })}>
          {voices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {needKey && status && !k[needKey] && <div className="hint">API 키가 없어 무료 Edge 음성으로 자동 대체됩니다.</div>}
      </div>
      <div className="field">
        <div className="lbl">추가 옵션</div>
        <Toggle title="AI 영상 클립 (Kling)" desc={klingOk ? "일부 장면을 움직이는 영상으로 변환" : "설정에서 Kling 키를 넣으면 사용 가능"}
          checked={form.i2v} disabled={!klingOk} onChange={(i2v) => setForm({ i2v })} />
        <Toggle title="CapCut 프로젝트" desc="CapCut에서 바로 편집할 수 있게 생성" checked={form.capcut} onChange={(capcut) => setForm({ capcut })} />
        <Toggle title="YouTube 자동 업로드" desc="완성 후 바로 업로드" checked={form.upload} onChange={(upload) => setForm({ upload })} />
        {form.upload && (
          <div className="sub-opts">
            <select value={form.privacy} onChange={(e) => setForm({ privacy: e.target.value })}>
              <option value="private">비공개</option>
              <option value="unlisted">일부 공개</option>
              <option value="public">공개</option>
            </select>
            <input type="time" value={form.schedule} title="예약 발행 시각 (비우면 즉시)" onChange={(e) => setForm({ schedule: e.target.value })} />
          </div>
        )}
      </div>
      <button className="btn pri big" onClick={start}>{lines.length > 1 ? `생성 시작 (${lines.length}개)` : "생성 시작"}</button>
    </div>
  );
}

/* ───────────── 진행 상황 ───────────── */

const STATUS_TXT: Record<Job["status"], string> = { queued: "대기", running: "진행 중", done: "완료", failed: "실패", cancelled: "취소됨" };

function JobList() {
  const { jobs } = useStore();
  if (!jobs.length) {
    return (
      <div className="empty">
        <div className="ic"><Icon name="sparkle" size={22} /></div>
        아직 진행 중인 작업이 없습니다<br />왼쪽에 주제를 입력하고 생성을 시작하세요
      </div>
    );
  }
  return <>{[...jobs].reverse().map((j) => <JobCard key={j.id} job={j} />)}</>;
}

function JobCard({ job: j }: { job: Job }) {
  const { refreshJobs, resumeProject, refreshProjects, openModal } = useStore();
  const [showLog, setShowLog] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  const stick = useRef(true);
  const done = j.steps.filter((s) => s.state === "done" || s.state === "skipped").length;
  const pct = j.status === "done" ? 100 : Math.round((done / Math.max(1, j.steps.length)) * 100);
  const kind = j.kind === "resume" ? " · 이어하기" : j.kind === "upload" ? " · 업로드" : "";
  const mins = j.started ? Math.round(((j.finished || Date.now() / 1000) - j.started) / 60) : null;

  useEffect(() => {
    const el = logRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [j.logs, showLog]);

  const act = async (path: string, method: string) => {
    await api(path, { method });
    refreshJobs();
  };
  const view = async () => {
    const list = await refreshProjects();
    const p = list.find((x) => x.id === j.project_id);
    if (p) openModal(<ProjectModal p={p} />);
  };

  return (
    <div className="job">
      <div className="job-top"><b title={j.topic}>{j.topic}</b><span className={`badge ${j.status}`}>{STATUS_TXT[j.status]}</span></div>
      <div className="pmeta" style={{ margin: "-4px 0 6px" }}>{j.project_id}{kind}{mins !== null && ` · ${mins}분`}</div>
      <div className="bar"><i style={{ width: `${pct}%` }} /></div>
      <div className="steps">{j.steps.map((s) => <span key={s.name} className={`step ${s.state}`}>{s.label}</span>)}</div>
      <div className={`cur ${j.status === "failed" ? "err" : ""}`}>{j.status === "failed" ? j.error : j.current}</div>
      <button className="linkbtn" onClick={() => setShowLog(!showLog)}>{showLog ? "▾ 로그 닫기" : "▸ 로그 보기"}</button>
      {showLog && (
        <pre className="logbox" ref={logRef}
          onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < 8; }}>
          {j.logs.join("\n")}
        </pre>
      )}
      <div className="job-act">
        {isActive(j) && (
          <button className="btn sm ghost danger" onClick={() => act(`/api/jobs/${j.id}/cancel`, "POST")}>
            {j.status === "running" ? "현재 단계 후 중지" : "취소"}
          </button>
        )}
        {(j.status === "failed" || j.status === "cancelled") && j.kind !== "upload" && (
          <button className="btn sm" onClick={() => resumeProject(j.project_id)}>이어서 하기</button>
        )}
        {j.status === "done" && j.kind !== "upload" && <button className="btn sm" onClick={view}>영상 보기</button>}
        {!isActive(j) && <button className="btn sm ghost" onClick={() => act(`/api/jobs/${j.id}`, "DELETE")}>목록에서 지우기</button>}
      </div>
    </div>
  );
}

function ReadyCard() {
  const { status, go } = useStore();
  if (!status) return null;
  const k = status.keys;
  const items: [boolean, string, string, boolean][] = [
    [!!k.ANTHROPIC_API_KEY, "Claude API 키", "대본 작성에 필요", true],
    [!!k.GEMINI_API_KEY, "Gemini API 키", "이미지 생성에 필요", true],
    [status.ffmpeg, "FFmpeg", "영상 합성에 필요", true],
    [!!(k.KLING_ACCESS_KEY && k.KLING_SECRET_KEY), "Kling 키 (선택)", "AI 영상 클립", false],
    [!!(k.YOUTUBE_CLIENT_ID && status.youtube_token), "YouTube 인증 (선택)", "자동 업로드", false],
  ];
  const ready = items.filter((i) => i[3]).every((i) => i[0]);
  return (
    <div className="card">
      <h3>준비 상태</h3>
      {items.map(([ok, t, d, req]) => (
        <div key={t} className="row" style={{ padding: "7px 0" }}>
          <span className={`dot ${ok ? "ok" : req ? "err" : ""}`} />
          <span style={{ flex: 1 }}>{t}</span>
          <span className="pmeta">{ok ? "준비됨" : d}</span>
        </div>
      ))}
      {!ready && <button className="btn sm" style={{ marginTop: 10 }} onClick={() => go("settings")}>API 키 설정하기</button>}
    </div>
  );
}

/* ───────────── 생성된 영상 ───────────── */

const PSTATE: Record<string, [string, string]> = {
  done: ["완료", "done"], running: ["진행 중", "running"], failed: ["실패", "failed"],
  incomplete: ["미완성", "queued"], planned: ["기획서", "queued"],
};

function ProjectGrid() {
  const { projects, openModal, resumeProject, makeFromBrief, openFolder } = useStore();
  if (!projects.length) return <div className="card empty">아직 만든 영상이 없습니다</div>;
  return (
    <div className="pgrid">
      {projects.map((p) => {
        const [st, cls] = PSTATE[p.state] || [p.state, ""];
        const date = new Date(p.mtime * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
        const thumb = fileUrl(p.thumbnail);
        return (
          <div className="pcard" key={p.id}>
            <div className="thumb" style={thumb ? { backgroundImage: `url('${thumb}')` } : undefined}
              onClick={() => openModal(<ProjectModal p={p} />)}>
              {!thumb && !p.video && "영상 없음"}
              {p.video && <div className="play"><PlayIcon /></div>}
            </div>
            <div className="pbody">
              <b title={p.title || p.topic}>{p.title || p.topic}</b>
              <div className="pmeta">
                <span className={`badge ${cls}`}>{st}</span>
                {p.failed_step && <span>{p.failed_step} 단계</span>}
                {p.video_url && <a className="yt" onClick={() => BrowserOpenURL(p.video_url)}>YouTube ↗</a>}
                <span>{date}</span>
                {p.size_mb > 0 && <span>{p.size_mb}MB</span>}
              </div>
              <div className="pact">
                {p.video && <button className="btn sm" onClick={() => openModal(<ProjectModal p={p} />)}>보기</button>}
                {p.state === "planned" && <button className="btn sm pri" onClick={() => makeFromBrief(p.id, p.topic)}>기획서로 제작</button>}
                {(p.state === "failed" || p.state === "incomplete") && <button className="btn sm pri" onClick={() => resumeProject(p.id)}>이어서 하기</button>}
                {p.video && p.state !== "running" && (
                  <button className="btn sm" onClick={() => openModal(<UploadModal p={p} />)}>{p.video_url ? "재업로드" : "업로드"}</button>
                )}
                <button className="btn sm ghost" onClick={() => openFolder(p.id)}>폴더</button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ProjectModal({ p }: { p: Project }) {
  const { closeModal, openFolder, toast } = useStore();
  const copy = async () => {
    await ClipboardSetText(`${p.title}\n\n${p.description}\n\n${(p.tags || []).join(", ")}`);
    toast("제목·설명·태그를 복사했습니다");
  };
  return (
    <div className="mbox">
      {p.video && <video src={fileUrl(p.video)} controls autoPlay poster={fileUrl(p.thumbnail) || undefined} />}
      <div className="mbody">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <h2 className="mtitle">{p.title || p.topic}</h2>
          <button className="btn sm ghost" onClick={closeModal}>닫기</button>
        </div>
        <div className="pmeta" style={{ margin: "8px 0 14px" }}>{p.id} · 주제: {p.topic}</div>
        {p.tags?.length > 0 && <div className="tags">{p.tags.map((t) => <span key={t}>#{t}</span>)}</div>}
        {p.description && (<><div className="lbl">설명</div><div className="desc">{p.description}</div></>)}
        {!p.video && p.completed_steps.length > 0 && <div className="hint">완료된 단계: {p.completed_steps.join(", ")}</div>}
        <div className="row" style={{ marginTop: 16, flexWrap: "wrap" }}>
          {p.description && <button className="btn sm" onClick={copy}>제목·설명 복사</button>}
          {p.video_url && <button className="btn sm" onClick={() => BrowserOpenURL(p.video_url)}>YouTube에서 보기</button>}
          <button className="btn sm ghost" onClick={() => openFolder(p.id)}>폴더 열기</button>
        </div>
      </div>
    </div>
  );
}

function UploadModal({ p }: { p: Project }) {
  const { closeModal, toast, status, setTab, refreshJobs } = useStore();
  const [privacy, setPrivacy] = useState("private");
  const [schedule, setSchedule] = useState("");
  const upload = async () => {
    try {
      await api(`/api/projects/${encodeURIComponent(p.id)}/upload`, { body: { privacy, schedule } });
      closeModal();
      toast("업로드를 시작합니다");
      setTab("new");
      refreshJobs();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };
  return (
    <div className="mbox narrow">
      <div className="mbody">
        <h2 className="mtitle" style={{ marginBottom: 6 }}>YouTube 업로드</h2>
        <div className="pmeta" style={{ marginBottom: 18 }}>{p.title || p.topic}</div>
        {!status?.keys.YOUTUBE_CLIENT_ID && <div className="hint warn">설정에서 YouTube Client ID/Secret을 먼저 입력하세요.</div>}
        <div className="field">
          <div className="lbl">공개 상태</div>
          <select value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
            <option value="private">비공개</option>
            <option value="unlisted">일부 공개</option>
            <option value="public">공개</option>
          </select>
        </div>
        <div className="field">
          <div className="lbl">예약 발행 <span>비우면 즉시 · 예약 시 비공개로 올라간 뒤 공개</span></div>
          <input type="time" value={schedule} onChange={(e) => setSchedule(e.target.value)} />
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn ghost" onClick={closeModal}>취소</button>
          <button className="btn pri" onClick={upload}>업로드</button>
        </div>
      </div>
    </div>
  );
}
