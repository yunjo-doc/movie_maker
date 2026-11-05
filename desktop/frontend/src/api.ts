import type { Backend } from "./types";

let backend: Backend | null = null;

export function setBackend(b: Backend) {
  backend = b;
}

/** Python 서버의 파일 경로(/files/...)를 절대 URL로 */
export function fileUrl(path: string): string {
  return path && backend ? backend.url + path : "";
}

export async function api<T = unknown>(path: string, opt: { method?: string; body?: unknown } = {}): Promise<T> {
  if (!backend) throw new Error("백엔드가 준비되지 않았습니다");
  const r = await fetch(backend.url + path, {
    method: opt.method || (opt.body !== undefined ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", "X-Token": backend.token },
    body: opt.body !== undefined ? JSON.stringify(opt.body) : undefined,
  });
  let data: any = null;
  try {
    data = await r.json();
  } catch {
    /* 본문 없음 */
  }
  if (!r.ok) throw new Error((data && data.detail) || `오류 ${r.status}`);
  return data as T;
}

export function store<T>(key: string, value?: T): T | null {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem("mm_" + key) || "null");
    localStorage.setItem("mm_" + key, JSON.stringify(value));
  } catch {
    /* 저장소 사용 불가 */
  }
  return null;
}
