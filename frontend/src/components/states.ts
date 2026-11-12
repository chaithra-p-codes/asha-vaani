/** Loading, empty and error states, and the small status badges shared by every page. */
import { tr } from "../i18n.js";
import { html, raw } from "../ui/dom.js";
import { icon, IconName } from "../ui/icons.js";

export function skeletonRows(n = 4): string {
  return `<div aria-busy="true" aria-label="${tr("loading")}">${Array.from({ length: n },
    (_x, i) => `<div class="skeleton sk-line" style="width:${88 - (i % 3) * 14}%"></div>`).join("")}</div>`;
}

export function skeletonStats(n = 4): string {
  return Array.from({ length: n }, () => `<div class="stat" aria-hidden="true"><div class="skeleton sk-line" style="margin:2px 0;width:60%"></div>
    <div class="skeleton" style="height:34px;width:40%"></div></div>`).join("");
}

export function emptyState(text: string, ic: IconName = "info", action = ""): string {
  return html`<div class="empty">${raw(icon(ic))}<p>${text}</p>${raw(action)}</div>`;
}

export function errorState(text = tr("load_failed")): string {
  return html`<div class="error-state" role="alert"><p>${text}</p>
    <button class="btn" data-action="reload">${raw(icon("refresh"))}${tr("retry")}</button></div>`;
}

export function demoBadge(source: string | null | undefined): string {
  return source === "seed" || source === "demo" ? html`<span class="badge demo" title="${tr("demo_data")}">${tr("demo_data")}</span>` : "";
}

export function referralBadge(status: string | null | undefined): string {
  if (status === "REFER_NOW") return html`<span class="badge danger">${raw(icon("alert"))}${tr("ref_refer_now")}</span>`;
  if (status === "REVIEW_REQUIRED") return html`<span class="badge warn">${tr("ref_review")}</span>`;
  return html`<span class="subtle small">${tr("ref_none")}</span>`;
}

export function confirmationBadge(status: string | null | undefined): string {
  if (status === "PENDING_SYNC") return html`<span class="badge warn">${raw(icon("clock"))}${tr("st_pending_sync")}</span>`;
  if (status === "DRAFT") return html`<span class="badge neutral">${tr("st_draft")}</span>`;
  return html`<span class="badge">${raw(icon("check"))}${tr("st_confirmed")}</span>`;
}

export function priorityBadge(p: string | null | undefined): string {
  const key = (`pri_${p || "NORMAL"}`) as Parameters<typeof tr>[0];
  const cls = p === "URGENT" ? "danger" : p === "HIGH" ? "warn" : "neutral";
  return html`<span class="badge ${cls}">${tr(key)}</span>`;
}

export function statusBadge(status: string): string {
  const cls = status === "REFERRED" ? "danger" : status === "FOLLOWUP_DUE" ? "warn" : status === "COMPLETED" || status === "NO_VISITS" ? "neutral" : "";
  const key = (`badge_${status}`) as Parameters<typeof tr>[0];
  return html`<span class="badge ${cls}">${tr(key)}</span>`;
}
