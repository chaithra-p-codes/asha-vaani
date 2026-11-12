import { Key, Lang, tr, trf } from "../i18n.js";

const VT: Record<string, Record<Lang, string>> = {
  ANC: { en: "ANC", hi: "एएनसी (ANC)", kn: "ಎಎನ್‌ಸಿ (ANC)" },
  PNC: { en: "PNC", hi: "पीएनसी (PNC)", kn: "ಪಿಎನ್‌ಸಿ (PNC)" },
  NEWBORN: { en: "Newborn", hi: "नवजात शिशु", kn: "ನವಜಾತ ಶಿಶು" },
  IMMUNISATION: { en: "Immunisation", hi: "टीकाकरण", kn: "ಲಸಿಕಾಕರಣ" },
};
export const VISIT_TYPES = ["ANC", "PNC", "NEWBORN", "IMMUNISATION"] as const;

export function visitTypeLabel(vt: string | null | undefined, l: Lang): string {
  if (!vt) return "";
  return VT[vt]?.[l] || vt;
}

const CAT: Record<string, Key> = { pregnant: "cat_pregnant", postnatal: "cat_postnatal", newborn: "cat_newborn", infant: "cat_infant" };
export const CATEGORIES = Object.keys(CAT);
export function categoryLabel(c: string | null | undefined): string {
  return c && CAT[c] ? tr(CAT[c]) : c || "";
}

const LOCALE: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", kn: "kn-IN" };
export const locale = (l: Lang): string => LOCALE[l];

const asDate = (iso: string): Date => new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);

export function fmtDate(iso: string | null | undefined, l: Lang, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!iso) return "";
  const d = asDate(iso);
  if (isNaN(d.getTime())) return iso;
  try {
    return d.toLocaleDateString(LOCALE[l], { day: "numeric", month: "short", year: "numeric", ...opts });
  } catch {
    return iso.slice(0, 10);
  }
}

export function fmtShortDate(iso: string | null | undefined, l: Lang): string {
  return fmtDate(iso, l, { year: undefined });
}

export function fmtTime(iso: string | null | undefined, l: Lang): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  try {
    return d.toLocaleString(LOCALE[l], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function fmtClock(iso: string | null | undefined, l: Lang): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  try {
    return d.toLocaleTimeString(LOCALE[l], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

export function fmtLongToday(l: Lang): string {
  try {
    return new Date().toLocaleDateString(LOCALE[l], { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  } catch {
    return new Date().toDateString();
  }
}

/** Local calendar date as YYYY-MM-DD (not UTC, so late-evening visits land on the right day). */
export function localISO(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function addDays(iso: string, days: number): string {
  const d = asDate(iso);
  d.setDate(d.getDate() + days);
  return localISO(d);
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((asDate(toIso).getTime() - asDate(fromIso).getTime()) / 86400000);
}

export function fieldText(field: string, value: unknown, l: Lang): string {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) return "";
  switch (field) {
    case "weight_kg": return `${Number(value).toLocaleString(LOCALE[l], { maximumFractionDigits: 3 })} kg`;
    case "visit_type": return visitTypeLabel(String(value), l);
    case "ifa_tablets_given": return value ? tr("given", l) : tr("not_given", l);
    case "next_visit_date":
    case "visit_date": return fmtDate(String(value), l);
    default: return Array.isArray(value) ? value.join(", ") : String(value);
  }
}

/** Follow-up titles are written for speech ("P H C"); collapse spelled-out acronyms for the screen. */
export function displayText(s: string | null | undefined): string {
  return String(s || "").replace(/\b(?:[A-Z] ){1,5}[A-Z]\b/g, (m) => m.replace(/ /g, ""));
}

export function followupTitle(f: any, l: Lang): string {
  return displayText(f?.title_i18n?.[l] || f?.title || "");
}

export function greetingKey(): "greet_morning" | "greet_afternoon" | "greet_evening" {
  const h = new Date().getHours();
  return h < 12 ? "greet_morning" : h < 17 ? "greet_afternoon" : "greet_evening";
}

export function referralLabel(status: string | null | undefined): string {
  if (status === "REFER_NOW") return tr("ref_refer_now");
  if (status === "REVIEW_REQUIRED") return tr("ref_review");
  return tr("ref_none");
}

export function sourceLabel(source: string | null | undefined): string {
  if (source === "seed") return tr("src_seed");
  if (source === "demo") return tr("src_demo");
  return tr("src_live");
}

export function relatedVisitText(f: any, l: Lang): string {
  if (!f?.visit_type) return "";
  return trf("fu_related", { type: visitTypeLabel(f.visit_type, l), date: fmtShortDate(f.visit_date, l) });
}

export function initials(name: string | null | undefined): string {
  const parts = String(name || "").replace(/^Baby of\s+/i, "").split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] || "?").toUpperCase() + (parts[1]?.[0] || "").toUpperCase();
}

export function durationText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
