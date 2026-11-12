/** REST client. All requests are same-origin; the session token is sent as a header. */
export interface SessionInfo {
  session_id: string;
  token: string;
  ws_path: string;
  mode: "live" | "demo" | "diag";
  language: string;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function req<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method,
      headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", "Server unreachable");
  }
  const text = await resp.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = {}; }
  if (!resp.ok) throw new ApiError(resp.status, data.error || "http_error", data.message || resp.statusText);
  return data as T;
}

const qs = (params: Record<string, string | number | undefined | null>): string => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
};

export interface VisitFilters {
  q?: string; visit_type?: string; referral?: string; from?: string; to?: string; source?: string; limit?: number;
}

export const api = {
  health: () => req<any>("GET", "/api/health"),
  config: () => req<any>("GET", "/api/config"),
  status: () => req<any>("GET", "/api/session/status"),
  dashboard: () => req<any>("GET", "/api/dashboard"),
  createSession: (language: string, mode: string) =>
    req<SessionInfo>("POST", "/api/sessions", { language, consent: true, mode }),
  getSession: (id: string, token: string) => req<any>("GET", `/api/sessions/${encodeURIComponent(id)}`, undefined,
    { "X-Session-Token": token }),
  visits: (f: VisitFilters = {}) => req<any>("GET", `/api/visits${qs({ ...f })}`),
  exportUrl: (f: VisitFilters = {}) => `/api/visits/export.csv${qs({ ...f })}`,
  visit: (id: string) => req<any>("GET", `/api/visits/${encodeURIComponent(id)}`),
  followups: (status: "PENDING" | "DONE" | "ALL" = "PENDING") => req<any>("GET", `/api/followups?status=${status}`),
  setFollowup: (id: string, status: "PENDING" | "DONE") =>
    req<any>("POST", `/api/followups/${encodeURIComponent(id)}/status`, { status }),
  beneficiaries: () => req<any>("GET", "/api/beneficiaries"),
  beneficiary: (id: string) => req<any>("GET", `/api/beneficiaries/${encodeURIComponent(id)}`),
  referrals: () => req<any>("GET", "/api/referrals"),
  reports: (from: string, to: string) => req<any>("GET", `/api/reports${qs({ from, to })}`),
  metrics: () => req<any>("GET", "/api/metrics"),
  deleteDemo: () => req<any>("POST", "/api/demo-data/delete", { confirm: "DELETE" }),
  seedDemo: (reset: boolean) => req<any>("POST", "/api/demo-data/seed", { reset }),
};
