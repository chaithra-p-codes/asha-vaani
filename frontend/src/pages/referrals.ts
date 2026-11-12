/** Referral centre (/app/referrals). A referral exists only because the deterministic danger engine
 * matched a listed MCP card sign (REFER_NOW) or found an unclear mention (ANM review). Closing a
 * referral marks its REFERRAL / DANGER_REVIEW follow-up done; nothing clinical is inferred here. */
import { fmtShortDate, visitTypeLabel } from "../components/format.js";
import { pageHead } from "../components/shell.js";
import { demoBadge, emptyState, errorState, referralBadge, skeletonRows } from "../components/states.js";
import { lang, tr } from "../i18n.js";
import { api } from "../services/api.js";
import { $, html, on, raw, setHTML, toast } from "../ui/dom.js";
import { icon } from "../ui/icons.js";

export function renderReferrals(root: HTMLElement, refreshShell: () => void): void {
  const l = lang();
  let tab: "OPEN" | "CLOSED" = "OPEN";
  let all: any[] = [];

  root.innerHTML = html`${raw(pageHead(tr("nav_referrals"), tr("rf_meta")))}
    <p class="notice info" style="margin-bottom:16px">${raw(icon("shield"))}<span>${tr("rf_guideline")}</span></p>
    <div class="seg" role="tablist" id="tabs" aria-label="${tr("nav_referrals")}"></div>
    <section class="panel flush" id="list" style="margin-top:14px">${raw(skeletonRows(6))}</section>`;

  const card = (r: any) => {
    const refer = r.referral_status === "REFER_NOW";
    const signs = (r.signs || []) as any[];
    return html`<article class="ref-card ${r.state === "OPEN" ? "open" : ""} ${refer ? "refer" : ""}">
      <div class="ref-head">
        <div class="who"><span class="ref-icon ${refer ? "" : "review"}">${raw(icon(refer ? "alert" : "info"))}</span>
          <div><a href="/app/beneficiaries/${r.beneficiary_id}"><b>${r.beneficiary_name || "—"}</b></a>
            <p class="xs subtle"><span class="mono-id">ID ${r.beneficiary_id}</span> ${visitTypeLabel(r.visit_type, l)} <span class="num">${fmtShortDate(r.visit_date, l)}</span></p></div></div>
        <div class="chips">${raw(referralBadge(r.referral_status))}${raw(demoBadge(r.source))}
          ${r.state === "CLOSED" ? raw(html`<span class="badge neutral">${raw(icon("check"))}${tr("rf_closed")}</span>`) : ""}</div>
      </div>
      <div class="sign-list">${signs.map((s) => raw(html`<div class="sign"><b>${s.label?.[l] || s.label?.en}</b>
        <span class="xs subtle">${tr("rf_rule")}</span> <code>${s.rule_id || s.id}</code>
        <span class="xs subtle">${tr("rf_heard")}</span> <span class="small">“${s.matched_phrase}”</span></div>
        ${s.source_ref ? raw(html`<p class="xs subtle">${tr("rf_source")}: ${s.source_ref}</p>`) : ""}`))}</div>
      <div class="chips">
        ${r.followup_id ? (r.state === "OPEN"
          ? raw(html`<button class="btn ${refer ? "btn-primary" : ""}" data-action="close" data-id="${r.followup_id}">${raw(icon("check"))}${tr(refer ? "rf_mark_done" : "rf_mark_review")}</button>`)
          : raw(html`<button class="btn btn-ghost" data-action="reopen" data-id="${r.followup_id}">${raw(icon("undo"))}${tr("reopen")}</button>`)) : ""}
        <a class="btn btn-ghost" href="/app/visits/${r.visit_id}">${raw(icon("file"))}${tr("view_visit")}</a>
      </div></article>`;
  };

  const draw = () => {
    const open = all.filter((r) => r.state === "OPEN");
    const closed = all.filter((r) => r.state !== "OPEN");
    setHTML($("#tabs", root), html`<button role="tab" aria-selected="${tab === "OPEN"}" aria-pressed="${tab === "OPEN"}" data-action="tab" data-tab="OPEN">${tr("rf_open")} <span class="num">${open.length}</span></button>
      <button role="tab" aria-selected="${tab === "CLOSED"}" aria-pressed="${tab === "CLOSED"}" data-action="tab" data-tab="CLOSED">${tr("rf_closed")} <span class="num">${closed.length}</span></button>`);
    const list = tab === "OPEN" ? open : closed;
    setHTML($("#list", root), list.length ? list.map(card).join("")
      : emptyState(tr(tab === "OPEN" ? "rf_empty_open" : "rf_empty_closed"), "shield"));
  };

  const load = async () => {
    try {
      const d = await api.referrals();
      all = d.referrals || [];
      draw();
    } catch {
      setHTML($("#list", root), errorState());
    }
  };

  on(root, "click", async (action, el) => {
    if (action === "tab") { tab = el.dataset.tab as "OPEN" | "CLOSED"; draw(); }
    else if (action === "close" || action === "reopen") {
      (el as HTMLButtonElement).disabled = true;
      try {
        await api.setFollowup(el.dataset.id || "", action === "close" ? "DONE" : "PENDING");
        toast(tr(action === "close" ? "fu_marked" : "fu_reopened"));
        refreshShell();
        await load();
      } catch {
        (el as HTMLButtonElement).disabled = false;
        toast(tr("action_failed"));
      }
    } else if (action === "reload") void load();
  });
  void load();
}
