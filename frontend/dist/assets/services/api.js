export class ApiError extends Error {
    constructor(status, code, message) {
        super(message);
        this.status = status;
        this.code = code;
    }
}
async function req(method, path, body, headers = {}) {
    let resp;
    try {
        resp = await fetch(path, {
            method,
            headers: { ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
            body: body ? JSON.stringify(body) : undefined,
        });
    }
    catch {
        throw new ApiError(0, "network", "Server unreachable");
    }
    const text = await resp.text();
    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    }
    catch {
        data = {};
    }
    if (!resp.ok)
        throw new ApiError(resp.status, data.error || "http_error", data.message || resp.statusText);
    return data;
}
const qs = (params) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params))
        if (v !== undefined && v !== null && v !== "")
            q.set(k, String(v));
    const s = q.toString();
    return s ? `?${s}` : "";
};
export const api = {
    health: () => req("GET", "/api/health"),
    config: () => req("GET", "/api/config"),
    status: () => req("GET", "/api/session/status"),
    dashboard: () => req("GET", "/api/dashboard"),
    createSession: (language, mode) => req("POST", "/api/sessions", { language, consent: true, mode }),
    getSession: (id, token) => req("GET", `/api/sessions/${encodeURIComponent(id)}`, undefined, { "X-Session-Token": token }),
    visits: (f = {}) => req("GET", `/api/visits${qs({ ...f })}`),
    exportUrl: (f = {}) => `/api/visits/export.csv${qs({ ...f })}`,
    visit: (id) => req("GET", `/api/visits/${encodeURIComponent(id)}`),
    followups: (status = "PENDING") => req("GET", `/api/followups?status=${status}`),
    setFollowup: (id, status) => req("POST", `/api/followups/${encodeURIComponent(id)}/status`, { status }),
    beneficiaries: () => req("GET", "/api/beneficiaries"),
    beneficiary: (id) => req("GET", `/api/beneficiaries/${encodeURIComponent(id)}`),
    referrals: () => req("GET", "/api/referrals"),
    reports: (from, to) => req("GET", `/api/reports${qs({ from, to })}`),
    metrics: () => req("GET", "/api/metrics"),
    deleteDemo: () => req("POST", "/api/demo-data/delete", { confirm: "DELETE" }),
    seedDemo: (reset) => req("POST", "/api/demo-data/seed", { reset }),
};
