import DOMPurify from "dompurify";
import { marked } from "marked";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import type { Brief } from "../types";

type Msg = { role: "user" | "ai"; text: string };

const renderMd = (t: string) => ({ __html: DOMPurify.sanitize(marked.parse(t, { async: false }) as string) });

export default function PlanPage() {
  const { meta, toast, makeFromBrief, refreshProjects } = useStore();
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("");
  const [sid, setSid] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState("");
  const [input, setInput] = useState("");
  const [brief, setBrief] = useState<{ project_id: string; brief: Brief } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const briefRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, busy]);
  useEffect(() => {
    if (brief) briefRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [brief]);

  const add = (m: Msg) => setMsgs((x) => [...x, m]);

  const start = async () => {
    const t = topic.trim();
    if (!t) return toast("주제를 입력하세요", true);
    const st = meta.styles.find((s) => s.id === style);
    setStarted(true);
    setMsgs([{ role: "user", text: `주제: ${t}${st ? `\n스타일: ${st.name}` : ""}` }]);
    setBrief(null);
    setBusy("트렌드 분석과 기획안 3개를 만드는 중… (30초~1분)");
    try {
      const r = await api<{ sid: string; reply: string }>("/api/plan/start", { body: { topic: t, style } });
      setSid(r.sid);
      add({ role: "ai", text: r.reply });
    } catch (e) {
      add({ role: "ai", text: "⚠️ " + (e as Error).message });
    }
    setBusy("");
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy || !sid) return;
    setInput("");
    add({ role: "user", text });
    setBusy("답변 작성 중…");
    try {
      const r = await api<{ reply: string }>(`/api/plan/${sid}/message`, { body: { text } });
      add({ role: "ai", text: r.reply });
    } catch (e) {
      add({ role: "ai", text: "⚠️ " + (e as Error).message });
    }
    setBusy("");
  };

  const finalize = async () => {
    if (!sid || busy) return;
    setBusy("최종 기획서를 정리하는 중…");
    try {
      const r = await api<{ project_id: string; brief: Brief }>(`/api/plan/${sid}/finalize`, { method: "POST" });
      setBrief(r);
      refreshProjects();
    } catch (e) {
      toast((e as Error).message, true);
    }
    setBusy("");
  };

  const reset = () => {
    setSid(null);
    setStarted(false);
    setMsgs([]);
    setBrief(null);
    setTopic("");
  };

  return (
    <div className="wrap">
      <div className="head">
        <div>
          <h1>AI 기획실</h1>
          <p>AI PD와 대화하며 기획안을 다듬고, 확정한 기획서로 영상을 만듭니다.</p>
        </div>
        <button className="btn" onClick={reset} disabled={!!busy}>새 기획</button>
      </div>

      {!started ? (
        <div className="card" style={{ maxWidth: 720 }}>
          <div className="field">
            <div className="lbl">주제</div>
            <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="예: AI 시대 자녀교육"
              onKeyDown={(e) => e.key === "Enter" && !e.nativeEvent.isComposing && start()} />
          </div>
          <div className="field">
            <div className="lbl">그림 스타일 <span>기획서에 함께 저장됩니다</span></div>
            <div className="style-list">
              {[{ id: "", name: "선택 안 함", description: "config.yaml 기본 스타일", best_for: "" }, ...meta.styles].map((s) => (
                <button key={s.id} className={`style-opt ${style === s.id ? "on" : ""}`} onClick={() => setStyle(s.id)}>
                  <b>{s.name}</b>
                  <small>{s.description}{s.best_for && ` · ${s.best_for}`}</small>
                </button>
              ))}
            </div>
          </div>
          <button className="btn pri big" onClick={start}>리서치 + 기획안 3개 받기</button>
        </div>
      ) : (
        <>
          <div className="chat">
            {msgs.map((m, i) =>
              m.role === "ai"
                ? <div key={i} className="msg ai" dangerouslySetInnerHTML={renderMd(m.text)} />
                : <div key={i} className="msg user">{m.text}</div>,
            )}
            {busy && <div className="typing">{busy}</div>}
            <div ref={endRef} />
          </div>

          {brief && (
            <div className="card brief" style={{ marginTop: 18 }} ref={briefRef}>
              <h3>최종 기획서 · {brief.project_id}</h3>
              <dl>
                <dt>제목</dt><dd><b>{brief.brief.title}</b></dd>
                <dt>앵글</dt><dd>{brief.brief.angle}</dd>
                <dt>후킹</dt><dd>{brief.brief.hook}</dd>
                <dt>타겟</dt><dd>{brief.brief.target_audience}</dd>
                {brief.brief.visual_style && (<><dt>스타일</dt><dd>{brief.brief.visual_style.name}</dd></>)}
                <dt>챕터</dt>
                <dd>{(brief.brief.chapters || []).map((c) => <div key={c.chapter_number}>{c.chapter_number}. {c.chapter_title}</div>)}</dd>
                <dt>키워드</dt><dd>{(brief.brief.seo_keywords || []).join(", ")}</dd>
              </dl>
              <div className="hint" style={{ marginTop: 14 }}>음성·옵션은 '영상 생성' 화면의 현재 설정을 사용합니다.</div>
              <div className="row" style={{ marginTop: 14 }}>
                <button className="btn pri" onClick={() => makeFromBrief(brief.project_id, topic)}>이 기획서로 영상 만들기</button>
              </div>
            </div>
          )}

          <div className="composer">
            <textarea value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="피드백을 입력하세요. 예: 2번 기획안으로 가되 후킹을 더 강하게 (Enter 전송, Shift+Enter 줄바꿈)"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send();
                }
              }} />
            <div className="composer-btns">
              <button className="btn pri" onClick={send} disabled={!!busy || !sid}>보내기</button>
              <button className="btn" onClick={finalize} disabled={!!busy || !sid}>기획서 확정</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
