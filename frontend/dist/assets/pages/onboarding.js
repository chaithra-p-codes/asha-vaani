/** First-run onboarding: welcome + AI disclosure, language (English default), microphone and speaker
 * check, and the Speak -> Review -> Correct -> Confirm -> Save workflow. Completion is stored on this
 * device so returning users go straight to the app. */
import { audioContext, unlockAudio } from "../audio/audioContext.js";
import { isPermissionError, MicCapture } from "../audio/capture.js";
import { LANGUAGES, lang, setLang, tr, trf } from "../i18n.js";
import { navigate } from "../router.js";
import { prefs } from "../store.js";
import { $, html, on, raw } from "../ui/dom.js";
import { brandMark, icon } from "../ui/icons.js";
export function renderOnboarding(root, next = "/app") {
    let stepNo = 1;
    let chosen = lang();
    let mic = "idle";
    let micErr = "";
    let heardVoice = false;
    const capture = new MicCapture();
    const progress = () => `<div class="onb-progress" aria-hidden="true">${[1, 2, 3, 4]
        .map((n) => `<i class="${n <= stepNo ? "on" : ""}"></i>`).join("")}</div>`;
    const actions = (primary, back = true, extra = "") => html `<div class="onb-actions">
    ${back ? raw(html `<button class="btn btn-ghost" data-action="back">${raw(icon("back"))}${tr("back")}</button>`) : raw("<span></span>")}
    <div class="chips">${raw(extra)}${raw(primary)}</div></div>`;
    const step1 = () => html `
    <div class="onb-brand">${raw(brandMark())}<span class="wordmark-t">ASHA Vaani</span></div>
    <div class="grid-gap"><h1 class="h1" id="onb-h">${tr("onb1_title")}</h1><p class="muted">${tr("onb1_body")}</p></div>
    <section class="disclosure" aria-labelledby="ai-h">
      <h2 class="h3" id="ai-h">${raw(icon("info"))}${tr("ai_title")}</h2>
      <ul class="ticks">
        <li>${raw(icon("check"))}${tr("ai_does")}</li>
        <li>${raw(icon("close"))}${tr("ai_never")}</li>
        <li>${raw(icon("shield"))}${tr("ai_rules")}</li>
        <li>${raw(icon("lock"))}${tr("ai_data")}</li>
      </ul>
    </section>
    <label class="field"><span>${tr("onb_name")}</span>
      <input class="input" id="name" autocomplete="given-name" maxlength="40" value="${prefs.workerName()}" placeholder="Sunita">
      <small class="subtle">${tr("onb_name_hint")}</small></label>
    ${raw(actions(html `<button class="btn btn-primary" data-action="next">${tr("onb_next")}${raw(icon("arrowRight"))}</button>`, false))}`;
    const step2 = () => html `
    <div class="grid-gap"><h1 class="h1" id="onb-h">${tr("onb2_title")}</h1><p class="muted">${tr("onb2_body")}</p></div>
    <div class="lang-options" role="radiogroup" aria-labelledby="onb-h">
      ${LANGUAGES.map((x) => raw(html `<button type="button" class="lang-opt" role="radio" aria-checked="${x.code === chosen}"
        data-action="lang" data-code="${x.code}" lang="${x.code}"><span class="radio"></span>
        <span><b>${x.label}</b><span class="small muted">${tr(x.sub)}</span></span></button>`))}
    </div>
    ${raw(actions(html `<button class="btn btn-primary" data-action="next">${tr("onb_next")}${raw(icon("arrowRight"))}</button>`))}`;
    const micStatus = () => {
        if (mic === "ok")
            return html `<p class="notice info" role="status">${raw(icon("checkCircle"))}<span>${heardVoice ? tr("mic_ok") : tr("mic_testing")}</span></p>`;
        if (mic === "testing")
            return html `<p class="notice info" role="status">${raw(icon("mic"))}<span>${tr("mic_testing")}</span></p>`;
        if (mic === "blocked")
            return html `<p class="notice danger" role="alert">${raw(icon("micOff"))}<span>${tr("mic_denied")}</span></p>`;
        if (mic === "unsupported")
            return html `<p class="notice" role="alert">${raw(icon("alert"))}<span>${tr("mic_unsupported")}</span></p>`;
        if (mic === "error")
            return html `<p class="notice" role="alert">${raw(icon("alert"))}<span>${micErr}</span></p>`;
        return html `<p class="small subtle">${tr("mic_not_tested")}</p>`;
    };
    const step3 = () => html `
    <div class="grid-gap"><h1 class="h1" id="onb-h">${tr("onb3_title")}</h1><p class="muted">${tr("onb3_body")}</p></div>
    <div class="panel"><div class="panel-body" style="padding-top:16px;display:grid;gap:12px">
      <div class="meter" role="meter" aria-label="${tr("wave_label")}" aria-valuemin="0" aria-valuemax="100"><div id="lvl"></div></div>
      <div id="micstatus">${raw(micStatus())}</div>
      <div class="chips"><button class="btn" data-action="mic" ${mic === "ok" || mic === "testing" ? "disabled" : ""}>${raw(icon("mic"))}${tr(mic === "blocked" || mic === "error" ? "retry" : "mic_allow")}</button>
        <button class="btn" data-action="tone">${raw(icon("speaker"))}${tr("spk_test")}</button></div>
      <p class="xs subtle">${tr("spk_note")}</p>
    </div></div>
    ${raw(actions(html `<button class="btn btn-primary" data-action="next">${tr("onb_next")}${raw(icon("arrowRight"))}</button>`, true, mic === "ok" ? "" : html `<button class="btn btn-ghost" data-action="next">${tr("onb_skip")}</button>`))}`;
    const flow = [["mic", "flow_speak", "fd_speak"], ["eye", "flow_review", "fd_review"],
        ["pencil", "flow_correct", "fd_correct"], ["checkCircle", "flow_confirm", "fd_confirm"], ["save", "flow_save", "fd_save"]];
    const step4 = () => html `
    <div class="grid-gap"><h1 class="h1" id="onb-h">${tr("onb4_title")}</h1><p class="muted">${tr("onb4_body")}</p></div>
    <ol class="flow-list">${flow.map(([ic, t, d], i) => raw(html `<li><span class="ic">${raw(icon(ic))}</span>
      <div><b>${i + 1}. ${tr(t)}</b><p class="small muted">${tr(d)}</p></div></li>`))}</ol>
    ${raw(actions(html `<button class="btn btn-primary btn-lg" data-action="finish">${tr("onb_enter")}${raw(icon("arrowRight"))}</button>`))}`;
    const draw = () => {
        const body = [step1, step2, step3, step4][stepNo - 1]();
        root.innerHTML = html `<div class="onb"><div class="onb-card" role="region" aria-labelledby="onb-h">
      <div class="onb-top"><span class="xs subtle">${trf("onb_step", { n: stepNo })}</span>${raw(progress())}</div>
      ${raw(body)}</div></div>`;
        const h = $("h1", root);
        if (h) {
            h.setAttribute("tabindex", "-1");
            h.focus({ preventScroll: true });
        }
    };
    const saveName = () => {
        const input = $("#name", root);
        if (input)
            prefs.setWorkerName(input.value);
    };
    const testMic = async () => {
        if (!navigator.mediaDevices?.getUserMedia) {
            mic = "unsupported";
            draw();
            return;
        }
        mic = "testing";
        heardVoice = false;
        draw();
        try {
            await unlockAudio();
            capture.onFrame = (_f, rms) => {
                const bar = $("#lvl", root);
                if (bar)
                    bar.style.width = `${Math.min(100, rms * 900)}%`;
                if (rms > 0.02 && !heardVoice) {
                    heardVoice = true;
                    const st = $("#micstatus", root);
                    if (st)
                        st.innerHTML = micStatus();
                }
            };
            await capture.start();
            mic = "ok";
            draw();
        }
        catch (e) {
            capture.stop();
            if (isPermissionError(e))
                mic = "blocked";
            else {
                mic = "error";
                micErr = String(e?.message || e);
            }
            draw();
        }
    };
    const playTone = async () => {
        try {
            const ctx = await unlockAudio();
            const o = ctx.createOscillator();
            const g = ctx.createGain();
            o.type = "sine";
            o.frequency.setValueAtTime(523, ctx.currentTime);
            o.frequency.setValueAtTime(659, ctx.currentTime + 0.22);
            g.gain.setValueAtTime(0.0001, ctx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.03);
            g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.6);
            o.connect(g).connect(audioContext().destination);
            o.start();
            o.stop(ctx.currentTime + 0.62);
        }
        catch { /* audio unavailable; nothing to claim */ }
    };
    on(root, "click", async (action, el) => {
        if (action === "next") {
            if (stepNo === 1)
                saveName();
            if (stepNo === 2) {
                setLang(chosen);
                prefs.setSpeechLang(chosen);
            }
            if (stepNo === 3)
                capture.stop();
            stepNo = Math.min(4, stepNo + 1);
            draw();
        }
        else if (action === "back") {
            if (stepNo === 3)
                capture.stop();
            stepNo = Math.max(1, stepNo - 1);
            if (stepNo === 3 && mic === "ok")
                mic = "idle";
            draw();
        }
        else if (action === "lang") {
            chosen = el.dataset.code;
            setLang(chosen);
            draw();
        }
        else if (action === "mic") {
            await testMic();
        }
        else if (action === "tone") {
            await playTone();
        }
        else if (action === "finish") {
            capture.stop();
            prefs.setOnboarded(true);
            navigate(next.startsWith("/app") ? next : "/app", { replace: true });
        }
    });
    draw();
    return () => capture.stop();
}
