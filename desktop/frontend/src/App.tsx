import { useEffect, useState } from "react";
import { ChooseRoot, GetBackend, Restart } from "../wailsjs/go/main/App";
import { api, setBackend } from "./api";
import { Icon } from "./Icon";
import { isActive, StoreProvider, useStore, type Page } from "./store";
import type { Backend, Meta } from "./types";
import MakePage from "./pages/MakePage";
import PlanPage from "./pages/PlanPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  const [boot, setBoot] = useState<{ state: "loading" | "error" | "ready"; error?: string; root?: string }>({ state: "loading" });
  const [meta, setMeta] = useState<Meta | null>(null);

  const connect = async (getter: () => Promise<Backend>) => {
    setBoot({ state: "loading" });
    try {
      const b = await getter();
      if (b.error) return setBoot({ state: "error", error: b.error, root: b.root });
      setBackend(b);
      setMeta(await api<Meta>("/api/meta"));
      setBoot({ state: "ready" });
    } catch (e) {
      setBoot({ state: "error", error: (e as Error).message });
    }
  };

  useEffect(() => {
    connect(GetBackend);
  }, []);

  if (boot.state !== "ready" || !meta) {
    return (
      <div className="boot">
        <div className="logo big"><Icon name="logo" size={28} /></div>
        {boot.state === "loading" ? (
          <>
            <div className="typing">영상 엔진을 시작하는 중…</div>
            <div className="hint">처음 실행할 때는 10~20초 정도 걸릴 수 있습니다.</div>
          </>
        ) : (
          <>
            <h2>시작하지 못했습니다</h2>
            <pre className="boot-err">{boot.error}</pre>
            {boot.root && <div className="hint">프로젝트 폴더: {boot.root}</div>}
            <div className="row" style={{ marginTop: 18 }}>
              <button className="btn pri" onClick={() => connect(Restart)}>다시 시도</button>
              <button className="btn" onClick={() => connect(ChooseRoot)}>폴더 선택</button>
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <StoreProvider meta={meta}>
      <Shell />
    </StoreProvider>
  );
}

const NAV: { page: Page; label: string; icon: string }[] = [
  { page: "make", label: "영상 생성", icon: "pen" },
  { page: "plan", label: "AI 기획실", icon: "chat" },
  { page: "settings", label: "설정", icon: "sliders" },
];

function Shell() {
  const { page, go, jobs, projects, status } = useStore();
  const active = jobs.filter(isActive).length;
  const k = status?.keys || {};
  const tts = k.OPENAI_API_KEY ? "OpenAI" : k.ELEVENLABS_API_KEY ? "ElevenLabs" : "Edge (무료)";

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="logo"><Icon name="logo" size={20} /></div>
          <div><b>Movie Maker</b><small>AI 유튜브 영상 자동 제작</small></div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <button key={n.page} className={page === n.page ? "on" : ""} onClick={() => go(n.page)}>
              <Icon name={n.icon} size={18} />
              <span>{n.label}</span>
              {n.page === "make" && <em className="cnt">{active || projects.length || ""}</em>}
            </button>
          ))}
        </nav>
        <div className="engine">
          <div className="t">AI 엔진</div>
          <div className="row"><span className={`dot ${k.ANTHROPIC_API_KEY ? "ok" : "err"}`} />Claude {k.ANTHROPIC_API_KEY ? "연결됨" : "키 없음"}</div>
          <div className="row"><span className={`dot ${k.GEMINI_API_KEY ? "ok" : "err"}`} />Gemini {k.GEMINI_API_KEY ? "연결됨" : "키 없음"}</div>
          <div className="row"><span className="dot ok" />음성: {tts}</div>
        </div>
      </aside>
      <main className="main">
        {/* 화면 전환 시 기획 대화 등 상태가 유지되도록 모두 마운트해 두고 숨김 처리 */}
        <div className={page === "make" ? "" : "hide"}><MakePage /></div>
        <div className={page === "plan" ? "" : "hide"}><PlanPage /></div>
        <div className={page === "settings" ? "" : "hide"}><SettingsPage visible={page === "settings"} /></div>
      </main>
    </div>
  );
}
