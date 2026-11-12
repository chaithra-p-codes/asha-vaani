/** Visit records (/app/visits) and record detail (/app/visits/:id).
 * Server records are all CONFIRMED (nothing unconfirmed is ever written to the register).
 * A draft kept on this device is listed separately as Draft or Pending sync, never mixed in. */
import { fmtClock, fmtDate, fmtShortDate, fmtTime, followupTitle, sourceLabel, VISIT_TYPES, visitTypeLabel } from "../components/format.js";
import { registerSheet } from "../components/recordCard.js";
import { pageHead } from "../components/shell.js";
import { confirmationBadge, demoBadge, emptyState, errorState, priorityBadge, referralBadge, skeletonRows } from "../components/states.js";
import { Key, LANGUAGES, lang, tr } from "../i18n.js";
import { navigate, Route, setQuery } from "../router.js";
import { api, VisitFilters } from "../services/api.js";
import { clearPending, loadPending, PendingDraft } from "../services/pendingStore.js";
import { saveActiveSession } from "../store.js";
import { $, html, on, raw, setHTML } from "../ui/dom.js";
import { icon } from "../ui/icons.js";

export function renderVisits(root: HTMLElement, route: Route): void {
  const l = lang();
  const f = {
    q: route.query.get("q") || "", visit_type: route.query.get("type") || "", referral: route.query.get("referral") || "",
    status: route.query.get("status") || "", from: route.query.get("from") || "", to: route.query.get("to") || "",
  };
  const filters = (): VisitFilters => ({ q: f.q, visit_type: f.visit_type, referral: f.referral, from: f.from, to: f.to });

  root.innerHTML = html`${raw(pageHead(tr("nav_visits"), tr("vr_meta"), html`
      <a class="btn" id="csv" href="${api.exportUrl()}" download>${raw(icon("download"))}${tr("export_csv")}</a>
      <button class="btn" data-action="print">${raw(icon("printer"))}${tr("print_pdf")}</button>`))}
    <div class="toolbar no-print" role="search">
      <label class="search"><span class="sr-only">${tr("search")}</span>${raw(icon("search"))}
        <input class="input" id="q" type="search" inputmode="search" placeholder="${tr("search")}" value="${f.q}"></label>
      <label class="field"><span class="sr-only">${tr("col_type")}</span><select class="select" id="type">
        <option value="">${tr("type_all")}</option>${VISIT_TYPES.map((v) => raw(html`<option value="${v}" ${v === f.visit_type ? raw("selected") : ""}>${visitTypeLabel(v, l)}</option>`))}</select></label>
      <label class="field"><span class="sr-only">${tr("col_referral")}</span><select class="select" id="referral">
        ${([["", "ref_any"], ["ANY", "ref_only"], ["REFER_NOW", "ref_refer_now"], ["REVIEW_REQUIRED", "ref_review"], ["NONE", "ref_none"]] as [string, Key][]).map(([v, k]) =>
          raw(html`<option value="${v}" ${v === f.referral ? raw("selected") : ""}>${tr(k)}</option>`))}</select></label>
      <label class="field"><span class="sr-only">${tr("col_status")}</span><select class="select" id="status">
        ${([["", "status_all"], ["CONFIRMED", "st_confirmed"], ["DRAFT", "st_draft"], ["PENDING_SYNC", "st_pending_sync"]] as [string, Key][]).map(([v, k]) =>
          raw(html`<option value="${v}" ${v === f.status ? raw("selected") : ""}>${tr(k)}</option>`))}</select></label>
      <div class="date-range"><label class="field date-f"><span>${tr("from")}</span><input class="input" type="date" id="from" value="${f.from}"></label>
      <label class="field date-f"><span>${tr("to")}</span><input class="input" type="date" id="to" value="${f.to}"></label></div>
    </div>
    <div id="local"></div>
    <p class="small subtle" id="count" aria-live="polite"></p>
    <section class="panel flush" id="results">${raw(skeletonRows(8))}</section>`;

  const localRow = (p: PendingDraft) => {
    const status = p.kind === "sync" ? "PENDING_SYNC" : "DRAFT";
    if (f.status && f.status !== status) return "";
    return html`<section class="panel flush local" aria-labelledby="loc-h" style="margin-bottom:14px">
      <div class="panel-head"><h2 class="h3" id="loc-h">${tr("vr_local")}</h2></div>
      <ul class="rows"><li><div class="local-row">
        <span class="grow"><span class="row-title">${p.record?.beneficiary_name ? String(p.record.beneficiary_name) : ""}
          ${p.record?.beneficiary_id ? raw(html`<span class="mono-id">ID ${String(p.record.beneficiary_id)}</span>`) : raw(html`<span class="subtle">${tr("vr_unknown_id")}</span>`)}</span>
        <span class="row-sub">${visitTypeLabel(String(p.record?.visit_type || ""), l)} ${fmtTime(p.updated_at, l)}</span></span>
        ${raw(confirmationBadge(status))}
        <button class="btn" data-action="resume">${tr("resume")}</button>
        <button class="btn btn-ghost" data-action="discard">${tr("discard")}</button></div></li></ul></section>`;
  };

  const load = async () => {
    setQuery({ q: f.q, type: f.visit_type, referral: f.referral, status: f.status, from: f.from, to: f.to });
    ($("#csv", root) as HTMLAnchorElement).href = api.exportUrl(filters());
    const p = await loadPending();
    setHTML($("#local", root), p ? localRow(p) : "");
    if (f.status === "DRAFT" || f.status === "PENDING_SYNC") {
      $("#count", root)!.textContent = "";
      setHTML($("#results", root), "");
      if (!p) setHTML($("#results", root), emptyState(tr("no_visits"), "records"));
      return;
    }
    if (f.from && f.to && f.from > f.to) {
      setHTML($("#results", root), html`<p class="notice" style="margin:14px">${tr("rp_bad_range")}</p>`);
      return;
    }
    setHTML($("#results", root), skeletonRows(8));
    try {
      const { visits } = await api.visits(filters());
      const list = visits as any[];
      $("#count", root)!.textContent = list.length ? `${tr("results_n").replace("{n}", String(list.length))}` : "";
      setHTML($("#results", root), list.length ? html`<div class="table-wrap"><table class="table stack">
        <thead><tr><th>${tr("col_beneficiary")}</th><th>${tr("col_type")}</th><th>${tr("col_date")}</th><th>${tr("col_status")}</th><th>${tr("col_referral")}</th></tr></thead>
        <tbody>${list.map((v) => raw(html`<tr class="clickable" data-action="open" data-id="${v.id}" tabindex="0">
          <td class="primary" data-label="${tr("col_beneficiary")}"><span class="cell-main">${v.beneficiary_name || "—"}</span>
            <span class="cell-sub"><span class="mono-id">ID ${v.beneficiary_id}</span>${raw(demoBadge(v.source))}</span></td>
          <td data-label="${tr("col_type")}">${visitTypeLabel(v.visit_type, l)}</td>
          <td class="num" data-label="${tr("col_date")}">${fmtShortDate(v.visit_date, l)}</td>
          <td class="end" data-label="${tr("col_status")}">${raw(confirmationBadge(v.confirmation_status))}</td>
          <td data-label="${tr("col_referral")}">${raw(referralBadge(v.referral_status))}</td></tr>`))}</tbody></table></div>`
        : emptyState(tr("no_visits"), "records", html`<button class="btn" data-action="clear">${tr("clear_filters")}</button>`));
    } catch {
      setHTML($("#results", root), errorState());
    }
  };

  let debounce: number | undefined;
  $("#q", root)!.addEventListener("input", (e) => {
    f.q = (e.target as HTMLInputElement).value;
    window.clearTimeout(debounce);
    debounce = window.setTimeout(load, 250);
  });
  for (const id of ["type", "referral", "status", "from", "to"] as const) {
    $(`#${id}`, root)!.addEventListener("change", (e) => {
      const v = (e.target as HTMLInputElement).value;
      if (id === "type") f.visit_type = v; else (f as any)[id] = v;
      void load();
    });
  }
  on(root, "click", async (action, el) => {
    if (action === "open") navigate(`/app/visits/${el.dataset.id}`);
    else if (action === "reload") void load();
    else if (action === "print") window.print();
    else if (action === "clear") {
      Object.assign(f, { q: "", visit_type: "", referral: "", status: "", from: "", to: "" });
      for (const id of ["q", "type", "referral", "status", "from", "to"]) ($(`#${id}`, root) as HTMLInputElement).value = "";
      void load();
    } else if (action === "resume") {
      const p = await loadPending();
      if (p) {
        saveActiveSession({ session_id: p.session_id, token: p.token, ws_path: "", mode: p.mode as any, language: p.language });
        sessionStorage.setItem("asha.resume", "1");
        navigate("/app/new-visit");
      }
    } else if (action === "discard") { await clearPending(); setHTML($("#local", root), ""); }
  });
  root.addEventListener("keydown", (ev) => {
    const row = (ev.target as HTMLElement).closest("tr[data-action=open]") as HTMLElement | null;
    if (row && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); navigate(`/app/visits/${row.dataset.id}`); }
  });
  void load();
}

const EVENT_KEYS = new Set(["consent_given", "session_started", "field_corrected", "undo", "danger_review", "referral_alert",
  "danger_confirmed", "danger_denied", "id_from_register_confirmed", "save_failed", "session_resumed", "visit_saved",
  "barge_in", "advice_refused"]);
const QUIET_EVENTS = new Set(["turn", "llm_merge", "listen_timeout", "stt_unavailable", "tts_unavailable"]);

export function renderVisitDetail(root: HTMLElement, id: string): void {
  const l = lang();
  root.innerHTML = html`<a class="back-link no-print" href="/app/visits">${raw(icon("back"))}${tr("nav_visits")}</a>
    <div id="detail">${raw(skeletonRows(10))}</div>`;

  const load = async () => {
    let v: any;
    try {
      v = await api.visit(id);
    } catch (e: any) {
      setHTML($("#detail", root), e?.status === 404 ? emptyState(tr("vd_not_found"), "records") : errorState());
      return;
    }
    const pos = (v.danger_details || []).filter((d: any) => d.status === "POSITIVE");
    const rev = (v.danger_details || []).filter((d: any) => d.status === "REVIEW" || d.status === "UNCERTAIN");
    const meta = Object.fromEntries(Object.entries(v.field_confidence || {}).map(([k, c]) => [k, { confidence: c as string }]));
    const via = v.confirmed_via === "seed" ? tr("via_seed") : v.confirmed_via === "voice" ? tr("via_voice") : tr("via_button");
    const audit = ((v.audit || []) as any[]).filter((a) => !QUIET_EVENTS.has(a.event_type));
    const evLabel = (a: any) => {
      const base = EVENT_KEYS.has(a.event_type) ? tr(("ev_" + a.event_type) as Key) : tr("ev_other");
      const field = a.field_name ? `: ${tr(("f_" + a.field_name) as Key) || a.field_name}` : "";
      return base + field;
    };
    setHTML($("#detail", root), html`
      <div class="page-head"><div>
        <h1 class="h1">${v.beneficiary_name || "ID " + v.beneficiary_id}</h1>
        <p class="meta"><span class="mono-id">ID ${v.beneficiary_id}</span><span class="sep"></span>${visitTypeLabel(v.visit_type, l)}<span class="sep"></span><span class="num">${fmtDate(v.visit_date, l)}</span></p></div>
        <div class="chips">${raw(confirmationBadge(v.confirmation_status))}${raw(v.referral_status !== "NONE" ? referralBadge(v.referral_status) : "")}${raw(demoBadge(v.source))}</div>
      </div>
      <div class="chips no-print" style="margin:-6px 0 18px">
        <a class="btn" href="/app/beneficiaries/${v.beneficiary_id}">${raw(icon("user"))}${tr("view_beneficiary")}</a>
        <button class="btn" data-action="print">${raw(icon("printer"))}${tr("print_pdf")}</button></div>
      ${pos.length ? raw(html`<section class="danger-panel" role="alert" style="margin-bottom:16px"><p class="h3">${raw(icon("alert"))}${tr("danger_title")}</p>
        ${pos.map((d: any) => raw(html`<p>${d.label?.[l] || d.label?.en}</p><p class="why">${tr("danger_why")} ${d.rule_id}: ${tr("danger_heard")} “${d.matched_phrase}”</p>`))}
        <p class="why">${tr("danger_source")}</p></section>`) : ""}
      ${rev.length ? raw(html`<section class="danger-panel review" style="margin-bottom:16px"><p class="h3">${raw(icon("info"))}${tr("danger_review")}</p>
        ${rev.map((d: any) => raw(html`<p class="why">${d.label?.[l] || d.label?.en}: “${d.matched_phrase}”</p>`))}</section>`) : ""}
      <div class="grid-2">
        <div style="display:grid;gap:16px;align-content:start">
          <section class="panel flush" aria-labelledby="vd-rec"><div class="panel-head"><h2 class="h3" id="vd-rec">${tr("vd_record")}</h2></div>
            ${raw(registerSheet(v, meta, l, { evidence: v.field_evidence || {} }))}</section>
          <section class="panel flush" aria-labelledby="vd-tx"><div class="panel-head"><h2 class="h3" id="vd-tx">${tr("vd_transcript")}</h2></div>
            <div class="panel-body quote-list">${(v.transcript || []).length ? raw((v.transcript as any[]).map((t) => html`<blockquote>${t.text}</blockquote>`).join(""))
              : raw(html`<p class="small subtle">${tr("vd_no_transcript")}</p>`)}</div></section>
        </div>
        <div style="display:grid;gap:16px;align-content:start">
          <section class="panel" aria-label="${tr("vd_record")}"><div class="panel-body" style="padding-top:16px">
            <dl class="kv"><dt>${tr("vd_saved")}</dt><dd class="num">${fmtTime(v.saved_at, l)}</dd>
            <dt>${tr("vd_source")}</dt><dd>${sourceLabel(v.source)}</dd>
            <dt>${tr("vd_language")}</dt><dd>${LANGUAGES.find((x) => x.code === v.language)?.label || v.language || "—"}</dd>
            <dt>${tr("vd_confirmed_via")}</dt><dd>${via}</dd></dl></div></section>
          <section class="panel flush" aria-labelledby="vd-fu"><div class="panel-head"><h2 class="h3" id="vd-fu">${tr("next_actions")}</h2></div>
            ${(v.followups || []).length ? raw(html`<ul class="rows">${(v.followups as any[]).map((fu) => raw(html`<li><div class="row-item">
              <span class="pri ${fu.priority}"></span><span class="grow"><span class="row-title wrap">${followupTitle(fu, l)}</span>
              <span class="row-sub num">${fu.due_date ? fmtShortDate(fu.due_date, l) : tr("no_date")}</span></span>
              ${fu.status === "DONE" ? raw(html`<span class="badge neutral">${raw(icon("check"))}${tr("fu_completed")}</span>`) : raw(priorityBadge(fu.priority))}</div></li>`))}</ul>`)
              : raw(html`<p class="small subtle pad">${tr("prof_no_followups")}</p>`)}</section>
          <section class="panel flush" aria-labelledby="vd-hi"><div class="panel-head"><h2 class="h3" id="vd-hi">${tr("vd_history")}</h2></div>
            ${audit.length ? raw(html`<ol class="timeline">${audit.map((a) => raw(html`<li><span class="when">${fmtClock(a.timestamp, l)}</span>
              <span class="rail"><i class="${a.event_type === "visit_saved" ? "done" : a.event_type === "field_corrected" || a.event_type === "undo" ? "review" : a.event_type === "referral_alert" || a.event_type === "danger_confirmed" ? "referral" : ""}"></i></span>
              <div class="what"><b>${evLabel(a)}</b>${a.reason_code && a.event_type !== "visit_saved" ? raw(html`<p class="xs subtle">${a.reason_code}</p>`) : ""}</div></li>`))}</ol>`)
              : raw(html`<p class="small subtle pad">${tr("vd_no_history")}</p>`)}</section>
        </div>
      </div>`);
  };

  on(root, "click", (action) => {
    if (action === "print") window.print();
    else if (action === "reload") void load();
  });
  void load();
}
