import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, store } from "./api";
import type { FormOptions, Job, Meta, Project, Status } from "./types";

export type Page = "make" | "plan" | "settings";
export type Tab = "new" | "list";

type Ctx = {
  meta: Meta;
  status: Status | null;
  jobs: Job[];
  projects: Project[];
  form: FormOptions;
  setForm: (patch: Partial<FormOptions>) => void;
  page: Page;
  go: (p: Page) => void;
  tab: Tab;
  setTab: (t: Tab) => void;
  toast: (msg: string, err?: boolean) => void;
  modal: ReactNode;
  openModal: (n: ReactNode) => void;
  closeModal: () => void;
  refreshStatus: () => Promise<void>;
  refreshProjects: () => Promise<Project[]>;
  refreshJobs: () => void;
  resumeProject: (id: string) => Promise<void>;
  makeFromBrief: (id: string, topic?: string) => Promise<void>;
  openFolder: (id: string) => Promise<void>;
};

const StoreCtx = createContext<Ctx | null>(null);
export const useStore = () => {
  const c = useContext(StoreCtx);
  if (!c) throw new Error("StoreProvider 밖에서 사용");
  return c;
};

export const isActive = (j: Job) => j.status === "queued" || j.status === "running";

export function StoreProvider({ meta, children }: { meta: Meta; children: ReactNode }) {
  const saved = store<Partial<FormOptions>>("form") || {};
  const [form, setFormState] = useState<FormOptions>({
    style: saved.style ?? "",
    length: saved.length || "normal",
    tts: saved.tts || meta.tts_default,
    voice: saved.voice || meta.voice_default[saved.tts || meta.tts_default] || "",
    i2v: !!saved.i2v,
    capcut: !!saved.capcut,
    upload: !!saved.upload,
    privacy: saved.privacy || "private",
    schedule: saved.schedule || "",
  });
  const setForm = useCallback((patch: Partial<FormOptions>) => {
    setFormState((f) => {
      const n = { ...f, ...patch };
      store("form", n);
      return n;
    });
  }, []);

  const [status, setStatus] = useState<Status | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [page, setPage] = useState<Page>("make");
  const [tab, setTab] = useState<Tab>("new");
  const [modal, setModal] = useState<ReactNode>(null);
  const [toastState, setToast] = useState<{ msg: string; err?: boolean; on: boolean }>({ msg: "", on: false });
  const toastTimer = useRef<number>(0);

  const toast = useCallback((msg: string, err?: boolean) => {
    setToast({ msg, err, on: true });
    clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast((t) => ({ ...t, on: false })), 3200);
  }, []);

  const go = useCallback((p: Page) => setPage(p), []);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api<Status>("/api/status"));
    } catch {
      /* 무시 */
    }
  }, []);

  const refreshProjects = useCallback(async () => {
    try {
      const p = await api<Project[]>("/api/projects");
      setProjects(p);
      return p;
    } catch {
      return [];
    }
  }, []);

  // 작업 목록 폴링: 진행 중이면 1.5초, 아니면 5초
  const pollTimer = useRef<number>(0);
  const lastActive = useRef(0);
  const poll = useCallback(async () => {
    clearTimeout(pollTimer.current);
    let next = 5000;
    try {
      const j = await api<Job[]>("/api/jobs");
      setJobs(j);
      const active = j.filter(isActive).length;
      if (active < lastActive.current) refreshProjects();
      lastActive.current = active;
      if (active) next = 1500;
    } catch {
      /* 무시 */
    }
    pollTimer.current = window.setTimeout(poll, next);
  }, [refreshProjects]);

  useEffect(() => {
    refreshStatus();
    refreshProjects();
    poll();
    const t = window.setInterval(refreshStatus, 30000);
    return () => {
      clearInterval(t);
      clearTimeout(pollTimer.current);
    };
  }, [refreshStatus, refreshProjects, poll]);

  const resumeProject = useCallback(
    async (id: string) => {
      try {
        await api(`/api/projects/${encodeURIComponent(id)}/resume`, { method: "POST" });
        toast("이어서 진행합니다");
        go("make");
        setTab("new");
        poll();
      } catch (e) {
        toast((e as Error).message, true);
      }
    },
    [toast, go, poll],
  );

  const makeFromBrief = useCallback(
    async (id: string, topic?: string) => {
      try {
        await api("/api/jobs", { body: { project_id: id, topics: [topic || ""], options: { ...form, style: "" } } });
        toast("기획서로 영상 제작을 시작합니다");
        go("make");
        setTab("new");
        poll();
      } catch (e) {
        toast((e as Error).message, true);
      }
    },
    [form, toast, go, poll],
  );

  const openFolder = useCallback(
    async (id: string) => {
      try {
        await api(`/api/projects/${encodeURIComponent(id)}/open`, { method: "POST" });
      } catch (e) {
        toast((e as Error).message, true);
      }
    },
    [toast],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setModal(null);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const value: Ctx = {
    meta, status, jobs, projects, form, setForm, page, go, tab, setTab, toast, modal,
    openModal: setModal, closeModal: () => setModal(null),
    refreshStatus, refreshProjects, refreshJobs: poll, resumeProject, makeFromBrief, openFolder,
  };

  return (
    <StoreCtx.Provider value={value}>
      {children}
      <div className={`modal ${modal ? "on" : ""}`} onClick={(e) => e.target === e.currentTarget && setModal(null)}>
        {modal}
      </div>
      <div className={`toast ${toastState.on ? "on" : ""} ${toastState.err ? "err" : ""}`}>{toastState.msg}</div>
    </StoreCtx.Provider>
  );
}
