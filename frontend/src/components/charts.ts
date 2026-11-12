/** Small, dependency-free charts for the Reports page.
 * One series, one hue (forest), thin bars with rounded data ends anchored to the baseline,
 * recessive grid, a hover/focus tooltip and a table alternative rendered by the page. */
import { esc } from "../ui/dom.js";

let tip: HTMLElement | null = null;
function tooltip(): HTMLElement {
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "tooltip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  return tip;
}
export function hideTooltip(): void {
  if (tip) tip.hidden = true;
}
function showTooltip(text: string, x: number, y: number): void {
  const t = tooltip();
  t.textContent = text;
  t.hidden = false;
  const w = t.offsetWidth;
  const left = Math.max(8, Math.min(window.innerWidth - w - 8, x - w / 2));
  t.style.left = `${left}px`;
  t.style.top = `${Math.max(8, y - 40)}px`;
}

function niceMax(v: number): number {
  if (v <= 4) return Math.max(1, v);
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * pow >= v) return m * pow;
  return v;
}

/** Bar with only the top corners rounded (data end), flat on the baseline. */
function barPath(x: number, y: number, w: number, h: number, r = 4): string {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

export interface DayPoint { label: string; tip: string; value: number }

/** Vertical bar chart drawn at the container's real pixel width; redraws on resize. Returns a disposer. */
export function columnChart(host: HTMLElement, data: DayPoint[], ariaLabel: string): () => void {
  const draw = () => {
    const W = Math.max(280, Math.floor(host.clientWidth));
    const H = 220;
    const m = { l: 30, r: 8, t: 12, b: 28 };
    const iw = W - m.l - m.r;
    const ih = H - m.t - m.b;
    const max = niceMax(Math.max(0, ...data.map((d) => d.value)));
    const step = iw / Math.max(1, data.length);
    const gap = step > 6 ? 2 : 1;
    const bw = Math.max(1, step - gap);
    const ticks = max <= 4 ? Array.from({ length: max + 1 }, (_x, i) => i) : [0, max / 4, max / 2, (3 * max) / 4, max];
    const y = (v: number) => m.t + ih - (v / max) * ih;
    const labelEvery = Math.max(1, Math.ceil(data.length / Math.floor(iw / 64)));
    let s = `<svg class="chart" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(ariaLabel)}">`;
    s += `<g class="grid">${ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/>`).join("")}</g>`;
    s += `<g class="axis">${ticks.map((t) => `<text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${Number.isInteger(t) ? t : t.toFixed(1)}</text>`).join("")}</g>`;
    data.forEach((d, i) => {
      const x = m.l + i * step + gap / 2;
      if (d.value > 0) s += `<path class="bar" data-i="${i}" d="${barPath(x, y(d.value), bw, m.t + ih - y(d.value))}"/>`;
      s += `<rect class="hit" data-i="${i}" x="${m.l + i * step}" y="${m.t}" width="${step}" height="${ih}" fill="transparent"/>`;
      if (i % labelEvery === 0) s += `<text class="axis" x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${esc(d.label)}</text>`;
    });
    s += `<line x1="${m.l}" x2="${W - m.r}" y1="${m.t + ih}" y2="${m.t + ih}" stroke="#CFC8BB"/></svg>`;
    host.innerHTML = s;
  };
  draw();
  const onMove = (ev: PointerEvent) => {
    const el = (ev.target as Element).closest("[data-i]") as SVGElement | null;
    host.querySelectorAll(".bar.hot").forEach((b) => b.classList.remove("hot"));
    if (!el) { hideTooltip(); return; }
    const i = Number(el.getAttribute("data-i"));
    host.querySelector(`.bar[data-i="${i}"]`)?.classList.add("hot");
    showTooltip(data[i].tip, ev.clientX, ev.clientY);
  };
  const onLeave = () => { hideTooltip(); host.querySelectorAll(".bar.hot").forEach((b) => b.classList.remove("hot")); };
  host.addEventListener("pointermove", onMove);
  host.addEventListener("pointerleave", onLeave);
  let ro: ResizeObserver | null = null;
  let lastW = host.clientWidth;
  if ("ResizeObserver" in window) {
    ro = new ResizeObserver(() => { if (Math.abs(host.clientWidth - lastW) > 4) { lastW = host.clientWidth; draw(); } });
    ro.observe(host);
  }
  return () => { ro?.disconnect(); onLeave(); };
}

/** Horizontal bars with direct value labels (categories are few, so no legend is needed). */
export function hbars(rows: { label: string; value: number; tip: string }[]): string {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return `<div class="hbar">${rows.map((r) => `<div class="r" title="${esc(r.tip)}"><span>${esc(r.label)}</span>
    <span class="track"><span class="fill" style="width:${(r.value / max) * 100}%"></span></span><span class="v">${r.value}</span></div>`).join("")}</div>`;
}
