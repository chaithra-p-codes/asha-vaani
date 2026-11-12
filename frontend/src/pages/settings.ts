/** Settings (/app/settings): General, Audio, Services, Privacy and data.
 * UI language and speaking language are separate preferences, both stored on this device. */
import { unlockAudio } from "../audio/audioContext.js";
import { isPermissionError, MicCapture } from "../audio/capture.js";
import { pageHead } from "../components/shell.js";
import { Key, Lang, LANGUAGES, lang, setLang, tr, trf } from "../i18n.js";
import { navigate } from "../router.js";
import { api } from "../services/api.js";
import { clearPending } from "../services/pendingStore.js";
import { prefs, saveActiveSession, setBargeIn, store } from "../store.js";
import { $, html, on, raw, setHTML, toast } from "../ui/dom.js";
import { icon } from "../ui/icons.js";

const METRIC_LABELS: Record<string, string> = {
  client_ttfa_ms: "End of speech to first agent audio (phone)",
  server_end_of_speech_to_first_audio_ms: "End of speech to first audio sent (server)",
  endpoint_wait_ms: "End of speech to endpoint decided",
  transcript_ready_after_turn_end_ms: "Endpoint to final transcript",
  prisma_reported_latency_ms: "Prisma reported latency",
  tts_first_chunk_ms: "Timbre request to first chunk",
  rule_extraction_ms: "Rule extraction",
  llm_extraction_ms: "LLM extraction (Gemini)",
  danger_rules_ms: "Danger rules",
  stt_open_ms: "Prisma connect",
};

export function renderSettings(root: HTMLElement, langChanged: () => void, refreshShell: () => void): () => void {
  const mic = new MicCapture();
  let micTimer: number | undefined;
  let deleteArmed = false;
  let deleteTimer: number | undefined;

  const seg = (action: string, current: Lang) => LANGUAGES.map((x) => html`<button type="button" data-action="${action}" data-code="${x.code}"
    aria-pressed="${x.code === current}" lang="${x.code}">${x.label}</button>`).join("");

  const draw = () => {
    root.innerHTML = html`${raw(pageHead(tr("nav_settings")))}
      <nav class="chips jump" aria-label="${tr("nav_settings")}">
        <a class="chip" href="#set-general" data-jump="general">${tr("set_general")}</a><a class="chip" href="#set-audio" data-jump="audio">${tr("set_audio")}</a>
        <a class="chip" href="#set-services" data-jump="services">${tr("set_services")}</a><a class="chip" href="#set-privacy" data-jump="privacy">${tr("set_privacy")}</a></nav>
      <div class="settings">
      <section class="panel" id="set-general" aria-labelledby="g-h"><div class="panel-head"><h2 class="h3" id="g-h">${tr("set_general")}</h2></div>
        <div class="panel-body set-rows">
          <div class="set-row"><div><b id="ul-h">${tr("set_language")}</b><p class="small subtle">${tr("set_language_hint")}</p></div>
            <div class="seg" role="group" aria-labelledby="ul-h">${raw(seg("ui-lang", lang()))}</div></div>
          <div class="set-row"><div><b id="sl-h">${tr("set_speech_lang")}</b><p class="small subtle">${tr("set_speech_lang_hint")}</p></div>
            <div class="seg" role="group" aria-labelledby="sl-h">${raw(seg("speech-lang", prefs.speechLang()))}</div></div>
          <form class="set-row" id="nameform"><div><label for="wname"><b>${tr("set_name")}</b></label><p class="small subtle">${tr("onb_name_hint")}</p></div>
            <div class="inline-form"><input class="input" id="wname" maxlength="40" value="${prefs.workerName()}" autocomplete="given-name">
              <button class="btn" type="submit">${tr("set_save")}</button></div></form>
        </div></section>

      <section class="panel" id="set-audio" aria-labelledby="a-h"><div class="panel-head"><h2 class="h3" id="a-h">${tr("set_audio")}</h2></div>
        <div class="panel-body set-rows">
          <div class="set-row col"><div><b>${tr("set_mic")}</b><p class="small subtle" id="micinfo" role="status">${tr("set_mic_off")}</p></div>
            <div class="meter" role="meter" aria-label="${tr("wave_label")}" aria-valuemin="0" aria-valuemax="100"><div id="lvl"></div></div>
            <div><button class="btn" data-action="mic">${raw(icon("mic"))}${tr("set_mic_btn")}</button></div></div>
          <div class="set-row col"><div><b>${tr("set_play")}</b><p class="small subtle">${tr("set_play_note")}</p></div>
            <div class="chips"><button class="btn" data-action="play" ${store.service === "live" ? "" : "disabled"}>${raw(icon("speaker"))}${tr("set_play_btn")}</button></div>
            <p class="small" id="playinfo" role="status">${store.service === "live" ? "" : tr("svc_key_missing")}</p></div>
          <div class="set-row"><div><label for="barge"><b>${tr("set_bargein")}</b></label><p class="small subtle">${tr("set_bargein_hint")}</p></div>
            <input type="checkbox" class="switch" id="barge" role="switch" ${store.bargeIn ? "checked" : ""}></div>
        </div></section>

      <section class="panel" id="set-services" aria-labelledby="s-h"><div class="panel-head"><h2 class="h3" id="s-h">${tr("set_conn")}</h2>
        <button class="btn btn-ghost" data-action="refresh">${raw(icon("refresh"))}${tr("retry")}</button></div>
        <div class="panel-body"><dl class="kv" id="conn"><dt>${tr("loading")}</dt><dd></dd></dl>
          <h3 class="h3 sub-title">${tr("set_latency")}</h3><dl class="kv num" id="lat"><dt>${tr("loading")}</dt><dd></dd></dl></div></section>

      <section class="panel" id="set-privacy" aria-labelledby="p-h"><div class="panel-head"><h2 class="h3" id="p-h">${tr("set_privacy")}</h2></div>
        <div class="panel-body set-rows">
          <div class="set-row col"><b>${tr("set_ai")}</b><p class="small">${tr("ai_body")}</p></div>
          <div class="set-row col"><b>${tr("privacy_title")}</b><p class="small">${tr("privacy_body")}</p>
            <p class="small subtle" id="retention">${tr("synthetic_note")}</p></div>
          <div class="set-row"><div><b>${tr("set_reload")}</b><p class="small subtle">${tr("set_reload_hint")}</p></div>
            <button class="btn" data-action="reload-demo">${raw(icon("refresh"))}${tr("set_reload")}</button></div>
          <div class="set-row"><div><b>${tr("set_delete")}</b><p class="small subtle">${tr("set_delete_hint")}</p></div>
            <button class="btn btn-quiet-danger" data-action="delete" id="delbtn">${raw(icon("trash"))}<span>${tr("set_delete")}</span></button></div>
          <div class="set-row"><div><b>${tr("set_reset_onb")}</b></div>
            <button class="btn btn-ghost" data-action="onboarding">${tr("set_reset_onb")}</button></div>
        </div></section>
      </div>`;
    $("#barge", root)?.addEventListener("change", (e) => setBargeIn((e.target as HTMLInputElement).checked));
    void loadInfo();
  };

  const loadInfo = async () => {
    try {
      const [health, cfg, st, met] = await Promise.all([api.health(), api.config(), api.status(), api.metrics()]);
      store.config = cfg;
      const usage = (st.usage_recorded as any[]).map((u) => `${u.alias} ${u.service}: ${Math.round(u.total)} ${u.unit}`).join("; ");
      const rows: [Key, string][] = [
        ["svc_backend", trf("svc_backend_ok", { v: health.version })],
        ["svc_stt", `${cfg.stt_model} (${cfg.stt_format})`],
        ["svc_tts", `${cfg.tts_model}, ${cfg.tts_voice}, ${cfg.tts_sample_rate} Hz`],
        ["svc_key", st.gnani_configured ? tr("svc_key_ok") : tr("svc_key_missing")],
        ["svc_extraction", cfg.llm_model ? `${cfg.llm_provider} ${cfg.llm_model}` : cfg.llm_provider],
        ["svc_endpointing", `${cfg.endpoint_silence_ms.dictation} ms / ${cfg.endpoint_silence_ms.short_answer} ms`],
        ["svc_usage", usage || tr("svc_usage_none")],
      ];
      if (st.llm?.last_error) rows.push(["svc_last_error", String(st.llm.last_error)]);
      setHTML($("#conn", root), rows.map(([k, v]) => html`<dt>${tr(k)}</dt><dd>${v}</dd>`).join(""));
      const play = root.querySelector('[data-action="play"]') as HTMLButtonElement | null;
      if (play) play.disabled = !st.gnani_configured;
      const pi = $("#playinfo", root);
      if (pi && !pi.dataset.used) pi.textContent = st.gnani_configured ? "" : tr("svc_key_missing");
      const ret = $("#retention", root);
      if (ret) ret.textContent = `${tr("synthetic_note")} ${trf("set_retention", { h: cfg.retention_hours })}`;
      const mm = met.metrics as Record<string, { n: number; median_ms: number; p95_ms: number }>;
      const keys = Object.keys(mm);
      setHTML($("#lat", root), keys.length ? keys.map((k) => html`<dt>${METRIC_LABELS[k] || k}</dt>
        <dd>median ${mm[k].median_ms} ms, p95 ${mm[k].p95_ms} ms, n=${mm[k].n}</dd>`).join("") : html`<dt>${tr("none_yet")}</dt><dd></dd>`);
    } catch {
      setHTML($("#conn", root), html`<dt>${tr("svc_backend")}</dt><dd class="danger-t">${tr("svc_offline")}</dd>`);
      setHTML($("#lat", root), "");
    }
  };

  const stopMic = () => {
    mic.stop();
    window.clearTimeout(micTimer);
    const bar = $("#lvl", root);
    if (bar) bar.style.width = "0%";
    const info = $("#micinfo", root);
    if (info) info.textContent = tr("set_mic_off");
  };

  on(root, "click", async (action, el) => {
    if (action === "ui-lang") { setLang(el.dataset.code as Lang); langChanged(); return; }
    if (action === "speech-lang") { prefs.setSpeechLang(el.dataset.code as Lang); draw(); toast(tr("set_saved")); return; }
    if (action === "refresh") { void loadInfo(); refreshShell(); return; }
    if (action === "mic") {
      if (mic.running) { stopMic(); return; }
      try {
        await unlockAudio();
        mic.onFrame = (_f, rms) => {
          const bar = $("#lvl", root);
          if (bar) bar.style.width = `${Math.min(100, rms * 900)}%`;
        };
        await mic.start();
        $("#micinfo", root)!.textContent = tr("set_mic_ok");
        micTimer = window.setTimeout(stopMic, 8000);
      } catch (e) {
        $("#micinfo", root)!.textContent = isPermissionError(e) ? tr("mic_denied") : String((e as Error)?.message || e);
      }
      return;
    }
    if (action === "play") {
      const info = $("#playinfo", root)!;
      info.dataset.used = "1";
      info.textContent = tr("loading");
      try {
        await unlockAudio();
        const resp = await fetch(`/api/diagnostics/tts?lang=${prefs.speechLang()}`);
        if (!resp.ok) {
          const j = await resp.json().catch(() => ({}));
          info.textContent = (j as any).message || String(resp.status);
          return;
        }
        const ms = resp.headers.get("X-First-Chunk-Ms");
        const cached = resp.headers.get("X-From-Cache") === "true";
        const url = URL.createObjectURL(await resp.blob());
        const audio = new Audio(url);
        await audio.play();
        info.textContent = `Gnani Timbre v3.0: ${cached ? "cached fixed phrase" : `first chunk ${ms} ms`}`;
      } catch (e) {
        info.textContent = String(e);
      }
      return;
    }
    if (action === "reload-demo") {
      (el as HTMLButtonElement).disabled = true;
      try {
        const r = await api.seedDemo(true);
        toast(trf("reloaded", { n: r.total_seed_visits }));
        refreshShell();
      } catch {
        toast(tr("action_failed"));
      } finally {
        (el as HTMLButtonElement).disabled = false;
      }
      return;
    }
    if (action === "delete") {
      const btn = $("#delbtn", root)!;
      if (!deleteArmed) {
        deleteArmed = true;
        btn.classList.add("btn-danger");
        btn.querySelector("span")!.textContent = tr("set_delete_tap");
        btn.setAttribute("aria-label", tr("set_delete_confirm"));
        deleteTimer = window.setTimeout(() => {
          deleteArmed = false;
          btn.classList.remove("btn-danger");
          btn.querySelector("span")!.textContent = tr("set_delete");
          btn.removeAttribute("aria-label");
        }, 5000);
        return;
      }
      window.clearTimeout(deleteTimer);
      deleteArmed = false;
      try {
        await api.deleteDemo();
        await clearPending();
        saveActiveSession(null);
        toast(tr("deleted"));
        refreshShell();
        draw();
      } catch {
        toast(tr("action_failed"));
      }
      return;
    }
    if (action === "onboarding") { prefs.setOnboarded(false); navigate("/onboarding"); }
  });
  root.addEventListener("submit", (ev) => {
    if (!(ev.target as HTMLElement).closest("#nameform")) return;
    ev.preventDefault();
    prefs.setWorkerName(($("#wname", root) as HTMLInputElement).value);
    toast(tr("set_saved"));
  });
  root.addEventListener("click", (ev) => {
    const a = (ev.target as HTMLElement).closest("[data-jump]") as HTMLElement | null;
    if (!a) return;
    ev.preventDefault();
    document.getElementById(`set-${a.dataset.jump}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  draw();
  return () => { stopMic(); window.clearTimeout(deleteTimer); };
}
