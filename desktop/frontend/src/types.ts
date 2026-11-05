export type Backend = { url: string; token: string; root: string; error: string };

export type Style = { id: string; name: string; description: string; best_for: string };

export type Meta = {
  styles: Style[];
  default_style: string;
  tts_default: string;
  voices: Record<string, [string, string][]>;
  voice_default: Record<string, string>;
};

export type Status = {
  keys: Record<string, boolean>;
  ffmpeg: boolean;
  youtube_token: boolean;
  model: string;
};

export type StepState = "pending" | "running" | "done" | "skipped" | "failed";

export type Job = {
  id: string;
  kind: "new" | "resume" | "upload";
  topic: string;
  project_id: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  steps: { name: string; label: string; state: StepState }[];
  logs: string[];
  current: string;
  error: string;
  started: number | null;
  finished: number | null;
};

export type Brief = {
  title?: string;
  angle?: string;
  hook?: string;
  target_audience?: string;
  visual_style?: { name: string };
  chapters?: { chapter_number: number; chapter_title: string }[];
  seo_keywords?: string[];
};

export type Project = {
  id: string;
  topic: string;
  title: string;
  description: string;
  tags: string[];
  state: "done" | "running" | "failed" | "incomplete" | "planned";
  failed_step: string;
  completed_steps: string[];
  video: string;
  thumbnail: string;
  video_url: string;
  has_brief: boolean;
  brief: Brief;
  mtime: number;
  size_mb: number;
};

export type KeyInfo = { key: string; label: string; usage: string; required: boolean; set: boolean; masked: string };

export type FormOptions = {
  style: string;
  length: string;
  tts: string;
  voice: string;
  i2v: boolean;
  capcut: boolean;
  upload: boolean;
  privacy: string;
  schedule: string;
};
