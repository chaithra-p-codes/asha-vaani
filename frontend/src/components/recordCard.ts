/** The register sheet: the authoritative review surface for a visit record (draft or saved). */
import { Key, Lang, tr, trf } from "../i18n.js";
import { html, raw } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
import { fieldText } from "./format.js";

export const FIELDS = ["beneficiary_id", "beneficiary_name", "visit_type", "weight_kg", "vaccinations_given",
  "vaccinations_due", "ifa_tablets_given", "next_visit_date", "visit_date"] as const;
export const REQUIRED_FIELDS = ["beneficiary_id", "visit_type"] as const;
export const ASKED_FIELDS = ["weight_kg", "next_visit_date"] as const;
export const CORRECTABLE = new Set(["beneficiary_id", "visit_type", "weight_kg", "vaccinations_given", "ifa_tablets_given",
  "next_visit_date"]);

interface Meta { confidence?: string; source?: string; note?: string; corrected?: boolean; raw?: string }

const isEmpty = (v: unknown) => v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function chip(field: string, value: unknown, meta: Meta | undefined, l: Lang, changed: boolean): string {
  if (field === "visit_date" && isEmpty(value)) return `<span class="badge neutral">${tr("chip_auto", l)}</span>`;
  if (isEmpty(value)) return `<span class="badge warn">${tr("chip_missing", l)}</span>`;
  if (meta?.confidence === "confirm") return `<span class="badge warn">${tr("chip_confirm", l)}</span>`;
  if (changed || meta?.corrected) return `<span class="badge">${tr("chip_changed", l)}</span>`;
  if (meta?.source === "register") return `<span class="badge neutral">${tr("chip_register", l)}</span>`;
  if (meta?.confidence === "system") return `<span class="badge neutral">${tr("chip_auto", l)}</span>`;
  return `<span class="badge">${tr("chip_heard", l)}</span>`;
}

export interface SheetOptions {
  changed?: Set<string>;
  issues?: { field: string; message: string; code?: string }[];
  correctable?: boolean;
  evidence?: Record<string, string | null | undefined>;
  title?: string;
  note?: string;
}

export function registerSheet(record: Record<string, unknown>, meta: Record<string, Meta>, l: Lang, o: SheetOptions = {}): string {
  const changed = o.changed || new Set<string>();
  const rows = FIELDS.map((f) => {
    const v = record[f];
    const m = meta[f];
    const empty = isEmpty(v);
    if (empty && (f === "beneficiary_name" || f === "vaccinations_due")) return "";
    const text = empty ? (f === "visit_date" ? fieldText("visit_date", new Date().toISOString().slice(0, 10), l)
      : tr("not_heard_v", l)) : fieldText(f, v, l);
    const why = m?.confidence === "confirm" && m.note ? m.note
      : (o.issues || []).find((i) => i.field === f && i.code !== "missing_required")?.message || "";
    const spoken = (o.evidence && o.evidence[f]) || m?.raw || "";
    const canFix = o.correctable && CORRECTABLE.has(f);
    return html`<div class="row ${changed.has(f) ? "changed" : ""}" data-field="${f}">
      <span class="label">${tr(("f_" + f) as Key, l)}</span>
      <span class="value ${empty && f !== "visit_date" ? "empty-v" : ""} ${f === "beneficiary_id" ? "mono-id" : ""}">${text}</span>
      <span class="side">${raw(chip(f, v, m, l, changed.has(f)))}${canFix ? raw(html`<button type="button" class="btn btn-ghost btn-xs"
        data-action="correct" data-field="${f}" aria-label="${tr("btn_correct", l)}: ${tr(("f_" + f) as Key, l)}">${raw(icon("pencil"))}<span class="hide-xs">${tr("btn_correct", l)}</span></button>`) : ""}</span>
      ${why ? raw(html`<span class="why">${why}</span>`) : ""}
      ${spoken && !empty && f !== "visit_date" ? raw(html`<span class="heard-phrase">${trf("spoken_as", { p: String(spoken) }, l)}</span>`) : ""}
    </div>`;
  }).join("");
  return html`<section class="register" aria-label="${o.title || tr("ws_record", l)}">${o.note ? raw(html`<p class="small subtle reg-note">${o.note}</p>`) : ""}${raw(rows)}</section>`;
}

/** Missing and to-check items for the side panel. */
export function missingList(record: Record<string, unknown>, meta: Record<string, Meta>, l: Lang): string {
  const items: string[] = [];
  for (const f of REQUIRED_FIELDS) {
    if (isEmpty(record[f])) items.push(html`<li>${raw(icon("alertCircle"))}<span><b>${tr(("f_" + f) as Key, l)}</b> <span class="subtle">${tr("missing_required", l)}</span></span></li>`);
  }
  for (const f of ASKED_FIELDS) {
    if (isEmpty(record[f])) items.push(html`<li>${raw(icon("circle"))}<span>${tr(("f_" + f) as Key, l)} <span class="subtle">${tr("missing_optional", l)}</span></span></li>`);
  }
  for (const f of FIELDS) {
    if (!isEmpty(record[f]) && meta[f]?.confidence === "confirm") {
      items.push(html`<li>${raw(icon("alert"))}<span>${tr(("f_" + f) as Key, l)} <span class="subtle">${tr("chip_confirm", l)}</span></span></li>`);
    }
  }
  const reqOk = REQUIRED_FIELDS.every((f) => !isEmpty(record[f]));
  if (reqOk) items.unshift(html`<li class="ok">${raw(icon("checkCircle"))}<span>${tr("missing_none", l)}</span></li>`);
  return `<ul class="missing">${items.join("")}</ul>`;
}
