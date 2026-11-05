import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";
import type { KeyInfo } from "../types";

export default function SettingsPage({ visible }: { visible: boolean }) {
  const { status, refreshStatus, toast } = useStore();
  const [keys, setKeys] = useState<KeyInfo[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [authing, setAuthing] = useState(false);

  const load = useCallback(async () => {
    try {
      setKeys(await api<KeyInfo[]>("/api/settings"));
    } catch (e) {
      toast((e as Error).message, true);
    }
  }, [toast]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  const save = async () => {
    const body = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v));
    if (!Object.keys(body).length) return toast("변경된 키가 없습니다");
    try {
      await api("/api/settings", { body });
      setValues({});
      toast("저장했습니다");
      await refreshStatus();
      load();
    } catch (e) {
      toast((e as Error).message, true);
    }
  };

  const auth = async () => {
    setAuthing(true);
    try {
      await api("/api/youtube/auth", { method: "POST" });
      toast("YouTube 인증 성공");
      await refreshStatus();
    } catch (e) {
      toast((e as Error).message, true);
    }
    setAuthing(false);
  };

  return (
    <div className="wrap">
      <div className="head">
        <div>
          <h1>설정</h1>
          <p>API 키는 이 컴퓨터의 <code>.env</code> 파일에만 저장됩니다.</p>
        </div>
      </div>
      <div className="card" style={{ marginBottom: 22 }}>
        <h3>API 키</h3>
        {keys.map((k) => (
          <div className="krow" key={k.key}>
            <div>
              {k.label}
              {k.required && <span className="req">필수</span>}
              <small>{k.usage}</small>
            </div>
            <input type="password" autoComplete="off" value={values[k.key] || ""}
              placeholder={k.set ? `${k.masked}  (변경하려면 새로 입력)` : "키를 입력하세요"}
              onChange={(e) => setValues((v) => ({ ...v, [k.key]: e.target.value }))} />
            <span className={`dot ${k.set ? "ok" : k.required ? "err" : ""}`} title={k.set ? "설정됨" : "없음"} />
          </div>
        ))}
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 14 }}>
          <button className="btn pri" onClick={save}>저장</button>
        </div>
      </div>
      <div className="card">
        <h3>YouTube 계정</h3>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div>
            <div className="row"><span className={`dot ${status?.youtube_token ? "ok" : ""}`} />{status?.youtube_token ? "인증 완료" : "아직 인증하지 않음"}</div>
            <div className="hint">버튼을 누르면 브라우저에서 Google 로그인 창이 열립니다. 최초 1회만 하면 됩니다.</div>
          </div>
          <button className="btn" onClick={auth} disabled={authing}>{authing ? "브라우저에서 로그인하세요…" : "YouTube 인증"}</button>
        </div>
      </div>
      {status && <div className="hint" style={{ marginTop: 18 }}>대본 모델: {status.model}</div>}
    </div>
  );
}
