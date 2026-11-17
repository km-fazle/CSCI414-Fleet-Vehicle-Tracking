const FRESH = "#1f8a3b";
const STALE = "#ee0000";
const TRACK = "#1a73e8";

const rosterEl = document.getElementById("roster");
const inspectorEl = document.getElementById("inspector");
const statusEl = document.getElementById("status");
const compareEl = document.getElementById("compare");
const alertsEl = document.getElementById("alerts");
const tapeEl = document.getElementById("tape");
const tapeNote = document.getElementById("tape-note");
const shell = document.getElementById("shell");
const filterEl = document.getElementById("filter");
const replayEl = document.getElementById("replay");

let current = null;
let selectedId = null;
let dismissed = false;
let fitted = false;
let pulling = false;
let view = "live";
let query = "";

const map = L.map("map", { zoomControl: true, attributionControl: true }).setView([40.73, -73.99], 12);
const tileCredit = "&copy; Esri, HERE, Garmin, OpenStreetMap contributors";
const streets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
  attribution: tileCredit,
  maxZoom: 18,
  maxNativeZoom: 18,
});
const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  attribution: tileCredit,
  maxZoom: 18,
  maxNativeZoom: 18,
});
streets.addTo(map);
map.attributionControl.setPosition("bottomleft");

const lines = new Map();
const marks = new Map();

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  if (attrs) {
    Object.entries(attrs).forEach(([key, value]) => {
      if (value == null) return;
      if (key === "class") node.className = value;
      else node.setAttribute(key, value);
    });
  }
  if (text != null) node.textContent = text;
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function ms(value) {
  if (!finite(value)) return "—";
  const digits = value >= 100 ? 1 : value >= 10 ? 2 : 3;
  return `${Number(value.toFixed(digits))} ms`;
}

function seconds(value) {
  if (!finite(value)) return "—";
  return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} s`;
}

function ageLabel(value) {
  if (!finite(value)) return "No fix";
  const magnitude = Math.abs(value);
  if (magnitude < 1000) return `${Math.round(value)} ms`;
  if (magnitude < 60000) return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} s`;
  const minutes = Math.round(magnitude / 60000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} m`;
}

function rate(value) {
  if (!finite(value)) return "—";
  return value >= 100 ? `${value.toFixed(0)} /s` : `${value.toFixed(2)} /s`;
}

function clock(iso) {
  const match = typeof iso === "string" && iso.match(/T(\d{2}:\d{2}:\d{2}\.\d{3})/);
  return match ? match[1] : "—";
}

function lagOf(point) {
  const sent = Date.parse(point.event_time);
  const received = Date.parse(point.received_at);
  if (!Number.isFinite(sent) || !Number.isFinite(received)) return null;
  return received - sent;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function labelFor(board, id) {
  const vehicle = (board.vehicles || []).find((item) => item.vehicle_id === id);
  return vehicle ? vehicle.label || id : id;
}

function bars(kind) {
  const node = el("span", { class: `bars ${kind}`, "aria-hidden": "true" });
  for (let i = 0; i < 4; i += 1) node.append(el("i"));
  return node;
}

function applyChrome() {
  shell.dataset.view = view;
  replayEl.hidden = view !== "replay";
  compareEl.hidden = view !== "reports";
  alertsEl.hidden = view !== "alerts";
  inspectorEl.hidden = true;
  document.querySelectorAll(".nav button").forEach((button) => {
    button.classList.toggle("on", button.dataset.view === view);
  });
}

function setView(next) {
  view = next;
  applyChrome();
  requestAnimationFrame(() => map.invalidateSize());
}

function renderStatus(board) {
  clear(statusEl);
  const api = board.api || {};
  const live = el("span");
  live.append(el("i", { class: api.live ? "lamp on" : "lamp off" }));
  live.append(document.createTextNode(api.live ? "API live" : "API down"));
  const ready = el("span");
  ready.append(el("i", { class: api.ready ? "lamp on" : "lamp off" }));
  ready.append(document.createTextNode(api.ready ? "Mongo ready" : "Mongo down"));
  statusEl.append(live, ready);
  const probe = el("span", { title: "Vehicle-list request from the client namespace, on a warm TLS connection" });
  probe.textContent = finite(api.warm_ms) ? `Read ${ms(api.warm_ms)}` : "";
  if (probe.textContent) statusEl.append(probe);
}

function matches(vehicle) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return `${vehicle.label || ""} ${vehicle.vehicle_id}`.toLowerCase().includes(needle);
}

function renderRoster(board) {
  clear(rosterEl);
  const vehicles = (board.vehicles || []).filter(matches);
  if (!vehicles.length) {
    const reason = board.api && board.api.error ? board.api.error : "No vehicles match.";
    rosterEl.append(el("p", { class: "empty" }, reason));
    return;
  }
  vehicles.forEach((vehicle) => {
    const last = vehicle.last_known;
    const stale = Boolean(last && last.stale);
    const kind = !last ? "empty" : stale ? "stale" : "fresh";
    const button = el("button", {
      class: "vehicle",
      type: "button",
      "aria-pressed": vehicle.vehicle_id === selectedId ? "true" : "false",
    });
    button.append(el("span", { class: "v-label" }, vehicle.label || vehicle.vehicle_id));
    button.append(bars(kind));
    const state = !last ? "No fix" : stale ? `Stale · ${ageLabel(last.age_ms)}` : `Fresh · ${ageLabel(last.age_ms)}`;
    button.append(el("span", { class: `v-sub ${kind}` }, state));
    const where = last && finite(last.lat) ? `${last.lat.toFixed(5)}, ${last.lon.toFixed(5)}` : "No stored position";
    button.append(el("span", { class: "v-where" }, where));
    button.addEventListener("click", () => choose(vehicle.vehicle_id, true, true));
    rosterEl.append(button);
  });
}

function renderInspector() {
  inspectorEl.hidden = true;
}

function metricRow(name, baseline, delay) {
  const row = el("tr");
  row.append(el("th", { scope: "row" }, name));
  row.append(el("td", { class: "num" }, baseline));
  row.append(el("td", { class: "num" }, delay));
  return row;
}

function renderCompare(board) {
  clear(compareEl);
  const experiment = board.experiment || {};
  compareEl.append(el("h2", null, "Reports"));
  if (!experiment.available) {
    compareEl.append(el("p", { class: "caption" }, "No completed baseline and delay run is stored yet."));
    return;
  }
  const hash = (experiment.workload_sha256 || "").slice(0, 12);
  const match = experiment.same_coordinates ? `Same coordinates · ${hash}` : "Coordinate hashes differ";
  compareEl.append(el("p", { class: "caption" }, `Run ${experiment.stamp}. Impairment: ${experiment.impairment}. ${match}.`));
  const table = el("table");
  const head = el("tr");
  ["Measure", "Baseline", "Delayed"].forEach((label, index) => {
    head.append(el("th", { class: index ? "num" : "", scope: "col" }, label));
  });
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  const base = experiment.baseline || {};
  const delay = experiment.delay || {};
  const posts = (side) => (side.logical_posts == null ? "—" : `${side.post_successes} / ${side.logical_posts}`);
  [
    ["HTTP latency, median", ms(base.http_p50), ms(delay.http_p50)],
    ["Delivery lag, median", ms(base.lag_p50), ms(delay.lag_p50)],
    ["Location age, median", ms(base.age_p50), ms(delay.age_p50)],
    ["Ping average", ms(base.ping_avg), ms(delay.ping_avg)],
    ["Posts", posts(base), posts(delay)],
    ["Rate", rate(base.events_per_second), rate(delay.events_per_second)],
  ].forEach(([name, left, right]) => tbody.append(metricRow(name, left, right)));
  table.append(thead, tbody);
  compareEl.append(table);

  const recovery = el("div", { class: "recovery" });
  const record = experiment.recovery;
  if (!record) {
    recovery.append(el("p", null, "No recovery record for this run."));
  } else {
    recovery.append(el("p", null, `Down at ${clock(record.detected_down_at)} UTC (${record.error || "error"}).`));
    recovery.append(el("p", null, `Ready ${seconds(record.restart_to_ready_ms)} after restart. Detection to the next stored event was ${seconds(record.recovery_duration_ms)}, including the rest of the ${record.hold_seconds} s hold.`));
    recovery.append(el("p", null, record.retry_ok
      ? "The event sent during the outage was stored only when the client retried it."
      : "The retry after restore did not succeed."));
  }
  compareEl.append(recovery);
}

function card(title, body, ok) {
  const node = el("article", { class: ok ? "card ok" : "card bad" });
  node.append(el("h3", null, title));
  node.append(el("p", null, body));
  return node;
}

function renderAlerts(board) {
  clear(alertsEl);
  alertsEl.append(el("h2", null, "Alerts"));
  const api = board.api || {};
  const network = board.network || {};
  const freshCount = (board.vehicles || []).filter((vehicle) => vehicle.last_known && !vehicle.last_known.stale).length;
  const total = (board.vehicles || []).length;
  const staleCount = (board.vehicles || []).filter((vehicle) => vehicle.last_known && vehicle.last_known.stale).length;
  const grid = el("div", { class: "alert-grid" });
  grid.append(card("API", api.live ? "Live on 10.20.20.10:8443" : (api.error || "Not answering"), api.live));
  grid.append(card("MongoDB", api.ready ? "Ready on 10.30.30.10:27017" : "Not ready", api.ready));
  grid.append(card("Freshness", `${freshCount} of ${total} inside ${ageLabel(board.freshness_threshold_ms)}. ${staleCount} stale.`, freshCount > 0));
  const firewall = network.firewall || {};
  grid.append(card(
    "Firewall",
    `Accepted to API ${firewall.api_accept == null ? "—" : firewall.api_accept}. Dropped toward MongoDB ${firewall.client_data_drop == null ? "—" : firewall.client_data_drop}.`,
    firewall.client_data_drop != null,
  ));
  alertsEl.append(grid);
  const path = el("ol", { class: "path" });
  (network.zones || []).forEach((zone) => {
    const item = el("li", { class: zone.up ? "up" : "down" });
    item.append(el("span", { class: "role" }, zone.name));
    item.append(el("span", { class: "addr" }, `${zone.address} · ${zone.note}`));
    path.append(item);
  });
  alertsEl.append(path);
  const facts = el("p", { class: "caption" }, `Client link ${network.client_qdisc || "absent"}. Router link ${network.router_qdisc || "absent"}.`);
  facts.style.padding = "8px 16px";
  alertsEl.append(facts);
  if (network.firewall_error) alertsEl.append(el("p", { class: "caption" }, network.firewall_error));
}

function recentEvents(board) {
  const rows = [];
  Object.entries(board.tracks || {}).forEach(([id, points]) => {
    (points || []).forEach((point) => rows.push({ ...point, vehicle_id: point.vehicle_id || id }));
  });
  rows.sort((a, b) => String(b.event_time).localeCompare(String(a.event_time)) || (b.sequence || 0) - (a.sequence || 0));
  return rows.slice(0, 40);
}

function renderTape(board) {
  clear(tapeEl);
  const rows = recentEvents(board);
  const freshCount = (board.vehicles || []).filter((vehicle) => vehicle.last_known && !vehicle.last_known.stale).length;
  const total = (board.vehicles || []).length;
  tapeNote.textContent = total
    ? `${freshCount} of ${total} vehicles are inside the ${ageLabel(board.freshness_threshold_ms)} window.`
    : "Newest stored positions.";
  if (!rows.length) {
    const tr = el("tr");
    tr.append(el("td", { colspan: "7" }, "No events stored yet."));
    tapeEl.append(tr);
    return;
  }
  rows.forEach((point) => {
    const tr = el("tr", { class: point.vehicle_id === selectedId ? "on" : "" });
    tr.append(el("td", null, clock(point.event_time)));
    tr.append(el("td", null, labelFor(board, point.vehicle_id)));
    tr.append(el("td", { class: "num" }, point.sequence == null ? "—" : String(point.sequence)));
    tr.append(el("td", { class: "num" }, finite(point.lat) ? point.lat.toFixed(5) : "—"));
    tr.append(el("td", { class: "num" }, finite(point.lon) ? point.lon.toFixed(5) : "—"));
    tr.append(el("td", { class: "num" }, ms(lagOf(point))));
    tr.append(el("td", null, point.source_type || "—"));
    tr.addEventListener("click", () => choose(point.vehicle_id, true, true));
    tapeEl.append(tr);
  });
}

function cardHtml(vehicle) {
  const last = vehicle.last_known;
  const name = esc(vehicle.label || vehicle.vehicle_id);
  const ident = esc(vehicle.vehicle_id);
  if (!last || !finite(last.lat)) {
    return `<div class="vcard"><h3>${name}</h3><p class="vcard-id">${ident}</p><p>No stored position</p></div>`;
  }
  const state = last.stale ? "Stale" : "Fresh";
  const source = last.source_type === "nyc_tlc_derived" ? "Derived from NYC TLC trip data" : "Synthetic track, not a GPS receiver";
  return `<div class="vcard">
    <h3>${name}</h3>
    <p class="vcard-id">${ident}</p>
    <p class="vcard-state ${state.toLowerCase()}">${state} · ${esc(ageLabel(last.age_ms))}</p>
    <p class="vcard-where">${last.lat.toFixed(5)}, ${last.lon.toFixed(5)}</p>
    <dl>
      <dt>Sequence</dt><dd>${esc(last.sequence)}</dd>
      <dt>Event</dt><dd>${esc(clock(last.event_time))}</dd>
      <dt>Lag</dt><dd>${esc(ms(lagOf(last)))}</dd>
    </dl>
    <p class="vcard-note">${esc(source)}</p>
  </div>`;
}

function showPopup(id) {
  const marker = marks.get(id);
  const vehicle = (current.vehicles || []).find((item) => item.vehicle_id === id);
  if (!marker || !vehicle) return;
  const html = cardHtml(vehicle);
  const options = {
    className: "vehicle-card",
    closeButton: true,
    autoPan: true,
    keepInView: true,
    offset: [0, -14],
    maxWidth: 260,
    minWidth: 220,
    autoPanPaddingTopLeft: [48, 16],
    autoPanPaddingBottomRight: [16, 28],
  };
  if (!marker.getPopup()) marker.bindPopup(html, options);
  else marker.setPopupContent(html);
  marker.openPopup();
}

function icon(color, selected) {
  const size = selected ? 22 : 16;
  return L.divIcon({
    className: "ft-icon",
    html: `<i class="mark${selected ? " on" : ""}" style="background:${color}"></i>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function syncMap(board, pan) {
  const seen = new Set();
  const bounds = [];
  (board.vehicles || []).forEach((vehicle, index) => {
    const id = vehicle.vehicle_id;
    const points = (board.tracks && board.tracks[id]) || [];
    const coords = points
      .filter((point) => finite(point.lat) && finite(point.lon))
      .map((point) => [point.lat, point.lon]);
    if (!coords.length && vehicle.last_known && finite(vehicle.last_known.lat)) {
      coords.push([vehicle.last_known.lat, vehicle.last_known.lon]);
    }
    if (!coords.length) {
      if (lines.has(id)) {
        lines.get(id).remove();
        lines.delete(id);
      }
      if (marks.has(id)) {
        marks.get(id).remove();
        marks.delete(id);
      }
      return;
    }
    seen.add(id);
    const selected = id === selectedId;
    const markerColor = !vehicle.last_known ? "#8a8a8a" : vehicle.last_known.stale ? STALE : FRESH;
    if (!lines.has(id)) lines.set(id, L.polyline(coords, { color: TRACK, weight: 3, opacity: 0.85 }).addTo(map));
    const line = lines.get(id);
    line.setLatLngs(coords);
    line.setStyle({ weight: selected ? 5 : 3, opacity: selected ? 1 : 0.7 });
    const last = coords[coords.length - 1];
    if (!marks.has(id)) {
      const marker = L.marker(last, { icon: icon(markerColor, selected), zIndexOffset: selected ? 500 : index });
      marker.on("click", () => {
        if (view === "reports" || view === "alerts") setView("live");
        choose(id, false, true);
      });
      marker.addTo(map);
      marks.set(id, marker);
    }
    const marker = marks.get(id);
    marker.setLatLng(last);
    const iconKey = `${markerColor}:${selected ? 1 : 0}`;
    if (marker._ftIcon !== iconKey) {
      marker.setIcon(icon(markerColor, selected));
      marker._ftIcon = iconKey;
    }
    marker.setZIndexOffset(selected ? 800 : index);
    if (marker.getPopup()) marker.setPopupContent(cardHtml(vehicle));
    if (marker.isPopupOpen()) marker.openPopup();
    coords.forEach((pair) => bounds.push(pair));
    if (pan && selected) {
      const motion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const zoom = Math.max(map.getZoom(), 16);
      if (motion) map.setView(last, zoom);
      else map.flyTo(last, zoom, { duration: 0.35 });
    }
  });
  Array.from(lines.keys()).forEach((id) => {
    if (seen.has(id)) return;
    lines.get(id).remove();
    lines.delete(id);
    if (marks.has(id)) {
      marks.get(id).remove();
      marks.delete(id);
    }
  });
  if (!fitted && bounds.length) {
    map.fitBounds(bounds, { padding: [48, 48], maxZoom: 14 });
    fitted = true;
  }
}

function choose(id, pan, popup) {
  dismissed = false;
  selectedId = id;
  if (view === "reports" || view === "alerts") view = "live";
  if (!current) return;
  applyChrome();
  renderRoster(current);
  renderInspector(current);
  renderTape(current);
  syncMap(current, pan);
  if (popup) showPopup(id);
}

function render(board) {
  current = board;
  const vehicles = board.vehicles || [];
  const known = vehicles.some((vehicle) => vehicle.vehicle_id === selectedId);
  if (!known && !dismissed) {
    const first = vehicles.find((vehicle) => vehicle.last_known && finite(vehicle.last_known.lat));
    selectedId = first ? first.vehicle_id : null;
  }
  if (!known && dismissed) selectedId = null;
  applyChrome();
  renderStatus(board);
  renderRoster(board);
  renderInspector(board);
  renderCompare(board);
  renderAlerts(board);
  renderTape(board);
  syncMap(board, false);
  if (!render.sized) {
    requestAnimationFrame(() => map.invalidateSize());
    render.sized = true;
  }
}

function showBasemap(kind) {
  const streetButton = document.getElementById("basemap-map");
  const satButton = document.getElementById("basemap-sat");
  if (kind === "sat") {
    if (map.hasLayer(streets)) map.removeLayer(streets);
    satellite.addTo(map);
  } else {
    if (map.hasLayer(satellite)) map.removeLayer(satellite);
    streets.addTo(map);
  }
  streetButton.classList.toggle("on", kind !== "sat");
  satButton.classList.toggle("on", kind === "sat");
}

document.querySelectorAll(".nav button").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});
filterEl.addEventListener("input", () => {
  query = filterEl.value;
  if (current) renderRoster(current);
});
document.getElementById("basemap-map").addEventListener("click", () => showBasemap("map"));
document.getElementById("basemap-sat").addEventListener("click", () => showBasemap("sat"));

async function refresh() {
  if (pulling) return;
  pulling = true;
  try {
    const response = await fetch("/api/board", { cache: "no-store" });
    if (!response.ok) throw new Error(`Board returned ${response.status}`);
    render(await response.json());
  } catch (error) {
    clear(statusEl);
    statusEl.append(el("span", null, error.message || "The board could not be read"));
  } finally {
    pulling = false;
  }
}

refresh();
window.setInterval(refresh, 2000);
window.addEventListener("resize", () => map.invalidateSize());
