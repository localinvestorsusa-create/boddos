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
$("#chatForm").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("#chatInput").value.trim();
  if (!text) return;
  $("#chatInput").value = "";
  bubble("user", text);
  history.push({ role: "user", content: text });
  const thinking = bubble("bot", "…");
  try {
    const model = $("#modelSel").value;
    const r = await api("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, messages: history }),
    });
    thinking.textContent = r.reply || r.note || "(no reply)";
    if (r.served_by) thinking.title = "served by " + r.served_by;
    history.push({ role: "assistant", content: r.reply || "" });
  } catch (e) { thinking.textContent = "error: " + e; }
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
