/** Overview (/app): greeting, live counts from /api/dashboard, recent activity, upcoming follow-ups. */
import { fmtLongToday, fmtShortDate, followupTitle, greetingKey, visitTypeLabel } from "../components/format.js";
import { pageHead } from "../components/shell.js";
import { confirmationBadge, demoBadge, emptyState, errorState, priorityBadge, referralBadge, skeletonRows, skeletonStats } from "../components/states.js";
import { lang, tr, trf } from "../i18n.js";
import { navigate } from "../router.js";
import { api } from "../services/api.js";
import { clearPending, loadPending } from "../services/pendingStore.js";
import { prefs, saveActiveSession } from "../store.js";
import { $, html, on, raw, setHTML } from "../ui/dom.js";
import { icon } from "../ui/icons.js";

export function renderOverview(root: HTMLElement): void {
  const l = lang();
  const name = prefs.workerName();
  const greet = name ? `${tr(greetingKey())}, ${name}` : tr(greetingKey());

  root.innerHTML = html`
    ${raw(pageHead(greet, fmtLongToday(l)))}
    <div id="pending"></div>
    <section class="stat-grid" id="stats" aria-label="${tr("ov_summary")}">${raw(skeletonStats())}</section>
    <div class="cta-row">
      <div><p class="h3">${tr("ov_cta_title")}</p><p>${tr("ov_cta_body")}</p></div>
      <a class="btn btn-lg" href="/app/new-visit">${raw(icon("mic"))}${tr("start_new_visit")}</a>
    </div>
    <div id="demo"></div>
    <div class="grid-2" style="margin-top:16px">
      <section class="panel flush" aria-labelledby="recent-h">
        <div class="panel-head"><h2 class="h3" id="recent-h">${tr("ov_recent")}</h2><a class="link small" href="/app/visits">${tr("view_all")}</a></div>
        <div class="panel-body" id="recent">${raw(skeletonRows(5))}</div>
      </section>
      <div style="display:grid;gap:16px">
        <section class="panel flush" aria-labelledby="up-h">
          <div class="panel-head"><h2 class="h3" id="up-h">${tr("ov_upcoming")}</h2><a class="link small" href="/app/follow-ups">${tr("view_all")}</a></div>
          <div class="panel-body" id="upcoming">${raw(skeletonRows(4))}</div>
        </section>
        <section class="panel" aria-labelledby="sum-h">
          <div class="panel-head"><h2 class="h3" id="sum-h">${tr("ov_summary")}</h2></div>
          <div class="panel-body"><dl class="kv num" id="summary">${raw(skeletonRows(3))}</dl></div>
        </section>
      </div>
    </div>
    <h2 class="h3 section-label">${tr("ov_quick")}</h2>
    <nav class="quick" aria-label="${tr("ov_quick")}">
      <a href="/app/beneficiaries">${raw(icon("search"))}${tr("qa_beneficiaries")}</a>
      <a href="/app/follow-ups">${raw(icon("calendarCheck"))}${tr("qa_due")}</a>
      <a href="/app/referrals">${raw(icon("referral"))}${tr("qa_referrals")}</a>
      <a href="/app/reports">${raw(icon("chart"))}${tr("qa_reports")}</a>
    </nav>`;

  const load = async () => {
    try {
      const d = await api.dashboard();
      setHTML($("#stats", root), html`
        <a class="stat" href="/app/visits"><span class="label">${raw(icon("records"))}${tr("ov_visits_today")}</span>
          <span class="value">${d.visits_today}</span><span class="note">${trf("ov_note_total", { n: d.visits_total })}</span></a>
        <a class="stat" href="/app/beneficiaries"><span class="label">${raw(icon("users"))}${tr("ov_beneficiaries")}</span>
          <span class="value">${d.total_beneficiaries}</span><span class="note">${tr("ov_note_registered")}</span></a>
        <a class="stat" href="/app/follow-ups"><span class="label">${raw(icon("calendarCheck"))}${tr("ov_pending")}</span>
          <span class="value">${d.pending_followups}</span><span class="note">${trf("ov_note_overdue", { n: d.overdue_followups })}</span></a>
        <a class="stat ${d.urgent_referrals ? "urgent" : ""}" href="/app/referrals"><span class="label">${raw(icon("alert"))}${tr("ov_urgent")}</span>
          <span class="value">${d.urgent_referrals}</span><span class="note">${tr("ov_note_open")}</span></a>`);

      if (d.demo_visits) {
        setHTML($("#demo", root), html`<p class="notice info" style="margin-top:12px">${raw(icon("info"))}<span>${trf("demo_notice", { n: d.demo_visits })}</span></p>`);
      }

      const rec = d.recent as any[];
      setHTML($("#recent", root), rec.length ? html`<div class="table-wrap"><table class="table stack">
        <thead><tr><th>${tr("col_beneficiary")}</th><th>${tr("col_type")}</th><th>${tr("col_date")}</th><th>${tr("col_status")}</th><th>${tr("col_referral")}</th></tr></thead>
        <tbody>${rec.map((v) => raw(html`<tr class="clickable" data-action="open" data-id="${v.id}" tabindex="0">
          <td class="primary" data-label="${tr("col_beneficiary")}"><span class="cell-main">${v.beneficiary_name || "—"}</span>
            <span class="cell-sub"><span class="mono-id">ID ${v.beneficiary_id}</span>${raw(demoBadge(v.source))}</span></td>
          <td data-label="${tr("col_type")}">${visitTypeLabel(v.visit_type, l)}</td>
          <td data-label="${tr("col_date")}" class="num">${fmtShortDate(v.visit_date, l)}</td>
          <td class="end" data-label="${tr("col_status")}">${raw(confirmationBadge(v.confirmation_status))}</td>
          <td data-label="${tr("col_referral")}">${raw(referralBadge(v.referral_status))}</td></tr>`))}</tbody></table></div>`
        : emptyState(tr("empty_recent"), "records", html`<a class="btn btn-primary" href="/app/new-visit">${raw(icon("mic"))}${tr("start_new_visit")}</a>`));

      const up = d.upcoming_followups as any[];
      setHTML($("#upcoming", root), up.length ? html`<ul class="rows">${up.map((f) => raw(html`<li>
        <a class="row-item" href="/app/beneficiaries/${f.beneficiary_id}"><span class="pri ${f.priority}"></span>
          <span class="grow"><span class="row-title">${f.beneficiary_name || "ID " + f.beneficiary_id}</span>
          <span class="row-sub">${followupTitle(f, l)}</span></span>
          <span class="row-meta"><span class="num small">${f.due_date ? fmtShortDate(f.due_date, l) : tr("no_date")}</span>${raw(priorityBadge(f.priority))}</span>
          ${raw(icon("chevronRight"))}</a></li>`))}</ul>`
        : emptyState(tr("empty_upcoming"), "calendarCheck"));

      setHTML($("#summary", root), html`
        <dt>${tr("sum_visits")}</dt><dd>${d.visits_today}</dd>
        <dt>${tr("sum_due")}</dt><dd>${d.due_today_followups}</dd>
        <dt>${tr("sum_overdue")}</dt><dd class="${d.overdue_followups ? "warn-t" : ""}">${d.overdue_followups}</dd>
        <dt>${tr("sum_referrals")}</dt><dd class="${d.referrals_today ? "danger-t" : ""}">${d.referrals_today}</dd>`);
    } catch {
      setHTML($("#stats", root), "");
      setHTML($("#recent", root), errorState());
      setHTML($("#upcoming", root), "");
      setHTML($("#summary", root), "");
    }
    const p = await loadPending();
    if (p) {
      setHTML($("#pending", root), html`<div class="notice" style="margin-bottom:16px">${raw(icon("clock"))}<div class="grow">
        <b>${tr("pending_drafts")}</b><br><span class="small">${tr("pending_drafts_body")}</span></div>
        <div class="chips"><button class="btn" data-action="resume">${tr("resume")}</button>
        <button class="btn btn-ghost" data-action="discard">${tr("discard")}</button></div></div>`);
    }
  };

  on(root, "click", async (action, el) => {
    if (action === "open") navigate(`/app/visits/${el.dataset.id}`);
    else if (action === "reload") void load();
    else if (action === "resume") {
      const p = await loadPending();
      if (p) {
        saveActiveSession({ session_id: p.session_id, token: p.token, ws_path: "", mode: p.mode as any, language: p.language });
        sessionStorage.setItem("asha.resume", "1");
        navigate("/app/new-visit");
      }
    } else if (action === "discard") {
      await clearPending();
      setHTML($("#pending", root), "");
    }
  });
  root.addEventListener("keydown", (ev) => {
    const tr_ = (ev.target as HTMLElement).closest("tr[data-action=open]") as HTMLElement | null;
    if (tr_ && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); navigate(`/app/visits/${tr_.dataset.id}`); }
  });
  void load();
}
