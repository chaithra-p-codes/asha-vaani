/** App state and per-device preferences. The active visit session survives a page refresh via
 * sessionStorage (the server keeps the encrypted draft and requires re-confirmation on resume).
 * Preferences live in localStorage on this device only; nothing here is sent to the server. */
import type { Lang } from "./i18n.js";
import type { SessionInfo } from "./services/api.js";

const get = (k: string): string | null => {
  try { return localStorage.getItem(k); } catch { return null; }
};
const set = (k: string, v: string | null): void => {
  try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* unavailable */ }
};

export type ServiceState = "checking" | "live" | "demo" | "offline";

export const store = {
  config: null as any,
  service: "checking" as ServiceState,
  bargeIn: get("asha.bargein") !== "off",
};

export const prefs = {
  onboarded: (): boolean => get("asha.onboarded") === "1",
  setOnboarded: (on: boolean): void => set("asha.onboarded", on ? "1" : null),
  workerName: (): string => (get("asha.workerName") || "").trim(),
  setWorkerName: (name: string): void => set("asha.workerName", name.trim().slice(0, 40) || null),
  speechLang: (): Lang => {
    const v = get("asha.speechLang");
    return v === "hi" || v === "kn" || v === "en" ? v : "en";
  },
  setSpeechLang: (l: Lang): void => set("asha.speechLang", l),
};

export function setBargeIn(on: boolean): void {
  store.bargeIn = on;
  set("asha.bargein", on ? "on" : "off");
}

export function saveActiveSession(s: SessionInfo | null): void {
  try {
    if (s) sessionStorage.setItem("asha.session", JSON.stringify(s));
    else {
      sessionStorage.removeItem("asha.session");
      sessionStorage.removeItem("asha.resume");
    }
  } catch { /* storage unavailable */ }
}

export function activeSession(): SessionInfo | null {
  try {
    const raw = sessionStorage.getItem("asha.session");
    return raw ? (JSON.parse(raw) as SessionInfo) : null;
  } catch {
    return null;
  }
}

/** Service status used by the shell and pages. "live" only when the server says a Gnani key is set. */
export function serviceFromConfig(cfg: any | null): ServiceState {
  if (!cfg) return "offline";
  return cfg.gnani_configured ? "live" : "demo";
}
