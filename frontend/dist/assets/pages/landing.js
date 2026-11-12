/** Public landing page at "/". All product imagery is real UI drawn in HTML, labelled as an
 * illustration with synthetic data. No statistics are claimed. */
import { langSelect } from "../components/shell.js";
import { setLang, tr } from "../i18n.js";
import { html, raw } from "../ui/dom.js";
import { logo, icon } from "../ui/icons.js";
export function renderLanding(root, rerender) {
    const navLinks = () => html `<a href="#top">${tr("l_nav_home")}</a><a href="#how">${tr("l_nav_how")}</a>
    <a href="#features">${tr("l_nav_features")}</a><a href="#impact">${tr("l_nav_impact")}</a>`;
    const waveHeights = [6, 12, 20, 28, 16, 30, 22, 12, 26, 18, 10, 24, 30, 14, 8, 18, 26, 12, 6];
    const value = (ic, t, d) => html `<div>${raw(icon(ic))}<b>${tr(t)}</b><span>${tr(d)}</span></div>`;
    const step = (n, t, d) => html `<li class="step"><span class="n" aria-hidden="true">${n}</span><span class="rule"></span><b>${tr(t)}</b><p>${tr(d)}</p></li>`;
    const f1Wave = [10, 22, 38, 54, 30, 62, 46, 24, 52, 36, 18, 44, 60, 28, 14, 34, 50, 22, 12, 40, 58, 32, 20, 46, 64, 38, 16, 30, 48, 26, 12, 8];
    const feature = (cls, ic, t, d) => html `<article class="feature ${cls}">${raw(icon(ic))}<div><b>${tr(t)}</b><p>${tr(d)}</p></div>${cls === "f1"
        ? raw(`<div class="f1-wave" aria-hidden="true">${f1Wave.map((h) => `<i style="height:${h}px"></i>`).join("")}</div>`) : ""}</article>`;
    const impact = (ic, t, d) => html `<li>${raw(icon(ic))}<div><b>${tr(t)}</b><p>${tr(d)}</p></div></li>`;
    root.innerHTML = html `<div class="landing">
  <a class="sr-only skip" href="#main">${tr("skip_content")}</a>
  <header class="site-header" id="site-header">
    <div class="site bar">
      <a class="wordmark" href="/" aria-label="ASHA Vaani">${raw(logo())}</a>
      <nav class="site-nav" aria-label="${tr("nav_main")}">${raw(navLinks())}</nav>
      <div class="right">
        <span class="hide-sm">${raw(langSelect("site-lang"))}</span>
        <a class="btn btn-primary hide-sm" href="/app">${tr("get_started")}</a>
        <button class="icon-btn menu-btn" type="button" aria-expanded="false" aria-controls="mnav" aria-label="${tr("open_menu")}" data-action="menu">${raw(icon("menu"))}</button>
      </div>
    </div>
    <nav class="mobile-nav" id="mnav" aria-label="${tr("nav_main")}">${raw(navLinks())}
      <div class="mnav-foot">${raw(langSelect("site-lang-m"))}<a class="btn btn-primary" href="/app">${tr("get_started")}</a></div></nav>
  </header>

  <main id="main">
    <section class="site hero" id="top">
      <div class="copy">
        <p class="eyebrow">${tr("l_eyebrow")}</p>
        <h1 class="display">${tr("l_headline")}</h1>
        <p class="lede">${tr("l_sub")}</p>
        <div class="ctas"><a class="btn btn-primary btn-lg" href="/app">${raw(icon("mic"))}${tr("get_started")}</a>
          <a class="btn btn-lg" href="#how">${tr("l_cta_explore")}</a></div>
        <ul class="points">
          <li>${raw(icon("languages"))}${tr("l_point1")}</li>
          <li>${raw(icon("speaker"))}${tr("l_point2")}</li>
          <li>${raw(icon("shield"))}${tr("l_point3")}</li>
        </ul>
      </div>
      <figure class="showcase">
        <div class="device" aria-hidden="true"><div class="notch"></div><div class="screen">
          <div class="mock-top"><span class="mock-title">${tr("nav_new_visit")}</span><span class="mock-pill"><span class="dot"></span>${tr("ds_listening")}</span></div>
          <div class="mock-card"><div class="lbl">${tr("ws_transcript")}</div>${tr("mock_line")}</div>
          <div class="wave-mini">${raw(waveHeights.map((h) => `<i style="height:${h}px"></i>`).join(""))}</div>
          <div class="mock-card"><div class="lbl">${tr("ws_record")}</div>
            <div class="mock-row"><span>${tr("f_beneficiary_id")}</span><b>1024</b></div>
            <div class="mock-row"><span>${tr("f_visit_type")}</span><b>ANC</b></div>
            <div class="mock-row"><span>${tr("f_weight_kg")}</span><b>52 kg</b></div></div>
          <div class="mock-mic">${raw(icon("mic"))}</div>
        </div></div>
        <div class="float-panel float-record" aria-hidden="true">
          <p class="h3">${raw(icon("records"))}${tr("ws_record")}</p>
          <div class="r"><span>${tr("f_ifa_tablets_given")}</span><b>${tr("given")}</b></div>
          <div class="r"><span>${tr("f_next_visit_date")}</span><b>20 Nov</b></div>
          <div class="r"><span>${tr("f_vaccinations_given")}</span><b>TT</b></div>
          <div class="r"><span>${tr("col_status")}</span><span class="badge warn">${tr("ds_confirm")}</span></div>
        </div>
        <div class="float-panel float-task" aria-hidden="true">
          <p class="h3">${raw(icon("calendarCheck"))}${tr("nav_followups")}</p>
          <div class="task-row"><span class="pri NORMAL"></span><div><b>${tr("mock_task_title")}</b><span class="subtle xs">1024</span></div></div>
          <p class="xs subtle">${tr("mock_task_due")}</p>
        </div>
        <figcaption class="xs subtle showcase-cap">${tr("mock_caption")}</figcaption>
      </figure>
    </section>

    <section class="site"><div class="value-strip">
      ${raw(value("mic", "v1_t", "v1_d"))}${raw(value("records", "v2_t", "v2_d"))}${raw(value("speaker", "v3_t", "v3_d"))}${raw(value("calendarCheck", "v4_t", "v4_d"))}
    </div></section>

    <section class="site block" id="how" aria-labelledby="how-h">
      <div class="block-head"><h2 class="h1" id="how-h">${tr("how_title")}</h2><p class="lede">${tr("how_lede")}</p></div>
      <ol class="steps">${raw(step("01", "s1_t", "s1_d"))}${raw(step("02", "s2_t", "s2_d"))}${raw(step("03", "s3_t", "s3_d"))}${raw(step("04", "s4_t", "s4_d"))}</ol>
    </section>

    <section class="site block" id="features" aria-labelledby="feat-h">
      <div class="block-head"><h2 class="h1" id="feat-h">${tr("feat_title")}</h2><p class="lede">${tr("feat_lede")}</p></div>
      <div class="feature-grid">
        ${raw(feature("f1", "wave", "f1_t", "f1_d"))}${raw(feature("f2", "eye", "f2_t", "f2_d"))}${raw(feature("f3", "pencil", "f3_t", "f3_d"))}
        ${raw(feature("f4", "alert", "f4_t", "f4_d"))}${raw(feature("f5", "listChecks", "f5_t", "f5_d"))}${raw(feature("f6", "lock", "f6_t", "f6_d"))}
      </div>
    </section>

    <section class="site block" id="impact" aria-labelledby="impact-h">
      <div class="impact">
        <div class="block-head"><h2 class="h1" id="impact-h">${tr("impact_title")}</h2><p class="lede">${tr("impact_lede")}</p></div>
        <ul>${raw(impact("home", "i1_t", "i1_d"))}${raw(impact("calendarCheck", "i2_t", "i2_d"))}${raw(impact("referral", "i3_t", "i3_d"))}${raw(impact("languages", "i4_t", "i4_d"))}</ul>
      </div>
    </section>

    <section class="site"><div class="final-cta">
      <h2 class="h1">${tr("final_title")}</h2><p>${tr("final_body")}</p>
      <a class="btn btn-primary btn-lg" href="/app">${tr("final_btn")}</a>
    </div></section>
  </main>

  <footer class="site-footer"><div class="site">
    <div class="cols">
      <div><a class="wordmark" href="/">${raw(logo())}</a><p style="margin-top:10px">${tr("tagline")}</p></div>
      <div><h4>${tr("footer_product")}</h4><a href="#how">${tr("l_nav_how")}</a><a href="#features">${tr("l_nav_features")}</a>
        <a href="#impact">${tr("l_nav_impact")}</a><a href="/app">${tr("footer_open")}</a></div>
      <div><h4>${tr("footer_privacy_t")}</h4><p>${tr("footer_privacy")}</p></div>
    </div>
    <div class="fine"><p>${tr("footer_proto")}</p></div>
  </div></footer>
  </div>`;
    const header = root.querySelector("#site-header");
    const mnav = root.querySelector("#mnav");
    const menuBtn = root.querySelector("[data-action=menu]");
    const onScroll = () => header.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    root.addEventListener("click", (ev) => {
        const t = ev.target;
        if (t.closest("[data-action=menu]")) {
            const open = !mnav.classList.contains("open");
            mnav.classList.toggle("open", open);
            menuBtn.setAttribute("aria-expanded", String(open));
        }
        else if (t.closest("#mnav a")) {
            mnav.classList.remove("open");
            menuBtn.setAttribute("aria-expanded", "false");
        }
    });
    root.addEventListener("change", (ev) => {
        const t = ev.target;
        if (t.matches("[data-lang-select]")) {
            setLang(t.value);
            rerender();
        }
    });
    if (location.hash.length > 1 && !location.hash.startsWith("#/")) {
        document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView();
    }
    return () => window.removeEventListener("scroll", onScroll);
}
