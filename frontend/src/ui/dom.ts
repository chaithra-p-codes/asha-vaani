/** Tiny DOM helpers: every interpolated value goes through esc() (no HTML injection). */

export function esc(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Tagged template that escapes interpolations unless they are wrapped with raw(). */
export class Raw {
  constructor(public readonly html: string) {}
}
export const raw = (html: string): Raw => new Raw(html);

export function html(strings: TemplateStringsArray, ...values: unknown[]): string {
  let out = "";
  strings.forEach((s, i) => {
    out += s;
    if (i < values.length) {
      const v = values[i];
      if (v instanceof Raw) out += v.html;
      else if (Array.isArray(v)) out += v.map((x) => (x instanceof Raw ? x.html : esc(x))).join("");
      else out += esc(v);
    }
  });
  return out;
}

export function $(sel: string, root: ParentNode = document): HTMLElement | null {
  return root.querySelector(sel) as HTMLElement | null;
}

export function setHTML(el: HTMLElement | null, markup: string): void {
  if (el) el.innerHTML = markup;
}

export function on(root: HTMLElement, event: string, handler: (action: string, el: HTMLElement, ev: Event) => void): void {
  root.addEventListener(event, (ev) => {
    const target = (ev.target as HTMLElement | null)?.closest("[data-action]") as HTMLElement | null;
    if (target && root.contains(target)) handler(target.dataset.action || "", target, ev);
  });
}

let toastTimer: number | undefined;
export function toast(message: string): void {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { if (el) el.hidden = true; }, 3200);
}
