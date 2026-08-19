// BODDOS phone UI — talks to the local node it was served from.
const $ = (s) => document.querySelector(s);
let TOKEN = localStorage.getItem("boddos_token") || "";

async function api(p, opts = {}) {
  const headers = Object.assign({}, opts.headers || {});
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  const r = await fetch(p, Object.assign({}, opts, { headers }));
  if (r.status === 401) {
    const t = prompt("This node requires an API token. Paste it:");
    if (t) { TOKEN = t.trim(); localStorage.setItem("boddos_token", TOKEN); return api(p, opts); }
  }
  return r.json();
}
const history = [];
let curLoc = null;

// ---- geolocation (used for weather + duress + tracker context) ----
if (navigator.geolocation) {
  navigator.geolocation.watchPosition(
    (p) => (curLoc = { lat: p.coords.latitude, lon: p.coords.longitude }),
    () => {}, { enableHighAccuracy: true, maximumAge: 30000 }
  );
}

// ---- tabs ----
document.querySelectorAll("#tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "aware") refreshSensors();
    if (b.dataset.tab === "safety") refreshSafety();
    if (b.dataset.tab === "vision") { listCamDevices(); refreshExtCams(); }
  };
});

// ---- health + models ----
async function boot() {
  try {
    const h = await api("/health");
    $("#node").textContent = `${h.node} · ${h.role}`;
    const m = await api("/api/models");
    const sel = $("#modelSel");
    sel.innerHTML = "";
    const opt = (v) => { const o = document.createElement("option"); o.value = v; o.textContent = v; sel.appendChild(o); };
    opt(m.default);
    (m.local || []).forEach((x) => { if (x !== m.default) opt(x); });
  } catch (e) { $("#node").textContent = "offline"; }
}

// ---- advisor chat ----
function bubble(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + role;
  d.textContent = text;
  $("#chat").appendChild(d);
  $("#chat").scrollTop = $("#chat").scrollHeight;
  return d;
}
// Streaming send: renders tokens as they arrive, optionally speaks the reply.
async function sendMessage(text, { speak = false } = {}) {
  bubble("user", text);
  history.push({ role: "user", content: text });
  const out = bubble("bot", "");
  let full = "";
  try {
    const model = $("#modelSel").value;
    const headers = { "Content-Type": "application/json" };
    if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
    const r = await fetch("/api/chat/stream", {
      method: "POST", headers,
      body: JSON.stringify({ model, messages: history }),
    });
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const obj = JSON.parse(line.slice(5).trim());
        if (obj.t) { full += obj.t; out.textContent = full; $("#chat").scrollTop = $("#chat").scrollHeight; }
        if (obj.served_by) out.title = "served by " + obj.served_by;
      }
    }
  } catch (e) { out.textContent = "error: " + e; }
  history.push({ role: "assistant", content: full });
  if (speak && full) speakText(full);
  return full;
}

$("#chatForm").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("#chatInput").value.trim();
  if (!text) return;
  $("#chatInput").value = "";
  await sendMessage(text, { speak: $("#speakToggle").checked });
};

// ---- text-to-speech ----
function speakText(text) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.05;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

// ---- Live conversation mode: continuous listen -> stream -> speak ----
let liveOn = false, liveRec = null;
function setLive(on) {
  liveOn = on;
  $("#liveBtn").classList.toggle("rec", on);
  $("#liveBtn").textContent = on ? "⏹️ Stop" : "🎙️ Go Live";
  $("#liveState").textContent = on ? "listening…" : "tap to start a hands-free conversation";
  if (on) startLive(); else if (liveRec) liveRec.stop();
}
function startLive() {
  if (!SR) { alert("Speech recognition not supported here."); setLive(false); return; }
  liveRec = new SR();
  liveRec.lang = "";
  liveRec.continuous = false;
  liveRec.interimResults = false;
  liveRec.onresult = async (e) => {
    const text = e.results[0][0].transcript.trim();
    if (!text) return;
    $("#liveState").textContent = "thinking…";
    liveRec.stop();
    await sendMessage(text, { speak: true });
  };
  liveRec.onend = () => {
    // Resume listening after the assistant finishes speaking.
    if (!liveOn) return;
    const wait = () => {
      if (window.speechSynthesis && window.speechSynthesis.speaking) return setTimeout(wait, 300);
      $("#liveState").textContent = "listening…";
      try { liveRec.start(); } catch (e) {}
    };
    wait();
  };
  liveRec.onerror = () => {};
  try { liveRec.start(); } catch (e) {}
}
$("#liveBtn").onclick = () => setLive(!liveOn);

// ---- pull a model ----
$("#pullForm").onsubmit = async (e) => {
  e.preventDefault();
  const model = $("#pullInput").value.trim(); if (!model) return;
  $("#pullOut").textContent = "Starting pull…";
  const headers = { "Content-Type": "application/json" };
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  const r = await fetch("/api/models/pull", { method: "POST", headers, body: JSON.stringify({ model }) });
  const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
  while (true) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n"); buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const o = JSON.parse(line.slice(5).trim());
      if (o.done) { $("#pullOut").textContent = "✓ done"; boot(); }
      else if (o.total) $("#pullOut").textContent = `${o.status} ${Math.round(100 * (o.completed || 0) / o.total)}%`;
      else if (o.status) $("#pullOut").textContent = o.status;
    }
  }
};

// ---- panic / duress ----
$("#panic").onclick = async () => {
  if (!confirm("Trigger DURESS alert to your trusted contacts?")) return;
  const r = await api("/api/safety/duress", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: "manual panic", location: curLoc }),
  });
  alert(`Duress active. ${r.alerts.length} contact(s) queued.`);
  refreshSafety();
};

// ---- awareness ----
async function refreshSensors() {
  const s = await api("/api/sensors");
  const box = $("#sensors");
  const srcs = Object.entries(s.sources || {});
  if (!srcs.length) { box.innerHTML = '<p class="muted">No sensor nodes reporting yet. Flash the ESP32 firmware and point it at this node.</p>'; return; }
  box.innerHTML = "";
  for (const [id, d] of srcs) {
    const el = document.createElement("div");
    el.className = "card";
    const obs = (d.observations || []).map((o) => `• ${o}`).join("<br>") || '<span class="muted">nominal</span>';
    el.innerHTML = `<b>${id}</b> <span class="muted">${d.age_s}s ago</span><br>
      Devices nearby: <b>${d.device_count}</b>${d.closest ? ` (closest: ${d.closest})` : ""}<br>
      ${d.mag_uT != null ? `Mag field: ${d.mag_uT} µT<br>` : ""}
      ${d.sound_db != null ? `Sound: ${d.sound_db} dB<br>` : ""}
      ${obs}`;
    box.appendChild(el);
  }
}

// ---- safety ----
async function refreshSafety() {
  const s = await api("/api/safety/status");
  renderDeadman(s.deadman || []);
  renderSurveillance(s.surveillance);
  refreshPosture();
  const du = s.duress;
  $("#duressState").className = "card" + (du.active ? " alert" : "");
  $("#duressState").innerHTML = du.active
    ? `<span class="badge">DURESS ACTIVE</span> — ${du.events} event(s). <button onclick="clearDuress()">Stand down</button>`
    : `<span style="color:var(--ok)">All clear.</span> ${du.events} past event(s).`;
  const t = $("#trackers");
  const sus = s.tracker_suspects || [];
  if (!sus.length) { t.innerHTML = '<p class="muted">No suspicious trackers detected.</p>'; }
  else {
    t.innerHTML = "";
    sus.forEach((x) => {
      const el = document.createElement("div");
      el.className = "card alert";
      el.innerHTML = `<b>${x.name || x.mac}</b><br><span class="muted">${x.mac}</span><br>
        Seen in <b>${x.distinct_locations}</b> places over ${x.span_minutes} min (${x.sightings}×).<br>
        <span class="muted">${x.advice}</span>`;
      t.appendChild(el);
    });
  }
}
window.clearDuress = async () => { await api("/api/safety/clear", { method: "POST" }); refreshSafety(); };

// dead-man's switch
function renderDeadman(list) {
  const el = $("#dmList");
  if (!list.length) { el.innerHTML = "No active check-ins."; return; }
  el.innerHTML = list.map((c) => {
    const mins = Math.max(0, Math.round(c.due_in_s / 60));
    const state = c.overdue ? '<span class="badge">OVERDUE</span>' : `due in ~${mins}m`;
    return `<div>• <b>${c.label}</b> — ${state}${c.recurring ? " (repeats)" : ""}
      <button onclick="checkin('${c.label}')">Check in</button>
      <button onclick="cancelDm('${c.label}')">Cancel</button></div>`;
  }).join("");
}
window.checkin = async (l) => { await api("/api/safety/deadman/checkin", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: l }) }); refreshSafety(); };
window.cancelDm = async (l) => { await api("/api/safety/deadman/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ label: l }) }); refreshSafety(); };
$("#dmForm").onsubmit = async (e) => {
  e.preventDefault();
  const label = $("#dmLabel").value.trim() || "check-in";
  await api("/api/safety/deadman/arm", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, minutes: parseFloat($("#dmMins").value) || 30, recurring: $("#dmRecur").checked }),
  });
  $("#dmLabel").value = "";
  refreshSafety();
};

// surveillance scan
function renderSurveillance(rep) {
  const el = $("#surv");
  if (!rep || rep.clear) { el.innerHTML = '<p class="muted">Clear — no evil-twin APs or flagged devices.</p>'; return; }
  let html = "";
  (rep.evil_twin_candidates || []).forEach((t) => {
    html += `<div class="card alert"><b>Possible evil-twin: ${t.ssid}</b><br>
      <span class="muted">${t.bssid_count} radios advertise this name. ${t.risk}</span></div>`;
  });
  (rep.flagged_devices || []).forEach((d) => {
    html += `<div class="card alert"><b>${d.vendor_guess}</b> <span class="muted">${d.mac}</span><br>
      <span class="muted">${d.note}</span></div>`;
  });
  el.innerHTML = html;
}

// breach check
$("#brForm").onsubmit = async (e) => {
  e.preventDefault();
  const pw = $("#brInput").value; if (!pw) return;
  $("#brOut").textContent = "Checking (only a hash prefix is sent)…";
  const r = await api("/api/safety/breach", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: pw }),
  });
  $("#brInput").value = "";
  $("#brOut").textContent = r.ok ? (r.pwned ? `⚠ Found in breaches ${r.times_seen}× — ${r.advice}` : `✓ ${r.advice}`) : (r.error || "");
};

// security posture
async function refreshPosture() {
  const s = await api("/api/security/status");
  $("#secPosture").innerHTML =
    `Auth required: <b>${s.require_auth}</b> · TLS: <b>${s.tls_enabled}</b> · Mesh signing: <b>${s.mesh_signing}</b><br>
     Audit log: <b>${s.audit.intact ? "intact" : "TAMPERED"}</b> (${s.audit.entries} entries) · Vault: <b>${s.vault_unlocked ? "unlocked" : "locked"}</b>`;
}

$("#expForm").onsubmit = async (e) => {
  e.preventDefault();
  const v = $("#expInput").value.trim(); if (!v) return;
  $("#expOut").textContent = "Building your exposure-reduction plan…";
  const r = await api("/api/safety/exposure", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ identifiers: [v], plan: true }),
  });
  $("#expOut").textContent = r.action_plan || JSON.stringify(r, null, 2);
};

// ---- tools ----
$("#wxBtn").onclick = async () => {
  const q = curLoc ? `?lat=${curLoc.lat}&lon=${curLoc.lon}` : "";
  const w = await api("/api/weather" + q);
  $("#wx").innerHTML = w.ok
    ? `${w.condition}, ${w.temp_c}°C (feels ${w.feels_c}°). High ${w.high_c}/Low ${w.low_c}. Rain ${w.precip_prob_max}%.<br>${w.advisory.map((a) => "• " + a).join("<br>")}`
    : (w.error || "unavailable");
};
$("#trForm").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("#trInput").value.trim(); if (!text) return;
  $("#trOut").textContent = "…";
  const r = await api("/api/translate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  $("#trOut").textContent = r.english || r.error || "";
};
$("#agForm").onsubmit = async (e) => {
  e.preventDefault();
  const command = $("#agInput").value.trim(); if (!command) return;
  const r = await api("/api/agent/run", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, confirm: $("#agConfirm").checked }),
  });
  $("#agOut").textContent = r.ok ? (r.stdout || "(ok, no output)") : ("✗ " + (r.error || r.stderr));
};

// ---- voice input (Web Speech API) ----
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
function listen(btn, targetInput, opts = {}) {
  if (!SR) { alert("Speech recognition not supported in this browser."); return; }
  const rec = new SR();
  rec.lang = opts.lang || "";           // "" lets the browser auto-detect
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  btn.classList.add("rec");
  rec.onresult = (e) => {
    targetInput.value = e.results[0][0].transcript;
    if (opts.autosubmit && targetInput.form) targetInput.form.requestSubmit();
  };
  rec.onerror = () => {};
  rec.onend = () => btn.classList.remove("rec");
  rec.start();
}
if (SR) {
  $("#chatMic").onclick = () => listen($("#chatMic"), $("#chatInput"), { autosubmit: true });
  $("#trMic").onclick = () => listen($("#trMic"), $("#trInput"), { autosubmit: true });
} else {
  document.querySelectorAll(".mic").forEach((m) => (m.style.display = "none"));
}

// ---- vision: phone / glasses / external cameras ----
let camStream = null, camDevices = [], camIndex = 0;
async function listCamDevices() {
  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    camDevices = devs.filter((d) => d.kind === "videoinput");
    const sel = $("#camSel");
    sel.innerHTML = "";
    camDevices.forEach((d, i) => {
      const o = document.createElement("option");
      o.value = d.deviceId; o.textContent = d.label || `Camera ${i + 1}`;
      sel.appendChild(o);
    });
  } catch (e) {}
}
async function startCam(deviceId) {
  if (camStream) camStream.getTracks().forEach((t) => t.stop());
  const constraints = { video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "environment" }, audio: false };
  try {
    camStream = await navigator.mediaDevices.getUserMedia(constraints);
    $("#cam").srcObject = camStream;
    await listCamDevices();   // labels populate after permission granted
  } catch (e) { $("#visOut").textContent = "camera error: " + e; }
}
function grabFrameB64() {
  const v = $("#cam");
  if (!v.videoWidth) return null;
  const cv = document.createElement("canvas");
  cv.width = v.videoWidth; cv.height = v.videoHeight;
  cv.getContext("2d").drawImage(v, 0, 0);
  return cv.toDataURL("image/jpeg", 0.8).split(",")[1];   // strip data: prefix
}
$("#camStart").onclick = () => startCam($("#camSel").value);
$("#camSel").onchange = () => startCam($("#camSel").value);
$("#camFlip").onclick = () => {
  if (!camDevices.length) return;
  camIndex = (camIndex + 1) % camDevices.length;
  $("#camSel").value = camDevices[camIndex].deviceId;
  startCam(camDevices[camIndex].deviceId);
};
$("#visForm").onsubmit = async (e) => {
  e.preventDefault();
  const image_b64 = grabFrameB64();
  if (!image_b64) { $("#visOut").textContent = "Start the camera first."; return; }
  $("#visOut").textContent = "Looking…";
  const r = await api("/api/vision", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_b64, prompt: $("#visPrompt").value.trim() }),
  });
  $("#visOut").textContent = r.ok ? r.analysis : (r.error || "vision unavailable");
  if (r.ok && $("#speakToggle").checked) speakText(r.analysis);
};

// external cameras
async function refreshExtCams() {
  const r = await api("/api/cameras");
  const el = $("#extCams");
  if (!r.cameras || !r.cameras.length) { el.innerHTML = "No external cameras."; return; }
  el.innerHTML = r.cameras.map((c) =>
    `<div>• <b>${c.name}</b> <span class="muted">(${c.kind})</span>
      <button onclick="analyzeCam('${c.name}')">Look</button>
      <button onclick="delCam('${c.name}')">✕</button></div>
      <div id="ec-${c.name}" class="muted"></div>`).join("");
}
window.analyzeCam = async (name) => {
  $("#ec-" + name).textContent = "Looking…";
  const r = await api(`/api/cameras/${encodeURIComponent(name)}/analyze`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
  });
  $("#ec-" + name).textContent = r.ok ? r.analysis : (r.error || "failed");
};
window.delCam = async (name) => { await api(`/api/cameras/${encodeURIComponent(name)}`, { method: "DELETE" }); refreshExtCams(); };
$("#extCamForm").onsubmit = async (e) => {
  e.preventDefault();
  await api("/api/cameras", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: $("#ecName").value.trim(), url: $("#ecUrl").value.trim(), kind: $("#ecKind").value }),
  });
  $("#ecName").value = ""; $("#ecUrl").value = "";
  refreshExtCams();
};

// ---- Web Push (lock-screen alerts) ----
function urlB64ToUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64); return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}
async function enablePush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) { $("#pushOut").textContent = "Push not supported here."; return; }
  const key = await api("/api/push/publickey");
  if (!key.enabled) { $("#pushOut").textContent = "Push not configured on the node (see docs)."; return; }
  const reg = await navigator.serviceWorker.register("/sw.js");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") { $("#pushOut").textContent = "Notification permission denied."; return; }
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8(key.public_key) });
  const r = await api("/api/push/subscribe", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription: sub }),
  });
  $("#pushOut").textContent = r.ok ? "✓ Lock-screen alerts enabled." : (r.error || "failed");
}
$("#pushBtn").onclick = enablePush;
$("#pushTest").onclick = async () => { const r = await api("/api/push/test", { method: "POST" }); $("#pushOut").textContent = `Sent to ${r.subscriptions} device(s).`; };

// ---- live event bus ----
try {
  const wsUrl = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws" + (TOKEN ? "?token=" + encodeURIComponent(TOKEN) : "");
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "safety.duress") { bubble("sys", "⚠ duress event on mesh"); refreshSafety(); }
    if (e.type === "safety.surveillance") { bubble("sys", "⚠ surveillance risk detected"); if ($("#safety").classList.contains("active")) refreshSafety(); }
    if (e.type === "safety.geofence") { bubble("sys", "⚠ geofence: " + (e.alerts || []).join(", ")); }
    if (e.type === "sensors.update") { if ($("#aware").classList.contains("active")) refreshSensors(); }
  };
} catch (e) {}

boot();
