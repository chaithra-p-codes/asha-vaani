/** Reports (/app/reports). Every number comes from /api/reports, computed on the server from the
 * register. Charts use one hue and always have a table view. Demo data is labelled as such. */
import { columnChart, hbars, hideTooltip } from "../components/charts.js";
import { addDays, fmtDate, fmtShortDate, localISO, locale, VISIT_TYPES, visitTypeLabel } from "../components/format.js";
import { pageHead } from "../components/shell.js";
import { emptyState, errorState, skeletonRows, skeletonStats } from "../components/states.js";
import { Key, lang, tr, trf } from "../i18n.js";
import { Route, setQuery } from "../router.js";
import { api, ApiError } from "../services/api.js";
import { $, html, on, raw, setHTML } from "../ui/dom.js";
import { icon } from "../ui/icons.js";

export function renderReports(root: HTMLElement, route: Route): () => void {
  const l = lang();
  const today = localISO();
  let preset = route.query.get("range") || "30";
  let from = route.query.get("from") || addDays(today, -29);
  let to = route.query.get("to") || today;
  const views: Record<string, "chart" | "table"> = { day: "chart", type: "chart" };
  let data: any = null;
  let dispose: (() => void) | null = null;

  const presetRange = (p: string): [string, string] => [addDays(today, -(Number(p) - 1)), today];
  if (preset !== "custom") [from, to] = presetRange(preset);

  root.innerHTML = html`${raw(pageHead(tr("nav_reports"), tr("rp_meta")))}
    <div class="toolbar">
      <div class="seg" id="presets" role="group" aria-label="${tr("col_date")}"></div>
      <form class="custom-range" id="custom" ${preset === "custom" ? "" : "hidden"}>
        <label class="field date-f"><span>${tr("from")}</span><input class="input" type="date" id="from" value="${from}" max="${today}"></label>
        <label class="field date-f"><span>${tr("to")}</span><input class="input" type="date" id="to" value="${to}" max="${today}"></label>
        <button class="btn" type="submit">${tr("apply")}</button>
      </form>
    </div>
    <p class="small subtle" id="range" aria-live="polite"></p>
    <div id="demo"></div>
    <section class="stat-grid" id="kpis">${raw(skeletonStats())}</section>
    <div class="grid-2 even" style="margin-top:16px">
      <section class="panel" aria-labelledby="day-h"><div class="panel-head"><h2 class="h3" id="day-h">${tr("rp_over_time")}</h2>
        <div class="seg sm" data-view="day"></div></div><div class="panel-body" id="day">${raw(skeletonRows(5))}</div></section>
      <section class="panel" aria-labelledby="type-h"><div class="panel-head"><h2 class="h3" id="type-h">${tr("rp_by_type")}</h2>
        <div class="seg sm" data-view="type"></div></div><div class="panel-body" id="type">${raw(skeletonRows(4))}</div></section>
    </div>
    <section class="panel" aria-labelledby="fs-h" style="margin-top:16px"><div class="panel-head"><h2 class="h3" id="fs-h">${tr("rp_fu_status")}</h2></div>
      <div class="panel-body" id="fus">${raw(skeletonRows(2))}</div></section>`;

  const drawPresets = () => {
    setHTML($("#presets", root), (["7", "30", "90", "custom"] as const).map((p) => html`<button type="button" data-action="preset" data-p="${p}"
      aria-pressed="${p === preset}">${tr(p === "custom" ? "rp_custom" : (`rp_${p}` as Key))}</button>`).join(""));
    ($("#custom", root) as HTMLElement).hidden = preset !== "custom";
  };
  const viewToggle = (key: string) => html`<button type="button" data-action="view" data-k="${key}" data-v="chart" aria-pressed="${views[key] === "chart"}">${tr("rp_chart")}</button>
    <button type="button" data-action="view" data-k="${key}" data-v="table" aria-pressed="${views[key] === "table"}">${tr("rp_table")}</button>`;

  const drawDay = () => {
    dispose?.();
    dispose = null;
    const host = $("#day", root)!;
    const days = (data.visits_by_day || []) as { date: string; visits: number }[];
    setHTML(root.querySelector('[data-view="day"]') as HTMLElement, viewToggle("day"));
    if (!data.total_visits) { setHTML(host, emptyState(tr("rp_empty"), "chart")); return; }
    if (views.day === "table") {
      setHTML(host, html`<div class="table-wrap scroll-y"><table class="table"><thead><tr><th>${tr("col_date")}</th><th class="num-h">${tr("col_visits")}</th></tr></thead>
        <tbody>${days.filter((d) => d.visits > 0).map((d) => raw(html`<tr><td class="num">${fmtDate(d.date, l)}</td><td class="num">${d.visits}</td></tr>`))}</tbody></table></div>`);
      return;
    }
    host.innerHTML = '<div class="chart-host"></div>';
    const points = days.map((d) => ({ label: fmtShortDate(d.date, l), tip: `${fmtDate(d.date, l)}: ${trf("rp_visits_n", { n: d.visits })}`, value: d.visits }));
    dispose = columnChart(host.firstElementChild as HTMLElement, points, `${tr("rp_over_time")}, ${trf("rp_visits_n", { n: data.total_visits })}`);
  };

  const drawType = () => {
    const host = $("#type", root)!;
    setHTML(root.querySelector('[data-view="type"]') as HTMLElement, viewToggle("type"));
    const rows = VISIT_TYPES.map((t) => ({ label: visitTypeLabel(t, l), value: data.visits_by_type?.[t] || 0, tip: visitTypeLabel(t, l) }));
    if (!data.total_visits) { setHTML(host, emptyState(tr("rp_empty"), "chart")); return; }
    if (views.type === "table") {
      setHTML(host, html`<table class="table"><thead><tr><th>${tr("col_type")}</th><th class="num-h">${tr("col_count")}</th></tr></thead>
        <tbody>${rows.map((r) => raw(html`<tr><td>${r.label}</td><td class="num">${r.value}</td></tr>`))}</tbody></table>`);
      return;
    }
    setHTML(host, hbars(rows));
  };

  const draw = () => {
    const fmt = (n: number) => n.toLocaleString(locale(l));
    $("#range", root)!.textContent = `${fmtDate(data.from, l)} – ${fmtDate(data.to, l)}`;
    const demoCount = (data.sources?.seed || 0) + (data.sources?.demo || 0);
    setHTML($("#demo", root), demoCount ? html`<p class="notice info" style="margin-bottom:14px">${raw(icon("info"))}<span>${tr("rp_demo")}</span></p>` : "");
    const fu = data.followups || { pending: 0, done: 0 };
    const ref = data.referrals || { refer_now: 0, review: 0 };
    setHTML($("#kpis", root), html`
      <div class="stat"><span class="label">${raw(icon("records"))}${tr("rp_total")}</span><span class="value">${fmt(data.total_visits)}</span></div>
      <div class="stat"><span class="label">${raw(icon("clock"))}${tr("rp_fu_pending")}</span><span class="value">${fmt(fu.pending)}</span></div>
      <div class="stat"><span class="label">${raw(icon("checkCircle"))}${tr("rp_fu_done")}</span><span class="value">${fmt(fu.done)}</span></div>
      <div class="stat ${ref.refer_now ? "urgent" : ""}"><span class="label">${raw(icon("alert"))}${tr("rp_refer")}</span><span class="value">${fmt(ref.refer_now)}</span>
        <span class="note">${tr("rp_review")}: ${fmt(ref.review)}</span></div>`);
    drawDay();
    drawType();
    const total = fu.pending + fu.done;
    const pct = total ? Math.round((fu.done / total) * 100) : 0;
    setHTML($("#fus", root), total ? html`<div class="share" role="img" aria-label="${trf("rp_done_share", { p: pct })}">
        <div class="share-bar"><span style="width:${pct}%"></span></div>
        <div class="share-legend"><span><i class="sw done"></i>${tr("rp_fu_done")} <b class="num">${fu.done}</b></span>
          <span><i class="sw"></i>${tr("rp_fu_pending")} <b class="num">${fu.pending}</b></span><span class="subtle">${trf("rp_done_share", { p: pct })}</span></div></div>
        <p class="xs subtle" style="margin-top:8px">${tr("rp_fu_scope")}</p>`
      : emptyState(tr("rp_empty"), "calendarCheck"));
  };

  const load = async () => {
    setQuery(preset === "custom" ? { range: "custom", from, to } : { range: preset });
    if (from > to) { setHTML($("#kpis", root), html`<p class="notice">${tr("rp_bad_range")}</p>`); return; }
    try {
      data = await api.reports(from, to);
      draw();
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setHTML($("#kpis", root), html`<p class="notice">${e.message || tr("rp_bad_range")}</p>`);
      else { setHTML($("#kpis", root), ""); setHTML($("#day", root), errorState()); setHTML($("#type", root), ""); setHTML($("#fus", root), ""); }
    }
  };

  on(root, "click", (action, el) => {
    if (action === "preset") {
      preset = el.dataset.p || "30";
      if (preset !== "custom") { [from, to] = presetRange(preset); void load(); }
      drawPresets();
    } else if (action === "view") {
      views[el.dataset.k || "day"] = (el.dataset.v as "chart" | "table") || "chart";
      if (el.dataset.k === "day") drawDay(); else drawType();
    } else if (action === "reload") void load();
  });
  root.addEventListener("submit", (ev) => {
    if (!(ev.target as HTMLElement).closest("#custom")) return;
    ev.preventDefault();
    from = ($("#from", root) as HTMLInputElement).value || from;
    to = ($("#to", root) as HTMLInputElement).value || to;
    void load();
  });
  drawPresets();
  void load();
  return () => { dispose?.(); hideTooltip(); };
}
