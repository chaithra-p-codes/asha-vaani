/** Tiny DOM helpers: every interpolated value goes through esc() (no HTML injection). */
export function esc(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}
/** Tagged template that escapes interpolations unless they are wrapped with raw(). */
export class Raw {
    constructor(html) {
        this.html = html;
    }
}
export const raw = (html) => new Raw(html);
export function html(strings, ...values) {
    let out = "";
    strings.forEach((s, i) => {
        out += s;
        if (i < values.length) {
            const v = values[i];
            if (v instanceof Raw)
                out += v.html;
            else if (Array.isArray(v))
                out += v.map((x) => (x instanceof Raw ? x.html : esc(x))).join("");
            else
                out += esc(v);
        }
    });
    return out;
}
export function $(sel, root = document) {
    return root.querySelector(sel);
}
export function setHTML(el, markup) {
    if (el)
        el.innerHTML = markup;
}
export function on(root, event, handler) {
    root.addEventListener(event, (ev) => {
        const target = ev.target?.closest("[data-action]");
        if (target && root.contains(target))
            handler(target.dataset.action || "", target, ev);
    });
}
let toastTimer;
export function toast(message) {
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
    toastTimer = window.setTimeout(() => { if (el)
        el.hidden = true; }, 3200);
}
