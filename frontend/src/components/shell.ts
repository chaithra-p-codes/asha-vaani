/** App shell: desktop sidebar + top utility bar, mobile header + bottom nav with a "More" sheet.
 * The shell stays mounted across /app routes; only the content element is replaced per page. */
import { Lang, LANGUAGES, lang, setLang, tr } from "../i18n.js";
import { api } from "../services/api.js";
import { serviceFromConfig, store } from "../store.js";
import { esc, html, raw } from "../ui/dom.js";
import { logo, icon, IconName } from "../ui/icons.js";

export type NavName = "overview" | "new-visit" | "beneficiaries" | "visits" | "followups" | "referrals" | "reports" | "settings";

const NAV: { name: NavName; href: string; ic: IconName; label: () => string }[] = [
  { name: "overview", href: "/app", ic: "overview", label: () => tr("nav_overview") },
  { name: "new-visit", href: "/app/new-visit", ic: "mic", label: () => tr("nav_new_visit") },
  { name: "beneficiaries", href: "/app/beneficiaries", ic: "users", label: () => tr("nav_beneficiaries") },
  { name: "visits", href: "/app/visits", ic: "records", label: () => tr("nav_visits") },
  { name: "followups", href: "/app/follow-ups", ic: "calendarCheck", label: () => tr("nav_followups") },
  { name: "referrals", href: "/app/referrals", ic: "referral", label: () => tr("nav_referrals") },
  { name: "reports", href: "/app/reports", ic: "chart", label: () => tr("nav_reports") },
  { name: "settings", href: "/app/settings", ic: "settings", label: () => tr("nav_settings") },
];
const MOBILE_PRIMARY: NavName[] = ["overview", "beneficiaries", "new-visit", "followups"];

export interface Shell {
  el: HTMLElement;
  content(): HTMLElement;
  freshContent(): HTMLElement;
  setActive(name: NavName | null): void;
  refresh(): void;
}

export function langSelect(id: string): string {
  const l = lang();
  return html`<label class="sr-only" for="${id}">${tr("language")}</label>
    <select class="lang-select" id="${id}" data-lang-select>${LANGUAGES.map((x) =>
      raw(html`<option value="${x.code}" ${x.code === l ? raw("selected") : ""}>${x.label}</option>`))}</select>`;
}

export function mountShell(root: HTMLElement, onLangChange: () => void): Shell {
  let active: NavName | null = null;
  let counts = { followups: 0, referrals: 0 };

  const navLink = (n: (typeof NAV)[number]) => {
    const c = n.name === "followups" ? counts.followups : n.name === "referrals" ? counts.referrals : 0;
    return html`<a href="${n.href}" data-nav="${n.name}" ${n.name === active ? raw('aria-current="page"') : ""}>
      ${raw(icon(n.ic))}<span>${n.label()}</span>${c ? raw(html`<span class="count" aria-label="${c}">${c}</span>`) : ""}</a>`;
  };

  const svcPill = () => {
    const s = store.service;
    const [cls, text] = s === "live" ? ["ok", tr("svc_live")] : s === "demo" ? ["warn", tr("svc_demo_only")]
      : s === "offline" ? ["bad", tr("svc_offline")] : ["", tr("svc_checking")];
    return html`<span class="status-pill ${cls}" title="${text}"><span class="dot"></span><span class="txt">${text}</span></span>`;
  };

  root.innerHTML = html`<div class="app">
    <aside class="sidebar" aria-label="${tr("nav_main")}">
      <a class="wordmark" href="/">${raw(logo())}</a>
      <nav class="side-nav" id="side-nav"></nav>
      <div class="side-foot"><span><span class="badge demo">${tr("demo_data")}</span></span><p>${tr("prototype_note")}</p></div>
    </aside>
    <div class="main">
      <header class="topbar no-print"><span class="crumb" id="crumb"></span>
        <div class="right"><span id="svc"></span>${raw(langSelect("ui-lang"))}</div></header>
      <header class="m-header no-print"><a class="wordmark" href="/app">${raw(logo())}</a>
        <div class="right"><span id="svc-m"></span>${raw(langSelect("ui-lang-m"))}</div></header>
      <main class="content" id="content" tabindex="-1"></main>
    </div>
    <nav class="bottom-nav no-print" id="bottom-nav" aria-label="${tr("nav_main")}"></nav>
    <div class="more-sheet" id="more" aria-hidden="true"><div class="sheet" role="dialog" aria-modal="true" aria-label="${tr("nav_more")}">
      <div class="grab"></div><div id="more-links"></div></div></div>
  </div>`;
  const el = root.firstElementChild as HTMLElement;
  const q = <T extends HTMLElement>(sel: string) => el.querySelector(sel) as T;

  const drawNav = () => {
    q("#side-nav").innerHTML = NAV.map(navLink).join("");
    const bn = MOBILE_PRIMARY.map((n) => NAV.find((x) => x.name === n)!).map((n) => n.name === "new-visit"
      ? html`<a href="${n.href}" class="new-visit" data-nav="${n.name}" ${n.name === active ? raw('aria-current="page"') : ""}>
          <span class="ic">${raw(icon("mic"))}</span><span>${n.label()}</span></a>`
      : html`<a href="${n.href}" data-nav="${n.name}" ${n.name === active ? raw('aria-current="page"') : ""}>${raw(icon(n.ic))}<span>${n.label()}</span></a>`);
    const moreActive = active && !MOBILE_PRIMARY.includes(active);
    q("#bottom-nav").innerHTML = bn.join("") + html`<button type="button" data-more aria-haspopup="dialog" aria-expanded="false"
      ${moreActive ? raw('aria-current="page"') : ""}>${raw(icon("more"))}<span>${tr("nav_more")}</span></button>`;
    q("#more-links").innerHTML = NAV.filter((n) => !MOBILE_PRIMARY.includes(n.name)).map(navLink).join("");
    const crumb = NAV.find((n) => n.name === active);
    q("#crumb").textContent = crumb ? crumb.label() : "";
    q("#svc").innerHTML = svcPill();
    q("#svc-m").innerHTML = svcPill();
  };

  const sheet = q("#more");
  const openSheet = (open: boolean) => {
    sheet.classList.toggle("open", open);
    sheet.setAttribute("aria-hidden", String(!open));
    el.querySelector("[data-more]")?.setAttribute("aria-expanded", String(open));
    if (open) (sheet.querySelector("a") as HTMLElement | null)?.focus();
  };
  el.addEventListener("click", (ev) => {
    const t = ev.target as HTMLElement;
    if (t.closest("[data-more]")) { openSheet(!sheet.classList.contains("open")); return; }
    if (t === sheet || t.closest("#more a")) openSheet(false);
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && sheet.classList.contains("open")) openSheet(false); });
  el.addEventListener("change", (ev) => {
    const t = ev.target as HTMLSelectElement;
    if (t.matches("[data-lang-select]")) {
      setLang(t.value as Lang);
      drawNav();
      el.querySelectorAll<HTMLSelectElement>("[data-lang-select]").forEach((s) => { s.value = t.value; });
      onLangChange();
    }
  });

  let refreshing = false;
  const refresh = async () => {
    if (refreshing) return;
    refreshing = true;
    try {
      const [cfg, d] = await Promise.all([api.config(), api.dashboard()]);
      store.config = cfg;
      store.service = serviceFromConfig(cfg);
      counts = { followups: (d.overdue_followups || 0) + (d.due_today_followups || 0), referrals: d.urgent_referrals || 0 };
    } catch {
      store.service = "offline";
    } finally {
      refreshing = false;
      drawNav();
    }
  };

  drawNav();
  return {
    el,
    content: () => q("#content"),
    freshContent: () => {
      const old = q("#content");
      const fresh = old.cloneNode(false) as HTMLElement;
      old.replaceWith(fresh);
      return fresh;
    },
    setActive: (name) => {
      active = name;
      openSheet(false);
      drawNav();
    },
    refresh: () => { void refresh(); },
  };
}

/** Page header used inside the content area. */
export function pageHead(title: string, meta = "", actions = ""): string {
  return html`<div class="page-head"><div><h1 class="h1">${title}</h1>${meta ? raw(html`<p class="meta">${meta}</p>`) : ""}</div>
    ${actions ? raw(`<div class="chips">${actions}</div>`) : ""}</div>`;
}

export { esc };
