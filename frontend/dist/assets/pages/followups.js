/** Follow-up centre (/app/follow-ups): Overdue, Due today, Upcoming, Completed.
 * Tasks are created on the server by fixed rules (R1-R6) from confirmed visits; this page only
 * groups them by due date and lets the worker mark them completed or reopen them. */
import { fmtShortDate, followupTitle, relatedVisitText } from "../components/format.js";
import { pageHead } from "../components/shell.js";
import { demoBadge, errorState, priorityBadge, skeletonRows } from "../components/states.js";
import { lang, tr } from "../i18n.js";
import { api } from "../services/api.js";
import { $, html, on, raw, setHTML, toast } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
export function renderFollowups(root, refreshShell) {
    const l = lang();
    root.innerHTML = html `${raw(pageHead(tr("nav_followups"), tr("fu_meta")))}
    <nav class="chips jump" id="jump" aria-label="${tr("nav_followups")}"></nav>
    <div id="sections">${raw(skeletonRows(8))}</div>`;
    const item = (f) => html `<li class="fu-item" data-id="${f.id}">
    <span class="pri ${f.priority}" aria-hidden="true"></span>
    <div class="grow">
      <p class="row-title wrap">${followupTitle(f, l)}</p>
      <p class="row-sub"><a href="/app/beneficiaries/${f.beneficiary_id}">${f.beneficiary_name || "—"}</a>
        <span class="mono-id">ID ${f.beneficiary_id}</span> ${raw(demoBadge(f.source))}</p>
      <p class="xs subtle">${relatedVisitText(f, l)}</p>
    </div>
    <div class="fu-side">
      <span class="num small fu-due">${f.due_date ? fmtShortDate(f.due_date, l) : tr("fu_nodate")}</span>
      ${f.status === "DONE" ? raw(html `<span class="badge neutral">${raw(icon("check"))}${tr("fu_completed")}</span>`) : raw(priorityBadge(f.priority))}
    </div>
    <div class="fu-actions">
      ${f.status === "DONE"
        ? raw(html `<button class="btn btn-ghost" data-action="reopen" data-id="${f.id}">${raw(icon("undo"))}${tr("reopen")}</button>`)
        : raw(html `<button class="btn" data-action="done" data-id="${f.id}">${raw(icon("check"))}${tr("mark_done")}</button>`)}
      <a class="btn btn-ghost" href="/app/visits/${f.visit_id}">${raw(icon("file"))}${tr("view_visit")}</a>
    </div></li>`;
    const load = async () => {
        try {
            const d = await api.followups("ALL");
            const today = d.today;
            const all = d.followups;
            const pending = all.filter((f) => f.status === "PENDING");
            const groups = [
                ["overdue", "fu_overdue", pending.filter((f) => f.due_date && f.due_date < today)],
                ["today", "fu_today", pending.filter((f) => f.due_date === today)],
                ["upcoming", "fu_upcoming", pending.filter((f) => f.due_date && f.due_date > today)
                        .sort((a, b) => a.due_date.localeCompare(b.due_date))],
                ["nodate", "fu_nodate", pending.filter((f) => !f.due_date)],
                ["completed", "fu_completed", all.filter((f) => f.status === "DONE")
                        .sort((a, b) => (b.due_date || "").localeCompare(a.due_date || ""))],
            ];
            const shown = groups.filter(([k, , list]) => k !== "nodate" || list.length);
            setHTML($("#jump", root), shown.map(([k, key, list]) => html `<a class="chip ${k === "overdue" && list.length ? "chip-warn" : ""}"
        href="#fu-${k}" data-jump="${k}">${tr(key)} <b class="num">${list.length}</b></a>`).join(""));
            setHTML($("#sections", root), shown.map(([k, key, list]) => html `<section class="panel flush fu-section" id="fu-${k}" aria-labelledby="fh-${k}">
        <div class="panel-head"><h2 class="h3" id="fh-${k}">${tr(key)}</h2><span class="badge ${k === "overdue" && list.length ? "warn" : "neutral"} num">${list.length}</span></div>
        ${list.length ? raw(`<ul class="rows fu-list">${list.map(item).join("")}</ul>`) : raw(html `<p class="small subtle pad">${tr("fu_empty")}</p>`)}
      </section>`).join(""));
        }
        catch {
            setHTML($("#sections", root), errorState());
        }
    };
    on(root, "click", async (action, el) => {
        if (action === "done" || action === "reopen") {
            el.disabled = true;
            try {
                await api.setFollowup(el.dataset.id || "", action === "done" ? "DONE" : "PENDING");
                toast(tr(action === "done" ? "fu_marked" : "fu_reopened"));
                refreshShell();
                await load();
            }
            catch {
                el.disabled = false;
                toast(tr("action_failed"));
            }
        }
        else if (action === "reload")
            void load();
    });
    root.addEventListener("click", (ev) => {
        const a = ev.target.closest("[data-jump]");
        if (!a)
            return;
        ev.preventDefault();
        document.getElementById(`fu-${a.dataset.jump}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    void load();
}
