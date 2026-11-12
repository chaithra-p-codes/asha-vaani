const get = (k) => {
    try {
        return localStorage.getItem(k);
    }
    catch {
        return null;
    }
};
const set = (k, v) => {
    try {
        if (v === null)
            localStorage.removeItem(k);
        else
            localStorage.setItem(k, v);
    }
    catch { /* unavailable */ }
};
export const store = {
    config: null,
    service: "checking",
    bargeIn: get("asha.bargein") !== "off",
};
export const prefs = {
    onboarded: () => get("asha.onboarded") === "1",
    setOnboarded: (on) => set("asha.onboarded", on ? "1" : null),
    workerName: () => (get("asha.workerName") || "").trim(),
    setWorkerName: (name) => set("asha.workerName", name.trim().slice(0, 40) || null),
    speechLang: () => {
        const v = get("asha.speechLang");
        return v === "hi" || v === "kn" || v === "en" ? v : "en";
    },
    setSpeechLang: (l) => set("asha.speechLang", l),
};
export function setBargeIn(on) {
    store.bargeIn = on;
    set("asha.bargein", on ? "on" : "off");
}
export function saveActiveSession(s) {
    try {
        if (s)
            sessionStorage.setItem("asha.session", JSON.stringify(s));
        else {
            sessionStorage.removeItem("asha.session");
            sessionStorage.removeItem("asha.resume");
        }
    }
    catch { /* storage unavailable */ }
}
export function activeSession() {
    try {
        const raw = sessionStorage.getItem("asha.session");
        return raw ? JSON.parse(raw) : null;
    }
    catch {
        return null;
    }
}
/** Service status used by the shell and pages. "live" only when the server says a Gnani key is set. */
export function serviceFromConfig(cfg) {
    if (!cfg)
        return "offline";
    return cfg.gnani_configured ? "live" : "demo";
}
