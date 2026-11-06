/* HQ stage-3 front-end.
 *
 * Rules that make it feel instant:
 *  1. One WebSocket to the HQ backend, open the whole time.
 *  2. Optimistic UI: a tile flips the moment it's tapped, before HA confirms.
 *     If HA hasn't confirmed within 4s the tile reverts (and shows why).
 *  3. The latency panel measures tap -> HA-confirmed, so "feels instant" is a number.
 */

const $ = (s) => document.querySelector(s);
const lightsEl = $("#lights");
const climateEl = $("#climate");
const statusEl = $("#status");

const state = new Map();        // entity_id -> HA state object
const pending = new Map();      // entity_id -> { expect: 'on'|'off'|number, t0, timer }
const latencies = [];

let ws;
let haConnected = false;

// ---- clock -----------------------------------------------------------------
function tickClock() {
  const d = new Date();
  $("#clock").textContent = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}
setInterval(tickClock, 1000); tickClock();

// ---- websocket -------------------------------------------------------------
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => setStatus();
  ws.onclose = () => { haConnected = false; setStatus("backend offline"); setTimeout(connect, 1500); };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

function setStatus(text) {
  if (text) { statusEl.textContent = text; statusEl.className = "status off"; return; }
  statusEl.textContent = haConnected ? "connected" : "waiting for Home Assistant";
  statusEl.className = "status " + (haConnected ? "on" : "off");
}

function handle(msg) {
  switch (msg.type) {
    case "ha_connected":
      haConnected = msg.connected; setStatus(); break;
    case "states":
      state.clear();
      for (const s of msg.states) state.set(s.entity_id, s);
      renderAll(); break;
    case "state":
      state.set(msg.state.entity_id, msg.state);
      resolvePending(msg.state);
      renderOne(msg.state.entity_id); break;
    case "error":
      console.warn("HA error", msg.message);
      if (msg.ref) { const p = pending.get(msg.ref); if (p) { clearTimeout(p.timer); pending.delete(msg.ref); renderOne(msg.ref); } }
      break;
  }
}

// ---- optimistic updates + latency ------------------------------------------
function expect(entityId, expected) {
  const prev = pending.get(entityId);
  if (prev) clearTimeout(prev.timer);
  const p = { expect: expected, t0: performance.now() };
  p.timer = setTimeout(() => { pending.delete(entityId); renderOne(entityId); }, 4000);
  pending.set(entityId, p);
  renderOne(entityId);
}

function resolvePending(s) {
  const p = pending.get(s.entity_id);
  if (!p) return;
  const actual = s.entity_id.startsWith("climate.") ? s.attributes.temperature : s.state;
  if (actual === p.expect) {
    clearTimeout(p.timer);
    pending.delete(s.entity_id);
    recordLatency(performance.now() - p.t0);
  }
}

function recordLatency(ms) {
  latencies.push(ms);
  const avg = latencies.reduce((a, b) => a + b, 0) / latencies.length;
  $("#lat-last").textContent = Math.round(ms) + " ms";
  $("#lat-avg").textContent = Math.round(avg) + " ms";
  $("#lat-max").textContent = Math.round(Math.max(...latencies)) + " ms";
}

// ---- rendering -------------------------------------------------------------
function friendly(s) { return s.attributes.friendly_name || s.entity_id; }

function renderAll() {
  lightsEl.innerHTML = ""; climateEl.innerHTML = "";
  const ids = [...state.keys()].sort((a, b) => friendly(state.get(a)).localeCompare(friendly(state.get(b))));
  for (const id of ids) {
    if (id.startsWith("light.") || id.startsWith("switch.")) lightsEl.appendChild(lightTile(id));
    else if (id.startsWith("climate.")) climateEl.appendChild(climateCard(id));
  }
}

function renderOne(id) {
  const el = document.getElementById(id);
  if (!el) return;
  if (id.startsWith("climate.")) el.replaceWith(climateCard(id));
  else el.replaceWith(lightTile(id));
}

function lightTile(id) {
  const s = state.get(id);
  const p = pending.get(id);
  const on = p ? p.expect === "on" : s.state === "on";
  const el = document.createElement("div");
  el.id = id;
  el.className = "tile" + (on ? " on" : "") + (p ? " pending" : "") + (s.state === "unavailable" ? " unavailable" : "");
  el.innerHTML = `<div class="name">${friendly(s)}</div><div class="sub">${p ? "…" : s.state}</div>`;
  el.addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    if (s.state === "unavailable") return;
    const target = on ? "off" : "on";
    expect(id, target);
    send({ type: "call_service", domain: id.split(".")[0], service: "turn_" + target, data: { entity_id: id }, ref: id });
  });
  return el;
}

function climateCard(id) {
  const s = state.get(id);
  const p = pending.get(id);
  const target = p ? p.expect : s.attributes.temperature;
  const el = document.createElement("div");
  el.id = id; el.className = "climate";
  el.innerHTML = `
    <div class="name">${friendly(s)}</div>
    <div class="temps">now ${s.attributes.current_temperature ?? "–"}° · ${s.state}${s.attributes.hvac_action ? " · " + s.attributes.hvac_action : ""}</div>
    <div class="target${p ? " pending" : ""}">${target ?? "–"}°</div>
    <div class="btns"><button data-d="-0.5">−</button><button data-d="+0.5">+</button></div>`;
  for (const b of el.querySelectorAll("button")) {
    b.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      const next = Math.round(((target ?? 20) + parseFloat(b.dataset.d)) * 2) / 2;
      expect(id, next);
      send({ type: "call_service", domain: "climate", service: "set_temperature", data: { entity_id: id, temperature: next }, ref: id });
    });
  }
  return el;
}

connect();
