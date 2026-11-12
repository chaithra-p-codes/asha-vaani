/** Beneficiaries directory (/app/beneficiaries) and profile (/app/beneficiaries/:id). */
import { categoryLabel, CATEGORIES, daysBetween, fmtShortDate, followupTitle, initials, localISO, visitTypeLabel } from "../components/format.js";
import { registerSheet } from "../components/recordCard.js";
import { pageHead } from "../components/shell.js";
import { demoBadge, emptyState, errorState, priorityBadge, referralBadge, skeletonRows, statusBadge } from "../components/states.js";
import { lang, tr, trf } from "../i18n.js";
import { navigate, setQuery } from "../router.js";
import { api } from "../services/api.js";
import { $, html, on, raw, setHTML } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
export function renderBeneficiaries(root, route) {
    const l = lang();
    let q = route.query.get("q") || "";
    let cat = route.query.get("category") || "";
    let act = route.query.get("activity") || "";
    let rows = [];
    let today = localISO();
    root.innerHTML = html `${raw(pageHead(tr("nav_beneficiaries"), "", ""))}
    <div class="toolbar" role="search">
      <label class="search"><span class="sr-only">${tr("search")}</span>${raw(icon("search"))}
        <input class="input" id="q" type="search" inputmode="search" placeholder="${tr("search")}" value="${q}"></label>
      <label class="field"><span class="sr-only">${tr("col_category")}</span><select class="select" id="cat">
        <option value="">${tr("cat_all")}</option>${CATEGORIES.map((c) => raw(html `<option value="${c}" ${c === cat ? raw("selected") : ""}>${categoryLabel(c)}</option>`))}</select></label>
      <label class="field"><span class="sr-only">${tr("act_all")}</span><select class="select" id="act">
        ${[["", "act_all"], ["7", "act_7"], ["30", "act_30"], ["none", "act_none"]].map(([v, k]) => raw(html `<option value="${v}" ${v === act ? raw("selected") : ""}>${tr(k)}</option>`))}</select></label>
    </div>
    <p class="small subtle" id="count" aria-live="polite"></p>
    <section class="panel flush" id="list">${raw(skeletonRows(8))}</section>`;
    const filtered = () => rows.filter((b) => {
        if (q) {
            const s = q.toLowerCase().trim();
            if (!b.synthetic_external_id.includes(s) && !String(b.name).toLowerCase().includes(s))
                return false;
        }
        if (cat && b.category !== cat)
            return false;
        if (act === "none")
            return !b.last_visit_date;
        if (act)
            return !!b.last_visit_date && daysBetween(b.last_visit_date, today) <= Number(act);
        return true;
    });
    const draw = () => {
        const list = filtered();
        $("#count", root).textContent = rows.length ? `${trf("ben_meta", { n: rows.length })}. ${trf("results_n", { n: list.length })}.` : "";
        setHTML($("#list", root), list.length ? html `<div class="table-wrap"><table class="table stack">
      <thead><tr><th>${tr("col_beneficiary")}</th><th>${tr("col_category")}</th><th>${tr("col_last_visit")}</th>
        <th class="hide-sm">${tr("col_visits")}</th><th class="hide-sm">${tr("col_next_due")}</th><th>${tr("col_status")}</th></tr></thead>
      <tbody>${list.map((b) => raw(html `<tr class="clickable" data-action="open" data-id="${b.synthetic_external_id}" tabindex="0">
        <td class="primary" data-label="${tr("col_beneficiary")}"><span class="who-cell"><span class="avatar sm" aria-hidden="true">${initials(b.name)}</span>
          <span><span class="cell-main">${b.name}</span><span class="cell-sub"><span class="mono-id">ID ${b.synthetic_external_id}</span></span></span></span></td>
        <td data-label="${tr("col_category")}">${categoryLabel(b.category)}</td>
        <td data-label="${tr("col_last_visit")}" class="num">${b.last_visit_date ? raw(html `${fmtShortDate(b.last_visit_date, l)} <span class="subtle">${visitTypeLabel(b.last_visit_type, l)}</span>`) : "—"}</td>
        <td class="hide-sm num" data-label="${tr("col_visits")}">${b.visits}</td>
        <td class="hide-sm num" data-label="${tr("col_next_due")}">${b.next_due_date ? fmtShortDate(b.next_due_date, l) : "—"}</td>
        <td class="end" data-label="${tr("col_status")}">${raw(statusBadge(b.status))}</td></tr>`))}</tbody></table></div>`
            : emptyState(tr("ben_empty"), "users", html `<button class="btn" data-action="clear">${tr("clear_filters")}</button>`));
        setQuery({ q, category: cat, activity: act });
    };
    const load = async () => {
        setHTML($("#list", root), skeletonRows(8));
        try {
            const d = await api.beneficiaries();
            rows = d.beneficiaries;
            today = d.today || today;
            draw();
        }
        catch {
            setHTML($("#list", root), errorState());
        }
    };
    let debounce;
    $("#q", root).addEventListener("input", (e) => {
        q = e.target.value;
        window.clearTimeout(debounce);
        debounce = window.setTimeout(draw, 150);
    });
    $("#cat", root).addEventListener("change", (e) => { cat = e.target.value; draw(); });
    $("#act", root).addEventListener("change", (e) => { act = e.target.value; draw(); });
    on(root, "click", (action, el) => {
        if (action === "open")
            navigate(`/app/beneficiaries/${el.dataset.id}`);
        else if (action === "reload")
            void load();
        else if (action === "clear") {
            q = "";
            cat = "";
            act = "";
            $("#q", root).value = "";
            $("#cat", root).value = "";
            $("#act", root).value = "";
            draw();
        }
    });
    root.addEventListener("keydown", (ev) => {
        const row = ev.target.closest("tr[data-action=open]");
        if (row && (ev.key === "Enter" || ev.key === " ")) {
            ev.preventDefault();
            navigate(`/app/beneficiaries/${row.dataset.id}`);
        }
    });
    void load();
}
export function renderBeneficiary(root, id) {
    const l = lang();
    root.innerHTML = html `<a class="back-link" href="/app/beneficiaries">${raw(icon("back"))}${tr("nav_beneficiaries")}</a>
    <div id="profile">${raw(skeletonRows(10))}</div>`;
    const load = async () => {
        let p;
        try {
            p = await api.beneficiary(id);
        }
        catch (e) {
            setHTML($("#profile", root), e?.status === 404 ? emptyState(tr("ben_not_found"), "users") : errorState());
            return;
        }
        const tl = (p.timeline || []);
        const tlRow = (ev) => {
            const when = fmtShortDate(ev.date, l);
            let cls = "", text = "", sub = "", href = "";
            if (ev.kind === "visit") {
                text = trf("tl_visit", { type: visitTypeLabel(ev.visit_type, l) });
                href = `/app/visits/${ev.visit_id}`;
            }
            else if (ev.kind === "referral") {
                cls = "referral";
                text = tr("tl_referral");
                sub = ev.label?.[l] || ev.label?.en || "";
                href = `/app/visits/${ev.visit_id}`;
            }
            else if (ev.kind === "review") {
                cls = "review";
                text = tr("tl_review");
                sub = ev.label?.[l] || ev.label?.en || "";
                href = `/app/visits/${ev.visit_id}`;
            }
            else if (ev.kind === "followup") {
                cls = ev.status === "DONE" ? "done" : "";
                text = ev.status === "DONE" ? tr("tl_followup_done") : tr("tl_followup_due");
                sub = followupTitle(ev, l);
            }
            return html `<li><span class="when">${when}</span><span class="rail"><i class="${cls}"></i></span>
        <div class="what">${href ? raw(html `<a href="${href}"><b>${text}</b></a>`) : raw(html `<b>${text}</b>`)}${sub ? raw(html `<p class="small muted">${sub}</p>`) : ""}</div></li>`;
        };
        const latest = p.latest;
        const evidence = latest?.field_evidence || {};
        const metaFromConf = latest ? Object.fromEntries(Object.entries(latest.field_confidence || {}).map(([k, c]) => [k, { confidence: c }])) : {};
        setHTML($("#profile", root), html `
      <div class="profile-head">
        <span class="avatar" aria-hidden="true">${initials(p.name)}</span>
        <div class="grow"><h1 class="h1">${p.name}</h1>
          <p class="meta"><span class="mono-id">ID ${p.synthetic_external_id}</span><span class="sep"></span>${categoryLabel(p.category)}</p></div>
        <div class="chips">${raw(statusBadge(p.status))}<span class="badge demo">${tr("demo_data")}</span></div>
      </div>
      ${(p.aliases || []).length > 1 ? raw(html `<p class="small muted" style="margin:-8px 0 16px">${tr("prof_aliases")}: ${p.aliases.filter((a) => a !== p.name).join(", ")}</p>`) : ""}
      <div class="grid-2">
        <div style="display:grid;gap:16px;align-content:start">
          <section class="panel flush" aria-labelledby="pv-h"><div class="panel-head"><h2 class="h3" id="pv-h">${tr("prof_visits")}</h2>
            <a class="btn btn-primary" href="/app/new-visit">${raw(icon("mic"))}${tr("nav_new_visit")}</a></div>
            ${(p.visits_list || []).length ? raw(html `<div class="table-wrap"><table class="table stack">
              <thead><tr><th>${tr("col_date")}</th><th>${tr("col_type")}</th><th>${tr("col_referral")}</th><th></th></tr></thead>
              <tbody>${p.visits_list.map((v) => raw(html `<tr class="clickable" data-action="visit" data-id="${v.id}" tabindex="0">
                <td class="primary num" data-label="${tr("col_date")}"><span class="cell-main">${fmtShortDate(v.visit_date, l)}</span></td>
                <td data-label="${tr("col_type")}">${visitTypeLabel(v.visit_type, l)}</td>
                <td data-label="${tr("col_referral")}">${raw(referralBadge(v.referral_status))}</td>
                <td class="end">${raw(demoBadge(v.source))}</td></tr>`))}</tbody></table></div>`)
            : raw(emptyState(tr("prof_no_visits"), "records"))}
          </section>
          <section class="panel flush" aria-labelledby="pl-h"><div class="panel-head"><h2 class="h3" id="pl-h">${tr("prof_latest")}</h2>
            ${latest ? raw(html `<span class="small subtle num">${fmtShortDate(latest.visit_date, l)}</span>`) : ""}</div>
            ${latest ? raw(registerSheet(latest, metaFromConf, l, { evidence })) : raw(emptyState(tr("prof_no_visits"), "records"))}
          </section>
        </div>
        <div style="display:grid;gap:16px;align-content:start">
          <section class="panel flush" aria-labelledby="pf-h"><div class="panel-head"><h2 class="h3" id="pf-h">${tr("prof_followups")}</h2></div>
            ${(p.followups || []).filter((f) => f.status === "PENDING").length ? raw(html `<ul class="rows">${p.followups.filter((f) => f.status === "PENDING").map((f) => raw(html `<li>
              <div class="row-item"><span class="pri ${f.priority}"></span><span class="grow"><span class="row-title wrap">${followupTitle(f, l)}</span>
              <span class="row-sub num">${f.due_date ? fmtShortDate(f.due_date, l) : tr("no_date")}</span></span>${raw(priorityBadge(f.priority))}</div></li>`))}</ul>`)
            : raw(html `<p class="small subtle pad">${tr("prof_no_followups")}</p>`)}
          </section>
          <section class="panel flush" aria-labelledby="pr-h"><div class="panel-head"><h2 class="h3" id="pr-h">${tr("prof_referrals")}</h2></div>
            ${(p.referrals || []).length ? raw(html `<ul class="rows">${p.referrals.map((r) => raw(html `<li><a class="row-item" href="/app/visits/${r.visit_id}">
              <span class="grow"><span class="row-title wrap">${(r.signs || []).map((s) => s.label?.[l] || s.label?.en).join(", ")}</span>
              <span class="row-sub num">${fmtShortDate(r.visit_date, l)}</span></span>${raw(referralBadge(r.referral_status))}</a></li>`))}</ul>`)
            : raw(html `<p class="small subtle pad">${tr("prof_no_referrals")}</p>`)}
          </section>
          <section class="panel flush" aria-labelledby="pt-h"><div class="panel-head"><h2 class="h3" id="pt-h">${tr("prof_timeline")}</h2></div>
            ${tl.length ? raw(`<ol class="timeline">${tl.map(tlRow).join("")}</ol>`) : raw(html `<p class="small subtle pad">${tr("prof_no_visits")}</p>`)}
          </section>
        </div>
      </div>`);
    };
    on(root, "click", (action, el) => {
        if (action === "visit")
            navigate(`/app/visits/${el.dataset.id}`);
        else if (action === "reload")
            void load();
    });
    root.addEventListener("keydown", (ev) => {
        const row = ev.target.closest("tr[data-action=visit]");
        if (row && (ev.key === "Enter" || ev.key === " ")) {
            ev.preventDefault();
            navigate(`/app/visits/${row.dataset.id}`);
        }
    });
    void load();
}
