/** ASHA Vaani entry: history router, persistent app shell, onboarding gate, service worker. */
import { mountShell } from "./components/shell.js";
import { emptyState } from "./components/states.js";
import { lang, setLang, tr } from "./i18n.js";
import { renderBeneficiaries, renderBeneficiary } from "./pages/beneficiaries.js";
import { renderFollowups } from "./pages/followups.js";
import { renderLanding } from "./pages/landing.js";
import { renderOnboarding } from "./pages/onboarding.js";
import { renderOverview } from "./pages/overview.js";
import { renderReferrals } from "./pages/referrals.js";
import { renderReports } from "./pages/reports.js";
import { renderSettings } from "./pages/settings.js";
import { renderVisitDetail, renderVisits } from "./pages/visits.js";
import { renderWorkspace } from "./pages/workspace.js";
import { current, navigate, startRouter } from "./router.js";
import { api } from "./services/api.js";
import { prefs, serviceFromConfig, store } from "./store.js";
import { html, raw } from "./ui/dom.js";
let root = document.getElementById("app");
let shell = null;
let cleanup;
const NAV_FOR = {
    overview: "overview", "new-visit": "new-visit", beneficiaries: "beneficiaries", beneficiary: "beneficiaries",
    visits: "visits", visit: "visits", followups: "followups", referrals: "referrals", reports: "reports", settings: "settings",
};
const TITLE = {
    overview: () => tr("nav_overview"), "new-visit": () => tr("nav_new_visit"), beneficiaries: () => tr("nav_beneficiaries"),
    beneficiary: () => tr("nav_beneficiaries"), visits: () => tr("nav_visits"), visit: () => tr("nav_visits"),
    followups: () => tr("nav_followups"), referrals: () => tr("nav_referrals"), reports: () => tr("nav_reports"),
    settings: () => tr("nav_settings"), onboarding: () => tr("onb1_title"),
};
/** Replace the top-level root so listeners from the previous page never leak. */
function freshRoot() {
    const fresh = root.cloneNode(false);
    root.replaceWith(fresh);
    root = fresh;
    return fresh;
}
function rerender() {
    shell = null;
    void route(current());
}
async function route(r) {
    if (cleanup) {
        try {
            cleanup();
        }
        catch { /* page teardown must not block navigation */ }
        cleanup = undefined;
    }
    document.title = r.name === "landing" ? `ASHA Vaani: ${tr("tagline")}` : `${(TITLE[r.name] || (() => ""))()} | ASHA Vaani`;
    const keepScroll = r.name === "landing" && location.hash.length > 1;
    if (!keepScroll)
        window.scrollTo(0, 0);
    if (r.name === "landing") {
        shell = null;
        const el = freshRoot();
        cleanup = renderLanding(el, rerender);
        return;
    }
    if (r.name === "onboarding") {
        shell = null;
        const el = freshRoot();
        cleanup = renderOnboarding(el, r.query.get("next") || "/app");
        return;
    }
    if (r.name === "not-found") {
        shell = null;
        const el = freshRoot();
        el.innerHTML = html `<div class="onb"><div class="onb-card">${raw(emptyState("404", "info", html `<a class="btn btn-primary" href="/app">${tr("nav_overview")}</a><a class="btn btn-ghost" href="/">ASHA Vaani</a>`))}</div></div>`;
        return;
    }
    // Every /app route: first-run users see onboarding once, then come back here.
    if (!prefs.onboarded()) {
        navigate(`/onboarding?next=${encodeURIComponent(r.path)}`, { replace: true });
        return;
    }
    if (!shell) {
        const el = freshRoot();
        shell = mountShell(el, rerender);
    }
    shell.setActive(NAV_FOR[r.name] || null);
    shell.refresh();
    const content = shell.freshContent();
    const refreshShell = () => shell?.refresh();
    switch (r.name) {
        case "overview":
            renderOverview(content);
            break;
        case "new-visit":
            cleanup = renderWorkspace(content, { refreshShell });
            break;
        case "beneficiaries":
            renderBeneficiaries(content, r);
            break;
        case "beneficiary":
            renderBeneficiary(content, r.id || "");
            break;
        case "visits":
            renderVisits(content, r);
            break;
        case "visit":
            renderVisitDetail(content, r.id || "");
            break;
        case "followups":
            renderFollowups(content, refreshShell);
            break;
        case "referrals":
            renderReferrals(content, refreshShell);
            break;
        case "reports":
            cleanup = renderReports(content, r);
            break;
        case "settings":
            cleanup = renderSettings(content, rerender, refreshShell);
            break;
        default: content.innerHTML = emptyState("404", "info");
    }
    if (document.activeElement && document.activeElement !== document.body && !content.contains(document.activeElement)) {
        content.focus({ preventScroll: true });
    }
}
async function boot() {
    setLang(lang());
    // Config decides whether live speech can start; the UI says "checking" until it answers.
    api.config().then((cfg) => { store.config = cfg; store.service = serviceFromConfig(cfg); })
        .catch(() => { store.service = "offline"; })
        .finally(() => { if (shell)
        shell.refresh(); });
    startRouter((r) => { void route(r); });
    if ("serviceWorker" in navigator && location.protocol !== "file:") {
        navigator.serviceWorker.register("/sw.js").catch(() => { });
    }
}
boot();
