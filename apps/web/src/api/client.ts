/* Thin typed client over the NIS REST API. Errors are RFC 9457 Problem Details. */

export class ApiError extends Error {
  status: number;
  type: string;
  body: Record<string, unknown>;
  constructor(status: number, body: Record<string, unknown>) {
    super(String(body.detail || body.title || `HTTP ${status}`));
    this.status = status;
    this.type = String(body.type || "about:blank");
    this.body = body;
  }
}

const TOKEN_KEY = "nis.token";
let token: string | null = (() => {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
})();
const listeners = new Set<() => void>();

export function getToken() {
  return token;
}
export function setToken(t: string | null, remember = false) {
  token = t;
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
    if (t) (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, t);
  } catch {
    /* storage unavailable: token lives in memory only */
  }
  listeners.forEach((l) => l());
}
export function onAuthChange(fn: () => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

type Opts = { method?: string; body?: unknown; headers?: Record<string, string>; form?: FormData; raw?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && token) setToken(null);
  if (!res.ok) {
    let data: Record<string, unknown> = {};
    try {
      data = await res.json();
    } catch {
      data = { title: res.statusText };
    }
    throw new ApiError(res.status, data);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function download(path: string, method = "GET") {
  const res = await api<Response>(path, { method, raw: true });
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : "download";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function uid() {
  return (crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`).replace(/-/g, "").slice(0, 32);
}
