/** Voice workspace (/app/new-visit).
 * Start panel: speaking language, consent, live or labelled demo mode, resume a kept draft.
 * Session: Gnani Prisma STT -> transcript -> extraction -> validation -> danger rules -> Timbre read-back
 * -> spoken corrections -> explicit confirmation -> server save -> follow-ups.
 * Everything shown here comes from server events. Nothing is shown as saved until the server sends
 * "saved"; transcripts only appear when Gnani (or the labelled demo) produced them. */
import { unlockAudio } from "../audio/audioContext.js";
import { isPermissionError, MicCapture } from "../audio/capture.js";
import { PcmPlayer } from "../audio/player.js";
import { ClientVAD, FrameRing } from "../audio/vad.js";
import { displayText, durationText, fmtClock, fmtShortDate, followupTitle } from "../components/format.js";
import { missingList, registerSheet } from "../components/recordCard.js";
import { pageHead } from "../components/shell.js";
import { demoBadge, priorityBadge } from "../components/states.js";
import { LANGUAGES, lang, tr, trf } from "../i18n.js";
import { navigate } from "../router.js";
import { api, ApiError } from "../services/api.js";
import { clearPending, loadPending, savePending } from "../services/pendingStore.js";
import { VisitSocket } from "../services/visitSocket.js";
import { activeSession, prefs, saveActiveSession, store } from "../store.js";
import { $, esc, html, on, raw, setHTML, toast } from "../ui/dom.js";
import { icon } from "../ui/icons.js";
const DEMO_NOTES = {
    en: [
        { label: "ANC visit", text: "ANC checkup for beneficiary 1024. Weight is 52 kilos. TT injection recorded. IFA goli given. Next visit is on 20 November." },
        { label: "Fix weight", text: "No, weight is 54 kilos" },
        { label: "Yes, save", text: "Yes, that is correct" },
        { label: "Newborn + danger sign", text: "Newborn visit for beneficiary 1042, the baby has high fever and is not feeding, weight 2.8 kilo" },
    ],
    hi: [
        { label: "ANC विज़िट", text: "एएनसी चेकअप, लाभार्थी आईडी एक शून्य दो चार, वज़न बावन किलो, टीटी का इंजेक्शन लगा, आईएफए गोली दी, अगली विज़िट बीस नवंबर" },
        { label: "सुधार: वज़न", text: "नहीं, वज़न चौवन किलो है" },
        { label: "हाँ, सेव", text: "हाँ, सही है" },
        { label: "नवजात + खतरा", text: "Newborn visit beneficiary 1042, baby ko tez bukhar hai, weight 2.8 kilo, agli visit kal" },
    ],
    kn: [
        { label: "ANC ಭೇಟಿ", text: "ಫಲಾನುಭವಿ ಸಂಖ್ಯೆ 1007, ಎಎನ್‌ಸಿ ಭೇಟಿ, ತೂಕ ಐವತ್ತೆರಡು ಕೆಜಿ, ಐಎಫ್‌ಎ ಮಾತ್ರೆ ಕೊಟ್ಟಿದೆ, ಮುಂದಿನ ಭೇಟಿ ನವೆಂಬರ್ 25" },
        { label: "ತಿದ್ದುಪಡಿ", text: "ಇಲ್ಲ, ತೂಕ ಐವತ್ನಾಲ್ಕು ಕೆಜಿ" },
        { label: "ಹೌದು", text: "ಹೌದು, ಸರಿ" },
        { label: "ನವಜಾತ + ಅಪಾಯ", text: "Newborn visit 1042, ಮಗುವಿಗೆ ಜ್ವರ ಇದೆ, ಹಾಲು ಕುಡಿಯುತ್ತಿಲ್ಲ" },
    ],
};
/** What to say to correct a field, in the speaking language of the visit. */
const CORRECTION_EXAMPLES = {
    beneficiary_id: { en: "No, the ID is 1024", hi: "नहीं, आईडी 1024 है", kn: "ಇಲ್ಲ, ಐಡಿ 1024" },
    visit_type: { en: "No, it is a PNC visit", hi: "नहीं, यह पीएनसी विज़िट है", kn: "ಇಲ್ಲ, ಇದು ಪಿಎನ್‌ಸಿ ಭೇಟಿ" },
    weight_kg: { en: "No, weight is 54 kilo", hi: "नहीं, वज़न 54 किलो है", kn: "ಇಲ್ಲ, ತೂಕ 54 ಕಿಲೋ" },
    vaccinations_given: { en: "Penta 2 was given", hi: "पेंटा दो लगा", kn: "ಪೆಂಟಾ ಎರಡು ಕೊಟ್ಟಿದೆ" },
    ifa_tablets_given: { en: "IFA tablets were given", hi: "आईएफए गोली दी", kn: "ಐಎಫ್‌ಎ ಮಾತ್ರೆ ಕೊಟ್ಟಿದೆ" },
    next_visit_date: { en: "Next visit is on 25 November", hi: "अगली विज़िट पच्चीस नवंबर", kn: "ಮುಂದಿನ ಭೇಟಿ ನವೆಂಬರ್ 25" },
};
const langLabel = (code) => LANGUAGES.find((x) => x.code === code)?.label || code;
export function renderWorkspace(root, ctx) {
    const s = activeSession();
    if (s)
        return renderSession(root, s, ctx);
    renderStart(root);
}
// ====================================================================== start panel
function renderStart(root) {
    let speech = prefs.speechLang();
    let agreed = false;
    let busy = false;
    const draw = () => {
        const svc = store.service;
        const liveOk = svc === "live";
        const reachable = svc === "live" || svc === "demo" || svc === "checking";
        root.innerHTML = html `${raw(pageHead(tr("nav_new_visit"), tr("ws_start_body")))}
      <div id="pending"></div>
      <div class="grid-2">
        <section class="panel" aria-labelledby="start-h"><div class="start-panel">
          <h2 class="h2" id="start-h">${tr("ws_start_title")}</h2>
          <div class="field"><span id="sl-h">${tr("speech_language")}</span>
            <div class="seg" role="radiogroup" aria-labelledby="sl-h">${LANGUAGES.map((x) => raw(html `<button type="button" role="radio"
              aria-checked="${x.code === speech}" aria-pressed="${x.code === speech}" data-action="speech" data-code="${x.code}" lang="${x.code}">${x.label}</button>`))}</div>
            <small class="subtle">${tr(LANGUAGES.find((x) => x.code === speech).sub)}</small></div>
          <label class="check"><input type="checkbox" id="agree" ${agreed ? "checked" : ""}><span>${tr("consent_check")}</span></label>
          ${!reachable ? raw(html `<p class="notice danger" role="alert">${raw(icon("wifiOff"))}<span>${tr("server_unreachable")}</span></p>`)
            : !liveOk && svc !== "checking" ? raw(html `<p class="notice">${raw(icon("info"))}<span>${tr("live_unavailable")}</span></p>`) : ""}
          <div class="chips">
            <button class="btn btn-primary btn-lg" data-action="live" ${agreed && liveOk && !busy ? "" : "disabled"}>${raw(icon("mic"))}${tr("start_live")}</button>
            <button class="btn btn-lg" data-action="demo" ${agreed && reachable && !busy ? "" : "disabled"}>${raw(icon("play"))}${tr("start_demo")}</button>
          </div>
          <p class="small subtle">${tr("demo_explain")}</p>
        </div></section>
        <section class="panel" aria-labelledby="ai-h"><div class="panel-body" style="padding-top:18px;display:grid;gap:12px">
          <h2 class="h3" id="ai-h">${tr("ai_title")}</h2>
          <ul class="ticks">
            <li>${raw(icon("check"))}${tr("ai_does")}</li><li>${raw(icon("close"))}${tr("ai_never")}</li>
            <li>${raw(icon("shield"))}${tr("ai_rules")}</li><li>${raw(icon("lock"))}${tr("ai_data")}</li>
          </ul>
          <hr class="divider">
          <ol class="flow-list compact">
            <li><span class="ic">${raw(icon("mic"))}</span><div><b>${tr("flow_speak")}</b><p class="small muted">${tr("fd_speak")}</p></div></li>
            <li><span class="ic">${raw(icon("eye"))}</span><div><b>${tr("flow_review")}</b><p class="small muted">${tr("fd_review")}</p></div></li>
            <li><span class="ic">${raw(icon("pencil"))}</span><div><b>${tr("flow_correct")}</b><p class="small muted">${tr("fd_correct")}</p></div></li>
            <li><span class="ic">${raw(icon("checkCircle"))}</span><div><b>${tr("flow_confirm")}</b><p class="small muted">${tr("fd_confirm")}</p></div></li>
          </ol>
        </div></section>
      </div>`;
        $("#agree", root)?.addEventListener("change", (e) => { agreed = e.target.checked; draw(); });
        void showPending();
    };
    const showPending = async () => {
        const p = await loadPending();
        if (!p)
            return;
        setHTML($("#pending", root), html `<div class="notice" style="margin-bottom:16px">${raw(icon("clock"))}<div class="grow">
      <b>${tr("pending_drafts")}</b><br><span class="small">${tr("pending_drafts_body")}
      ${p.record?.beneficiary_id ? raw(html ` <span class="mono-id">ID ${String(p.record.beneficiary_id)}</span>`) : ""}</span></div>
      <div class="chips"><button class="btn" data-action="resume">${tr("resume")}</button>
      <button class="btn btn-ghost" data-action="discard">${tr("discard")}</button></div></div>`);
    };
    on(root, "click", async (action, el) => {
        if (action === "speech") {
            speech = el.dataset.code;
            draw();
            return;
        }
        if (action === "resume") {
            const p = await loadPending();
            if (p) {
                saveActiveSession({ session_id: p.session_id, token: p.token, ws_path: "", mode: p.mode, language: p.language });
                sessionStorage.setItem("asha.resume", "1");
                navigate("/app/new-visit", { replace: true });
            }
            return;
        }
        if (action === "discard") {
            await clearPending();
            setHTML($("#pending", root), "");
            return;
        }
        if ((action === "live" || action === "demo") && agreed && !busy) {
            busy = true;
            // This tap is the user gesture that unlocks audio playback and the microphone prompt.
            await unlockAudio();
            try {
                const s = await api.createSession(speech, action === "live" ? "live" : "demo");
                saveActiveSession(s);
                sessionStorage.removeItem("asha.resume");
                navigate("/app/new-visit", { replace: true });
            }
            catch (e) {
                busy = false;
                toast(e instanceof ApiError ? (e.status === 0 ? tr("server_unreachable") : e.message || e.code) : String(e));
                draw();
            }
        }
    });
    draw();
}
const DS_KEY = {
    ready: "ds_ready", connecting: "ds_connecting", listening: "ds_listening", processing: "ds_processing",
    extracting: "ds_extracting", reviewing: "ds_reviewing", speaking: "ds_speaking", confirm: "ds_confirm",
    correcting: "ds_correcting", saving: "ds_saving", completed: "ds_completed", reconnecting: "ds_reconnecting",
    offline: "ds_offline", alert: "ds_alert",
};
const BUSY_STATES = ["TRANSCRIBING", "EXTRACTING", "VALIDATING", "SAFETY_CHECK", "CORRECTING", "SAVING"];
function renderSession(root, info, ctx) {
    const ui = lang();
    const sl = info.language || "en";
    const m = {
        conn: "connecting", stt: "", tts: "none", state: "IDLE", awaiting: "dictation", streaming: false, speaking: false,
        record: {}, meta: {}, changed: new Set(), issues: [], danger: {}, referral: "NONE", lines: [],
        caption: { text: "", kind: "", noAudio: false }, saved: null, canUndo: false, canSave: false,
        demo: info.mode === "demo", recovery: null, micError: "", pendingSaveFailed: false, draftVersion: 0,
        correctHint: "", cancelArmed: false,
    };
    const started = Date.now();
    const socket = new VisitSocket(info.session_id, info.token);
    const player = new PcmPlayer();
    const capture = new MicCapture();
    const vad = new ClientVAD();
    const ring = new FrameRing(10);
    const levels = new Array(64).fill(0);
    let lastVoiceAt = 0;
    let ttfaPending = false;
    let destroyed = false;
    let cancelTimer;
    let waveQueued = false;
    let discarded = false;
    root.innerHTML = html `
    ${raw(pageHead(tr("nav_new_visit"), "", html `<button class="btn" data-action="pause">${raw(icon("pause"))}${tr("btn_pause")}</button>
      <button class="btn btn-quiet-danger" data-action="cancel" id="cancel">${raw(icon("close"))}<span>${tr("btn_cancel")}</span></button>`))}
    ${m.demo ? raw(html `<p class="notice demo-note" role="note">${raw(icon("info"))}<span>${tr("demo_banner")}</span></p>`) : ""}
    <div id="danger"></div>
    <div class="ws" id="ws">
      <section class="panel flush ws-main" aria-label="${tr("nav_new_visit")}">
        <div class="ws-session">
          <span id="live"></span>
          <span>${tr("ws_session")} <b class="mono-id">${info.session_id.slice(0, 8)}</b></span>
          <span>${tr("speech_language")} <b>${langLabel(sl)}</b></span>
          <span>${tr("ws_duration")} <b class="num" id="timer">00:00</b></span>
        </div>
        <ol class="state-line" id="steps"></ol>
        <div class="voice-stage">
          <p class="voice-state" id="vstate" aria-live="polite">${tr("ds_connecting")}</p>
          <p class="voice-hint" id="vhint"></p>
          <button class="mic idle" id="mic" data-action="mic" aria-label="${tr("mic_start")}">${raw(icon("mic"))}</button>
          <canvas class="wave" id="wave" role="img" aria-label="${tr("wave_label")}"></canvas>
          ${m.demo ? raw(html `<p class="xs subtle">${tr("wave_demo")}</p>`) : ""}
        </div>
        <div class="caption" id="caption" aria-live="polite"></div>
        <div class="transcript"><div class="sub-head"><b class="small">${tr("ws_transcript")}</b><span class="xs subtle" id="sttstat"></span></div>
          <div class="lines" id="lines"></div><p class="xs subtle" style="margin-top:6px">${tr("heard_note")}</p></div>
        <div class="controls" id="controls"></div>
        <div id="confirmbar"></div>
        ${m.demo ? raw(html `<div class="demo-strip"><b class="small">${tr("demo_pick")}</b>
          <div class="chips">${DEMO_NOTES[sl].map((d, i) => raw(html `<button class="chip" data-action="demo" data-i="${i}">${d.label}</button>`))}</div>
          <form class="demo-type" id="demotype"><label class="sr-only" for="demotext">${tr("demo_pick")}</label>
            <input class="input" id="demotext" maxlength="400" placeholder="${DEMO_NOTES[sl][1].text}" autocomplete="off">
            <button class="btn" type="submit">${raw(icon("arrowRight"))}<span class="sr-only">${tr("onb_next")}</span></button></form></div>`) : ""}
      </section>
      <aside class="ws-side">
        <section class="panel flush" aria-labelledby="rec-h">
          <div class="panel-head"><h2 class="h3" id="rec-h">${tr("ws_record")}</h2><span class="xs subtle" id="draftver"></span></div>
          <p class="small subtle" style="padding:0 18px 10px">${tr("ws_record_note")}</p>
          <div id="sheet"></div>
        </section>
        <section class="panel flush" aria-labelledby="miss-h">
          <div class="panel-head"><h2 class="h3" id="miss-h">${tr("ws_missing")}</h2></div><div id="missing"></div>
        </section>
        <section class="panel" aria-labelledby="conn-h">
          <div class="panel-head"><h2 class="h3" id="conn-h">${tr("ws_connection")}</h2></div>
          <div class="panel-body"><dl class="kv" id="conn"></dl></div>
        </section>
        <div id="pending"></div>
      </aside>
    </div>`;
    // ------------------------------------------------------------------ derived state
    const busy = () => BUSY_STATES.includes(m.state);
    const ds = () => {
        if (m.saved)
            return "completed";
        if (m.conn === "offline" || m.state === "PENDING" || m.state === "RECOVERY")
            return "offline";
        if (m.conn === "reconnecting" || m.state === "RECONNECTING")
            return "reconnecting";
        if (m.conn === "connecting")
            return "connecting";
        if (m.speaking)
            return m.state === "ALERTING" ? "alert" : "speaking";
        if (m.streaming)
            return "listening";
        if (m.state === "SAVING")
            return "saving";
        if (m.state === "CORRECTING")
            return "correcting";
        if (["EXTRACTING", "VALIDATING", "SAFETY_CHECK"].includes(m.state))
            return "extracting";
        if (m.state === "TRANSCRIBING")
            return "processing";
        if (m.state === "ALERTING")
            return "alert";
        if (m.state === "CONFIRMING" || m.awaiting === "confirmation")
            return "confirm";
        if (m.state === "READBACK" || m.state === "ASKING")
            return "reviewing";
        return "ready";
    };
    const stepIndex = () => {
        if (m.saved)
            return 5;
        if (m.state === "SAVING" || m.state === "CONFIRMING" || m.awaiting === "confirmation")
            return 3;
        if (["READBACK", "CORRECTING", "ALERTING"].includes(m.state) || m.awaiting === "correction")
            return 2;
        if (["TRANSCRIBING", "EXTRACTING", "VALIDATING", "SAFETY_CHECK", "ASKING"].includes(m.state) || m.awaiting.startsWith("field:")
            || Object.keys(m.record).length)
            return 1;
        return 0;
    };
    const hasData = () => !!(m.record.beneficiary_id || m.record.visit_type || m.record.weight_kg);
    const confirmReady = () => !m.saved && m.canSave && (m.state === "CONFIRMING" || m.state === "PENDING" ||
        (m.awaiting === "confirmation" && (m.streaming || m.state === "READBACK")));
    // ------------------------------------------------------------------ rendering
    const drawLive = () => {
        const [cls, text] = m.demo ? ["demo", tr("lb_demo")] : m.conn === "open" ? ["on", tr("lb_live")]
            : m.conn === "offline" || m.conn === "closed" ? ["off", tr("lb_offline")] : ["idle", tr("lb_connecting")];
        setHTML($("#live", root), html `<span class="live-badge ${cls}"><span class="dot"></span>${text}</span>`);
    };
    const drawSteps = () => {
        const idx = stepIndex();
        const d = ds();
        const tone = d === "offline" || d === "alert" ? "bad" : d === "reconnecting" ? "warn" : "";
        const names = ["step_listen", "step_understand", "step_review", "step_confirm", "step_saved"];
        setHTML($("#steps", root), names.map((k, i) => {
            const st = i < idx ? "done" : i === idx ? `now ${tone}` : "";
            return html `<li class="s ${st}" ${i === idx ? raw('aria-current="step"') : ""}>${i < idx ? raw(icon("check")) : ""}${tr(k)}</li>`;
        }).join(""));
    };
    const drawStage = () => {
        const d = ds();
        const vs = $("#vstate", root);
        vs.textContent = tr(DS_KEY[d]);
        vs.className = `voice-state ${d === "alert" || d === "offline" ? "bad-t" : ""}`;
        let hint = "";
        if (m.micError)
            hint = m.micError;
        else if (m.correctHint && !m.saved)
            hint = m.correctHint;
        else if (m.demo && (d === "ready" || d === "reviewing" || d === "confirm"))
            hint = d === "confirm" ? tr("hint_confirm") : tr("hint_demo");
        else
            hint = { ready: tr("hint_tap"), connecting: "", listening: tr("hint_listening"), processing: tr("hint_processing"),
                extracting: tr("hint_processing"), reviewing: tr("hint_tap"), speaking: tr("hint_speaking"), confirm: tr("hint_confirm"),
                correcting: tr("hint_processing"), saving: tr("hint_saving"), completed: "", reconnecting: tr("hint_reconnecting"),
                offline: tr("hint_offline"), alert: tr("hint_speaking") }[d];
        $("#vhint", root).textContent = hint;
        const mic = $("#mic", root);
        if (mic) {
            let cls = "idle", ic = icon("mic"), label = tr("mic_start");
            if (m.speaking) {
                cls = "talking";
                ic = icon("stop");
                label = tr("mic_interrupt");
            }
            else if (m.streaming) {
                cls = "speaking";
                ic = icon("stop");
                label = tr("mic_stop");
            }
            else if (busy()) {
                cls = "busy";
                label = tr(DS_KEY[d]);
            }
            else if (d === "offline" || d === "reconnecting" || d === "connecting") {
                cls = "off";
                label = tr(DS_KEY[d]);
            }
            mic.className = `mic ${cls}`;
            mic.innerHTML = ic;
            mic.setAttribute("aria-label", label);
            mic.disabled = m.demo || d === "offline" || d === "connecting" || d === "reconnecting";
        }
    };
    const drawCaption = () => {
        if (!m.caption.text) {
            setHTML($("#caption", root), html `<span class="who">${raw(icon("speaker"))}</span><p class="subtle">${tr("assistant")}</p>`);
            return;
        }
        setHTML($("#caption", root), html `<span class="who">${raw(icon("speaker"))}</span><p>${displayText(m.caption.text)}
      ${m.caption.noAudio ? raw(html `<span class="meta">${tr(m.demo ? "demo_text_only" : "audio_unavailable")}</span>`) : ""}</p>`);
    };
    const drawLines = () => {
        setHTML($("#lines", root), m.lines.length ? m.lines.slice(-8).map((x) => html `<p>${x}</p>`).join("")
            : html `<p class="subtle small" style="border:0;padding:0">${tr("transcript_empty")}</p>`);
        const el = $("#lines", root);
        if (el)
            el.scrollTop = el.scrollHeight;
        const st = $("#sttstat", root);
        if (st)
            st.textContent = m.demo ? tr("mode_demo") : m.stt;
    };
    const drawDanger = () => {
        const pos = Object.values(m.danger).filter((d) => d.status === "POSITIVE");
        const rev = Object.values(m.danger).filter((d) => d.status === "REVIEW" || d.status === "UNCERTAIN");
        let out = "";
        if (pos.length) {
            out += html `<section class="danger-panel" role="alert">
        <p class="h3">${raw(icon("alert"))}${tr("danger_title")}</p>
        <p>${pos.map((d) => d.label?.[ui] || d.label?.en).join(", ")}</p>
        ${pos.map((d) => raw(html `<p class="why">${tr("danger_why")} ${d.rule_id}: ${tr("danger_heard")} “${d.matched_phrase}”</p>`))}
        <p class="why">${tr("danger_source")}</p></section>`;
        }
        if (rev.length) {
            out += html `<section class="danger-panel review" role="status"><p class="h3">${raw(icon("info"))}${tr("danger_review")}</p>
        ${rev.map((d) => raw(html `<p class="why">${d.label?.[ui] || d.label?.en}: “${d.matched_phrase}” (${d.reason})</p>`))}</section>`;
        }
        setHTML($("#danger", root), out ? `<div class="danger-stack">${out}</div>` : "");
    };
    const drawSheet = () => {
        const canFix = !m.saved && hasData() && m.conn === "open";
        setHTML($("#sheet", root), registerSheet(m.record, m.meta, ui, { changed: m.changed, issues: m.issues, correctable: canFix }));
        setHTML($("#missing", root), missingList(m.record, m.meta, ui));
        const dv = $("#draftver", root);
        if (dv)
            dv.textContent = m.draftVersion ? `v${m.draftVersion}` : "";
    };
    const drawConn = () => {
        const sock = m.conn === "open" ? tr("conn_open") : m.conn === "reconnecting" || m.conn === "connecting" ? tr("ds_reconnecting") : tr("conn_closed");
        const stt = m.demo ? tr("not_used_demo") : m.stt || tr("stt_idle");
        const tts = m.demo ? tr("not_used_demo") : m.tts === "ok" ? tr("tts_ok") : m.tts === "text" ? tr("tts_text_only") : tr("tts_none");
        setHTML($("#conn", root), html `<dt>${tr("conn_socket")}</dt><dd>${sock}</dd>
      <dt>${tr("conn_stt")}</dt><dd>${stt}</dd><dt>${tr("conn_tts")}</dt><dd>${tts}</dd>`);
    };
    const drawControls = () => {
        if (m.saved) {
            setHTML($("#controls", root), "");
            setHTML($("#confirmbar", root), "");
            return;
        }
        const b = [];
        b.push(html `<button class="btn" data-action="repeat" ${hasData() && m.conn === "open" ? "" : "disabled"}>${raw(icon("replay"))}${tr("btn_repeat")}</button>`);
        b.push(html `<button class="btn" data-action="undo" ${m.canUndo && m.conn === "open" ? "" : "disabled"}>${raw(icon("undo"))}${tr("btn_undo")}</button>`);
        if (m.awaiting.startsWith("field:"))
            b.push(html `<button class="btn" data-action="skip">${raw(icon("skip"))}${tr("btn_skip")}</button>`);
        if (m.micError && !m.demo)
            b.push(html `<button class="btn" data-action="retry-mic">${raw(icon("mic"))}${tr("btn_retry_mic")}</button>`);
        if (m.conn === "offline")
            b.push(html `<button class="btn" data-action="reconnect">${raw(icon("refresh"))}${tr("btn_reconnect")}</button>`);
        setHTML($("#controls", root), b.join(""));
        let bar = "";
        if (confirmReady())
            bar += html `<button class="btn btn-primary btn-lg btn-block" data-action="confirm">${raw(icon("check"))}${tr("btn_confirm")}</button>
      <p class="xs subtle">${tr("correction_hint")}</p>`;
        if (m.pendingSaveFailed)
            bar += html `<button class="btn btn-block" data-action="retry">${raw(icon("refresh"))}${tr("btn_retry")}</button>`;
        setHTML($("#confirmbar", root), bar ? `<div class="confirm-bar">${bar}</div>` : "");
    };
    const drawCancel = () => {
        const c = $("#cancel", root);
        if (c)
            c.querySelector("span").textContent = m.cancelArmed ? tr("btn_cancel_confirm") : tr("btn_cancel");
    };
    const drawWave = () => {
        waveQueued = false;
        const c = $("#wave", root);
        if (!c)
            return;
        const dpr = window.devicePixelRatio || 1;
        const w = c.clientWidth || 300, h = c.clientHeight || 56;
        if (c.width !== Math.round(w * dpr)) {
            c.width = Math.round(w * dpr);
            c.height = Math.round(h * dpr);
        }
        const g = c.getContext("2d");
        if (!g)
            return;
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, h);
        const n = levels.length;
        const step = w / n;
        const bw = Math.max(2, step - 3);
        g.fillStyle = m.streaming ? "#1F5B40" : "#B9CDBF";
        for (let i = 0; i < n; i++) {
            const bh = Math.max(2, levels[i] * (h - 6));
            const x = i * step + (step - bw) / 2;
            const y = (h - bh) / 2;
            if (g.roundRect) {
                g.beginPath();
                g.roundRect(x, y, bw, bh, 1.5);
                g.fill();
            }
            else
                g.fillRect(x, y, bw, bh);
        }
    };
    const pushLevel = (rms) => {
        levels.push(Math.min(1, rms * 9));
        levels.shift();
        const mic = $("#mic", root);
        if (mic)
            mic.style.setProperty("--level", String(m.streaming ? Math.min(1, rms * 9) : 0));
        if (!waveQueued) {
            waveQueued = true;
            requestAnimationFrame(drawWave);
        }
    };
    const drawSummary = () => {
        const s = m.saved;
        const rec = s.record || m.record;
        const fus = (s.followups || []);
        const pos = (rec?.danger_details || []).filter((d) => d.status === "POSITIVE");
        root.innerHTML = html `
      <div class="saved-head" role="status">${raw(icon("checkCircle"))}<div><b>${tr("saved_title")}</b>
        <span>${s.saved_at ? trf("saved_at", { t: fmtClock(s.saved_at, ui) }) : tr("st_confirmed")}</span></div>
        ${m.demo ? raw(`<span style="margin-left:auto">${demoBadge("demo")}</span>`) : ""}</div>
      ${s.referral_status === "REFER_NOW" && pos.length ? raw(html `<section class="danger-panel" role="alert" style="margin-top:14px">
        <p class="h3">${raw(icon("alert"))}${tr("danger_title")}</p>
        <p>${pos.map((d) => d.label?.[ui] || d.label?.en).join(", ")}</p><p class="why">${tr("danger_source")}</p></section>`) : ""}
      <div class="grid-2" style="margin-top:16px">
        <section class="panel flush" aria-labelledby="sr-h"><div class="panel-head"><h2 class="h3" id="sr-h">${tr("vd_record")}</h2></div>
          ${raw(registerSheet(rec, m.meta, ui))}</section>
        <div style="display:grid;gap:16px;align-content:start">
          <section class="panel flush" aria-labelledby="fu-h"><div class="panel-head"><h2 class="h3" id="fu-h">${tr("next_actions")}</h2></div>
            ${fus.length ? raw(html `<ul class="rows">${fus.map((f) => raw(html `<li><div class="row-item"><span class="pri ${f.priority}"></span>
              <span class="grow"><span class="row-title wrap">${followupTitle(f, ui)}</span>
              <span class="row-sub">${f.due_date ? fmtShortDate(f.due_date, ui) : tr("no_date")}</span></span>${raw(priorityBadge(f.priority))}</div></li>`))}</ul>`)
            : raw(html `<p class="small subtle" style="padding:0 18px 16px">${tr("prof_no_followups")}</p>`)}
          </section>
          <div class="chips">
            <a class="btn btn-primary" href="/app/visits/${esc(s.visit_id)}">${raw(icon("file"))}${tr("view_record")}</a>
            <button class="btn" data-action="next">${raw(icon("mic"))}${tr("start_next")}</button>
            <a class="btn btn-ghost" href="/app">${tr("go_overview")}</a>
          </div>
        </div>
      </div>`;
    };
    const drawAll = () => {
        if (m.saved)
            return;
        drawLive();
        drawSteps();
        drawStage();
        drawCaption();
        drawLines();
        drawDanger();
        drawSheet();
        drawConn();
        drawControls();
        drawCancel();
    };
    const drawStatus = () => {
        if (m.saved)
            return;
        drawLive();
        drawSteps();
        drawStage();
        drawConn();
        drawControls();
    };
    drawAll();
    drawWave();
    const timer = window.setInterval(() => {
        const el = $("#timer", root);
        if (el)
            el.textContent = durationText(Date.now() - started);
    }, 1000);
    const onResize = () => drawWave();
    window.addEventListener("resize", onResize);
    const keepPending = async (reason, kind) => {
        if (m.saved || !hasData())
            return false;
        const ok = await savePending({ session_id: info.session_id, token: info.token, language: info.language, mode: info.mode,
            record: m.record, updated_at: new Date().toISOString(), reason, kind });
        if (!destroyed)
            setHTML($("#pending", root), html `<p class="notice">${raw(icon("lock"))}<span>${tr("st_pending_sync")}: ${reason}</span></p>`);
        return ok;
    };
    // ------------------------------------------------------------------ audio wiring
    player.onStarted = (uid) => {
        socket.send({ type: "playback_started", utterance_id: uid });
        if (ttfaPending && lastVoiceAt) {
            socket.send({ type: "client_metric", name: "client_ttfa_ms", value_ms: Math.round(performance.now() - lastVoiceAt) });
            ttfaPending = false;
        }
    };
    player.onEnded = (uid) => {
        socket.send({ type: "playback_ended", utterance_id: uid });
        m.speaking = player.playing;
        drawStatus();
    };
    const bargeIn = (manual) => {
        player.stopAll();
        m.speaking = false;
        socket.send({ type: manual ? "cancel_tts" : "barge_in" });
        drawStatus();
    };
    capture.onFrame = (frame, rms) => {
        if (m.streaming) {
            socket.sendAudio(frame);
            if (vad.update(rms)) {
                lastVoiceAt = performance.now();
                ttfaPending = true;
            }
            pushLevel(rms);
            return;
        }
        ring.push(frame);
        if (player.playing && store.bargeIn) {
            vad.update(rms, true);
            if (vad.run >= 8) {
                vad.run = 0;
                bargeIn(false);
            }
        }
        else {
            vad.update(rms);
        }
        pushLevel(m.speaking ? 0 : rms * 0.5);
    };
    const ensureMic = async () => {
        if (capture.running || m.demo)
            return true;
        try {
            await unlockAudio();
            await capture.start();
            m.micError = "";
            drawStatus();
            return true;
        }
        catch (e) {
            m.micError = isPermissionError(e) ? tr("mic_denied") : !navigator.mediaDevices?.getUserMedia ? tr("mic_unsupported")
                : String(e.message || e);
            drawStatus();
            return false;
        }
    };
    // ------------------------------------------------------------------ server events
    socket.onStatus = (s) => {
        m.conn = s;
        if (s === "offline" || s === "reconnecting") {
            m.streaming = false;
            void keepPending(tr(s === "offline" ? "ds_offline" : "ds_reconnecting"), "sync");
        }
        drawStatus();
        drawSheet();
    };
    socket.onAudio = (uid, data, off) => player.push(uid, data, off);
    socket.onEvent = (e) => {
        switch (e.type) {
            case "session":
                m.demo = !!e.demo;
                break;
            case "state":
                m.state = e.state;
                if (e.awaiting)
                    m.awaiting = e.awaiting;
                if (e.state === "SUMMARY")
                    m.streaming = false;
                break;
            case "listen":
                m.streaming = !!e.on;
                if (e.awaiting)
                    m.awaiting = e.awaiting;
                if (e.on && e.reason === "barge_in")
                    for (const f of ring.drain())
                        socket.sendAudio(f);
                if (!e.on)
                    pushLevel(0);
                break;
            case "stt_status":
                m.stt = tr({ connected: "stt_connected", unavailable: "stt_unavailable", speech_start: "stt_voice", processing: "stt_transcribing",
                    connecting: "lb_connecting", reconnecting: "ds_reconnecting", closed: "stt_idle", error: "stt_unavailable" }[e.status] || "stt_idle");
                drawLines();
                break;
            case "transcript":
                if (e.text) {
                    m.lines.push(e.text);
                    m.correctHint = "";
                }
                drawLines();
                break;
            case "turn_transcript":
                if (e.source === "demo") {
                    m.lines.push(e.text);
                    m.correctHint = "";
                    drawLines();
                }
                break;
            case "draft":
                m.record = e.record || {};
                m.meta = e.meta || {};
                m.changed = new Set(e.changed_fields || []);
                m.issues = e.issues || [];
                m.danger = e.danger || {};
                m.referral = e.referral_status;
                m.canUndo = !!e.can_undo;
                m.canSave = !!e.can_save;
                m.draftVersion = e.draft_version;
                drawSheet();
                drawDanger();
                break;
            case "agent_say":
                m.caption = { text: e.text, kind: e.kind, noAudio: !e.audio };
                if (e.audio) {
                    player.begin(e.utterance_id, e.sample_rate || 24000);
                    m.speaking = true;
                    m.tts = "ok";
                }
                else {
                    m.tts = "text";
                    window.setTimeout(() => socket.send({ type: "playback_ended", utterance_id: e.utterance_id }), Math.min(6000, 900 + 30 * String(e.text).length));
                }
                drawCaption();
                break;
            case "tts_end":
                player.end(e.utterance_id);
                break;
            case "tts_unavailable":
                m.caption.noAudio = true;
                m.tts = "text";
                player.end(e.utterance_id);
                drawCaption();
                break;
            case "tts_cancel":
                player.drop(e.utterance_ids || []);
                m.speaking = player.playing;
                break;
            case "danger_alert":
                for (const s of e.signs || [])
                    m.danger[s.id] = s;
                try {
                    navigator.vibrate?.([250, 120, 250]);
                }
                catch { /* not supported */ }
                drawDanger();
                break;
            case "recovery":
                m.recovery = e;
                m.streaming = false;
                void keepPending(e.message || e.code, "sync");
                break;
            case "save_failed":
                m.pendingSaveFailed = true;
                void keepPending("save failed", "sync");
                break;
            case "saved":
                if (e.record || e.resumed) {
                    m.saved = { ...e, record: e.record || m.record };
                    m.streaming = false;
                    capture.stop();
                    void clearPending();
                    saveActiveSession(null);
                    ctx.refreshShell();
                    drawSummary();
                    return;
                }
                break;
            case "error":
                if (!e.recoverable || e.code === "stt_budget")
                    toast(e.message || e.code);
                break;
        }
        drawStatus();
    };
    // ------------------------------------------------------------------ user actions
    const leave = async (discard) => {
        if (discard) {
            discarded = true;
            await clearPending();
            saveActiveSession(null);
            toast(tr("ws_cancelled"));
        }
        else {
            const kept = await keepPending(tr("st_draft"), "draft");
            saveActiveSession(null);
            if (kept)
                toast(tr("ws_kept"));
        }
        navigate("/app");
    };
    on(root, "click", async (action, el) => {
        if (action === "mic") {
            if (!(await ensureMic()))
                return;
            if (m.speaking || player.playing)
                bargeIn(true);
            else if (m.streaming)
                socket.send({ type: "stop_listening" });
            else
                socket.send({ type: "start_listening", reason: "user" });
        }
        else if (action === "undo")
            socket.send({ type: "action", action: "undo" });
        else if (action === "repeat") {
            player.stopAll();
            m.speaking = false;
            socket.send({ type: "action", action: "repeat" });
        }
        else if (action === "skip")
            socket.send({ type: "action", action: "skip" });
        else if (action === "confirm") {
            player.stopAll();
            m.speaking = false;
            socket.send({ type: "action", action: "confirm" });
        }
        else if (action === "retry") {
            m.pendingSaveFailed = false;
            socket.send({ type: "action", action: "retry_save" });
            drawControls();
        }
        else if (action === "retry-mic") {
            m.micError = "";
            await ensureMic();
        }
        else if (action === "reconnect")
            socket.retry();
        else if (action === "correct") {
            const f = el.dataset.field || "";
            const label = tr(("f_" + f)).toLowerCase();
            m.correctHint = trf("hint_correct_field", { field: label, example: CORRECTION_EXAMPLES[f]?.[sl] || "" });
            drawStage();
            if (m.demo) {
                $("#demotext", root)?.focus();
                return;
            }
            if (!(await ensureMic()))
                return;
            if (m.speaking || player.playing)
                bargeIn(true);
            if (!m.streaming)
                socket.send({ type: "start_listening", reason: "user" });
        }
        else if (action === "demo") {
            const note = DEMO_NOTES[sl][Number(el.dataset.i)];
            if (note)
                socket.send({ type: "demo_utterance", text: note.text });
        }
        else if (action === "pause")
            await leave(false);
        else if (action === "cancel") {
            if (!m.cancelArmed) {
                m.cancelArmed = true;
                drawCancel();
                window.clearTimeout(cancelTimer);
                cancelTimer = window.setTimeout(() => { m.cancelArmed = false; drawCancel(); }, 4000);
            }
            else
                await leave(true);
        }
        else if (action === "next") {
            saveActiveSession(null);
            navigate("/app/new-visit", { replace: true });
        }
    });
    root.addEventListener("submit", (ev) => {
        const form = ev.target.closest("#demotype");
        if (!form)
            return;
        ev.preventDefault();
        const input = $("#demotext", root);
        const text = input.value.trim();
        if (text) {
            socket.send({ type: "demo_utterance", text });
            input.value = "";
        }
    });
    socket.connect();
    if (!m.demo)
        void ensureMic();
    try {
        sessionStorage.setItem("asha.resume", "1");
    }
    catch { /* storage unavailable */ }
    return () => {
        if (destroyed)
            return;
        // Leaving mid-visit (e.g. via the sidebar) keeps an encrypted draft so the visit can be resumed.
        if (!m.saved && !discarded)
            void keepPending(tr("st_draft"), "draft");
        destroyed = true;
        window.clearInterval(timer);
        window.clearTimeout(cancelTimer);
        window.removeEventListener("resize", onResize);
        player.stopAll();
        capture.stop();
        socket.close();
    };
}
