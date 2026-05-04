/* =========================================================================
   RidePro – app.js
   Logic phía client: bản đồ, autocomplete, click chọn, đặt xe,
   gọi API tính giá real-time, hiển thị breakdown giá.
   ========================================================================= */

(function () {
'use strict';

const cfg = window.RIDEPRO_CONFIG || { mapCenter: [10.7717, 106.6669], ring1: null };

/* ====================== STATE ====================== */
const state = {
  pickup:       null,
  dest:         null,
  stop:         null,
  hasStopInput: false,
  vehicle:      'bike',
  tip:          0,
  insurance:    0,
  payment:      'cash',
  promo:        '',
  distanceKm:   0,
  routeSrc:     null,
  fare:         null,
  conditions:   null,
};

/* ====================== HELPERS ====================== */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const fmtMoney = (n) =>
  (Math.round(Number(n) || 0)).toLocaleString('vi-VN').replace(/,/g, '.') + 'đ';

function showToast(msg, type = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.className = 'toast'; }, 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return res.json();
}

/* ====================== MAP ====================== */
const map = L.map('map', { zoomControl: true }).setView(cfg.mapCenter, 14);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap',
  maxZoom: 19,
}).addTo(map);

if (cfg.ring1) {
  const r = cfg.ring1;
  L.rectangle(
    [[r.lat_min, r.lng_min], [r.lat_max, r.lng_max]],
    { color: '#00B14F', weight: 1.5, dashArray: '6 6', fillOpacity: 0.04 }
  ).addTo(map);
}

function makeMarker(latlng, role) {
  const html = `<div class="cm-pin ${role}"><i class="fa-solid fa-${
    role === 'start' ? 'circle-dot' : role === 'end' ? 'flag-checkered' : 'pause'
  }"></i></div>`;
  const icon = L.divIcon({ html, className: 'custom-marker', iconSize: [32, 32], iconAnchor: [6, 26] });
  return L.marker(latlng, { icon });
}

let pickupMarker = null, destMarker = null, stopMarker = null, routeLine = null;

function refreshMarkers() {
  if (pickupMarker) { map.removeLayer(pickupMarker); pickupMarker = null; }
  if (destMarker)   { map.removeLayer(destMarker);   destMarker   = null; }
  if (stopMarker)   { map.removeLayer(stopMarker);   stopMarker   = null; }
  if (state.pickup) pickupMarker = makeMarker([state.pickup.lat, state.pickup.lng], 'start').bindPopup('<b>Điểm đón</b><br>' + state.pickup.addr).addTo(map);
  if (state.dest)   destMarker   = makeMarker([state.dest.lat,   state.dest.lng],   'end').bindPopup('<b>Điểm đến</b><br>' + state.dest.addr).addTo(map);
  if (state.stop)   stopMarker   = makeMarker([state.stop.lat,   state.stop.lng],   'stop').bindPopup('<b>Điểm dừng</b><br>' + state.stop.addr).addTo(map);
}

function fitToMarkers() {
  const pts = [];
  if (state.pickup) pts.push([state.pickup.lat, state.pickup.lng]);
  if (state.dest)   pts.push([state.dest.lat,   state.dest.lng]);
  if (state.stop)   pts.push([state.stop.lat,   state.stop.lng]);
  if (pts.length >= 2) map.fitBounds(L.latLngBounds(pts).pad(0.2));
  else if (pts.length === 1) map.setView(pts[0], 16);
}

function setSourceBadge(source) {
  const el = $('#data-source');
  if (!source || source === 'empty') { el.className = 'map-source-badge'; el.textContent = ''; return; }
  const map_label = {
    osrm: 'Tuyến đường: OSM/OSRM (real)', cache: 'Tuyến đường: cache',
    photon: 'Địa điểm: OSM Photon', nominatim: 'Toạ độ: OSM Nominatim',
    error: 'Mất kết nối – dùng dữ liệu offline',
  };
  el.textContent = map_label[source] || source;
  el.className = 'map-source-badge show ' + (source === 'cache' ? 'cache' : source === 'error' ? 'error' : 'osm');
}

/* ====================== ROUTE ====================== */
async function recalcRoute() {
  if (!state.pickup || !state.dest) {
    state.distanceKm = 0; state.routeSrc = null;
    if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    $('#distance-box').classList.add('hidden');
    $('#dist-km').textContent = '— km';
    $('#dist-trip').textContent = '— phút';
    $('#eta-pickup').textContent = '— phút';
    updatePricing();
    return;
  }
  const points = [{ lat: state.pickup.lat, lng: state.pickup.lng }];
  if (state.stop) points.push({ lat: state.stop.lat, lng: state.stop.lng });
  points.push({ lat: state.dest.lat, lng: state.dest.lng });

  const res = await api('/api/route', { method: 'POST', body: { points } });
  if (!res.ok) { showToast(res.error || 'Không tìm được đường', 'error'); return; }

  state.distanceKm = res.distance_km || 0;
  state.routeSrc   = res.source;
  setSourceBadge(res.source);

  if (routeLine) map.removeLayer(routeLine);
  if (res.polyline && res.polyline.length) {
    routeLine = L.polyline(res.polyline, { color: '#00B14F', weight: 5, opacity: .85 }).addTo(map);
    map.fitBounds(routeLine.getBounds().pad(0.2));
  }

  $('#distance-box').classList.remove('hidden');
  $('#distance-num').textContent  = state.distanceKm.toFixed(2);
  $('#distance-label').textContent = `Giá ước tính cho ${state.distanceKm.toFixed(2)} km`;
  $('#dist-km').textContent        = state.distanceKm.toFixed(2) + ' km';
  $('#dist-trip').textContent      = (res.duration_min ? Math.round(res.duration_min) : Math.round(state.distanceKm * 2.5)) + ' phút';

  await updatePricing();
}

/* ====================== AUTOCOMPLETE ====================== */
function setupAutocomplete(inputId) {
  const input = document.getElementById(inputId);
  const list  = document.querySelector(`.ac-list[data-for="${inputId}"]`);
  let timer, active = -1, lastItems = [];

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { list.classList.remove('open'); list.innerHTML = ''; return; }
    timer = setTimeout(async () => {
      const res = await api('/api/places?q=' + encodeURIComponent(q));
      lastItems = (res.data || []);
      if (!lastItems.length) {
        list.innerHTML = '<div class="ac-empty">Không tìm thấy địa điểm phù hợp</div>';
      } else {
        list.innerHTML = lastItems.map((p, i) =>
          `<div class="ac-item" data-i="${i}">
            <i class="fa-solid fa-location-dot"></i>
            <div><div class="ac-name">${p.name}</div><div class="ac-addr">${p.addr}</div></div>
          </div>`
        ).join('');
        active = -1;
        setSourceBadge(res.source);
      }
      list.classList.add('open');
    }, 220);
  });

  list.addEventListener('click', (e) => {
    const item = e.target.closest('.ac-item');
    if (!item) return;
    selectItem(parseInt(item.dataset.i, 10));
  });

  input.addEventListener('keydown', (e) => {
    if (!list.classList.contains('open')) return;
    const items = list.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, items.length - 1); render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); render(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (active >= 0) selectItem(active); }
    else if (e.key === 'Escape') { list.classList.remove('open'); }
    function render() {
      items.forEach((it, i) => it.classList.toggle('active', i === active));
    }
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !list.contains(e.target)) list.classList.remove('open');
  });

  function selectItem(i) {
    const p = lastItems[i]; if (!p) return;
    input.value = p.name + ' – ' + p.addr;
    list.classList.remove('open');
    setLocation(inputId, p);
  }
}

function setLocation(role, p) {
  state[role] = p;
  refreshMarkers(); fitToMarkers(); recalcRoute();
}

setupAutocomplete('pickup');
setupAutocomplete('dest');

/* ====================== CLICK BẢN ĐỒ ====================== */
map.on('click', async (e) => {
  const { lat, lng } = e.latlng;
  const res = await api(`/api/nearest?lat=${lat}&lng=${lng}`);
  if (!res.ok) { showToast(res.error || 'Không lấy được địa chỉ', 'error'); return; }
  const place = res.data;
  setSourceBadge(res.source);

  let role;
  if (!state.pickup)           role = 'pickup';
  else if (!state.dest)        role = 'dest';
  else if (state.hasStopInput) role = 'stop';
  else                         role = 'pickup';

  if (role === 'pickup' && state.pickup && state.dest) {
    state.pickup = state.dest = state.stop = null;
  }
  state[role] = place;
  const inp = document.getElementById(role);
  if (inp) inp.value = place.name + ' – ' + place.addr;
  refreshMarkers(); fitToMarkers(); recalcRoute();
});

/* ====================== ADD STOP / CLEAR ====================== */
$('#add-stop-btn').addEventListener('click', () => {
  if (state.hasStopInput) return;
  state.hasStopInput = true;
  const row = document.createElement('div');
  row.className = 'input-row'; row.dataset.role = 'stop';
  row.innerHTML = `
    <span class="input-dot stop"></span>
    <div class="ac-wrap">
      <input id="stop" class="field-input ac-input" type="text"
             autocomplete="off" placeholder="Điểm dừng (tuỳ chọn)...">
      <div class="ac-list" data-for="stop"></div>
    </div>`;
  $('#route-inputs').appendChild(row);
  setupAutocomplete('stop');
  showToast('Đã thêm điểm dừng. Bạn có thể click bản đồ lần thứ 3.', 'success');
});

$('#clear-route-btn').addEventListener('click', () => {
  state.pickup = state.dest = state.stop = null;
  $('#pickup').value = ''; $('#dest').value = '';
  if ($('#stop')) $('#stop').value = '';
  if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  refreshMarkers(); recalcRoute();
});

/* ====================== RECENT ====================== */
$$('.recent-item').forEach(btn => {
  btn.addEventListener('click', async () => {
    const addr = btn.dataset.addr; if (!addr) return;
    const res = await api('/api/places?q=' + encodeURIComponent(addr) + '&limit=1');
    if (res.data && res.data[0]) {
      const target = !state.pickup ? 'pickup' : (!state.dest ? 'dest' : 'pickup');
      if (target === 'pickup' && state.pickup && state.dest) { state.pickup = state.dest = state.stop = null; }
      const inp = document.getElementById(target);
      if (inp) inp.value = res.data[0].name + ' – ' + res.data[0].addr;
      setLocation(target, res.data[0]);
    }
  });
});

/* ====================== VEHICLE / TIP / INS ====================== */
$$('.vehicle-card').forEach(card => {
  card.addEventListener('click', () => {
    $$('.vehicle-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    state.vehicle = card.dataset.vehicle;
    updatePricing();
  });
});

$$('.tip-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.tip-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    state.tip = parseInt(btn.dataset.tip || '0', 10);
    updatePricing();
  });
});

$$('.ins-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.ins-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    state.insurance = parseInt(btn.dataset.ins || '0', 10);
    updatePricing();
  });
});

$('#payment').addEventListener('change', e => { state.payment = e.target.value; });
$('#promo').addEventListener('input', e => {
  state.promo = e.target.value.trim();
  clearTimeout($('#promo')._h);
  $('#promo')._h = setTimeout(updatePricing, 350);
});

/* ====================== CONDITIONS ====================== */
const COND_META = {
  weather:     { name: 'Thời tiết',      icon: 'cloud-sun', max: 10 },
  traffic:     { name: 'Giao thông',     icon: 'car',       max: 10 },
  demand:      { name: 'Mức cầu',        icon: 'users',     max: 10 },
  pickup:      { name: 'Độ khó đón',     icon: 'map-pin',   max: 5  },
  time_of_day: { name: 'Giờ trong ngày', icon: 'clock',     max: 10 },
};

async function loadConditions() {
  const lat = state.pickup ? state.pickup.lat : null;
  const lng = state.pickup ? state.pickup.lng : null;
  const url = '/api/conditions' + (lat ? `?pickup_lat=${lat}&pickup_lng=${lng}` : '');
  const res = await api(url);
  if (!res.ok) return;
  state.conditions = res.data;
  renderConditions();
  $('#conditions-sub').textContent = 'Cập nhật ' + new Date().toLocaleTimeString('vi-VN');
}

function renderConditions() {
  const grid = $('#conditions-grid');
  if (!state.conditions) { grid.innerHTML = ''; return; }
  grid.innerHTML = Object.keys(COND_META).map(k => {
    const c = state.conditions[k]; if (!c) return '';
    const meta = COND_META[k];
    const max  = c.scale_max || meta.max;
    const pct  = Math.min(100, (c.score / max) * 100);
    const text = c.text || c.weather_text || (k === 'time_of_day' ? `Giờ ${c.hour}:00` : '');
    return `
      <div class="cond-card">
        <div class="cond-head">
          <div class="cond-name"><i class="fa-solid fa-${meta.icon}"></i> ${meta.name}</div>
          <div class="cond-score">${c.score}/${max}</div>
        </div>
        <div class="cond-bar"><div class="cond-fill" style="width:${pct}%"></div></div>
        <div class="cond-text" title="${text}">${text}</div>
      </div>`;
  }).join('');
}

$('#refresh-conditions').addEventListener('click', loadConditions);

/* ====================== PRICING ====================== */
async function updatePricing() {
  if (!state.distanceKm || !state.pickup || !state.dest) {
    $('#price-value').textContent = '—đ';
    $('#price-sub').textContent   = 'Chưa có lộ trình';
    $('#fare-breakdown').innerHTML = '<div class="breakdown-empty">Hãy chọn điểm đón và điểm đến để xem giá chi tiết.</div>';
    $$('.vehicle-price').forEach(el => el.textContent = '—đ');
    return;
  }

  const selectedRes = await api('/api/pricing', {
    method: 'POST',
    body: {
      vehicle:         state.vehicle,
      distance_km:     state.distanceKm,
      pickup_lat:      state.pickup.lat,
      pickup_lng:      state.pickup.lng,
      insurance_level: state.insurance,
      tip:             state.tip,
      promo_code:      state.promo,
    },
  });
  if (!selectedRes || !selectedRes.ok) return;

  state.fare = selectedRes.data;
  renderBreakdown(state.fare);

  const vehicleEl = document.querySelector(`.vehicle-price[data-price="${state.vehicle}"]`);
  if (vehicleEl) vehicleEl.textContent = fmtMoney(state.fare.total);

  $('#price-value').textContent = fmtMoney(state.fare.total);
  $('#price-sub').textContent   = `${state.fare.vehicle_label} • ${state.fare.distance_km.toFixed(2)} km • Đón ~${state.fare.eta_pickup_min}p`;
  $('#eta-pickup').textContent  = state.fare.eta_pickup_min + ' phút';
  $('#dist-trip').textContent   = state.fare.eta_trip_min + ' phút';

  state.conditions = state.fare.factors;
  renderConditions();
}

function renderBreakdown(fare) {
  const rows = fare.items.map(it => {
    // Nhận diện dòng phụ phí fuzzy để tô màu riêng
    const isFuzzy = it.label === 'Phụ phí thu thêm';
    const cls     = isFuzzy ? 'bd-row fuzzy-surcharge' : 'bd-row';
    return `
      <div class="${cls}">
        <div>
          <div class="bd-label">${it.label}</div>
          <div class="bd-note">${it.note || ''}</div>
        </div>
        <div class="bd-fee">${fmtMoney(it.fee)}</div>
      </div>`;
  }).join('');

  let promoRow = '';
  if (fare.promo && fare.promo.discount > 0) {
    promoRow = `
      <div class="bd-row">
        <div>
          <div class="bd-label">Khuyến mãi</div>
          <div class="bd-note">${fare.promo.label}</div>
        </div>
        <div class="bd-fee discount">- ${fmtMoney(fare.promo.discount)}</div>
      </div>`;
  }

  let savingsRow = '';
  if (fare.savings_vs_normal > 0) {
    savingsRow = `
      <div class="bd-row">
        <div>
          <div class="bd-label">Tiết kiệm so với xe thường</div>
          <div class="bd-note">Bạn đã tiết kiệm được</div>
        </div>
        <div class="bd-fee discount">${fmtMoney(fare.savings_vs_normal)}</div>
      </div>`;
  }

  $('#fare-breakdown').innerHTML = `
    ${rows}
    <div class="bd-row subtotal">
      <div><div class="bd-label">Tạm tính</div></div>
      <div class="bd-fee">${fmtMoney(fare.subtotal)}</div>
    </div>
    ${promoRow}
    <div class="bd-row total">
      <div><div class="bd-label">TỔNG THANH TOÁN</div></div>
      <div class="bd-fee">${fmtMoney(fare.total)}</div>
    </div>
    ${savingsRow}
  `;
}

/* ====================== CONFIRM BOOKING ====================== */
$('#confirm-btn').addEventListener('click', async () => {
  if (!state.pickup || !state.dest) {
    showToast('Vui lòng chọn điểm đón và điểm đến trước.', 'error'); return;
  }
  const phone = $('#phone').value.trim();
  if (!phone) {
    showToast('Vui lòng nhập số điện thoại liên lạc.', 'error');
    $('#phone').focus(); return;
  }
  const btn = $('#confirm-btn');
  btn.classList.add('loading'); btn.disabled = true;

  const body = {
    pickup:          state.pickup.name + ' – ' + state.pickup.addr,
    dest:            state.dest.name   + ' – ' + state.dest.addr,
    stop:            state.stop ? (state.stop.name + ' – ' + state.stop.addr) : '',
    pickup_coord:    state.pickup ? { lat: state.pickup.lat, lng: state.pickup.lng } : null,
    dest_coord:      state.dest   ? { lat: state.dest.lat,   lng: state.dest.lng }   : null,
    stop_coord:      state.stop   ? { lat: state.stop.lat,   lng: state.stop.lng }   : null,
    vehicle:         state.vehicle,
    distance_km:     state.distanceKm,
    tip:             state.tip,
    insurance_level: state.insurance,
    payment:         state.payment,
    promo_code:      state.promo,
    phone:           phone,
    note:            $('#note').value.trim(),
  };

  const res = await api('/api/book', { method: 'POST', body });
  btn.classList.remove('loading'); btn.disabled = false;

  if (!res.ok) { showToast('Đặt xe thất bại. Vui lòng thử lại.', 'error'); return; }
  showToast(res.message || 'Đã đặt chuyến thành công!', 'success');
  loadStats();
});

/* ====================== STATS / HISTORY VIEW ====================== */
async function loadStats() {
  const res = await api('/api/stats'); if (!res.ok) return;
  $('#stat-trips').textContent   = res.data.trips   || '—';
  $('#stat-savings').textContent = res.data.savings  ? fmtMoney(res.data.savings) : '—';
}

async function loadHistoryView() {
  const list = $('#history-list');
  list.innerHTML = '<div class="history-empty">Đang tải...</div>';
  const res = await api('/api/history');
  if (!res.ok || !res.data.length) {
    list.innerHTML = '<div class="history-empty">Chưa có chuyến đi nào. Hãy đặt chuyến đầu tiên!</div>';
    return;
  }
  list.innerHTML = res.data.map(r => `
    <div class="ride-card">
      <div class="ride-head">
        <div class="ride-vehicle"><i class="fa-solid fa-car-side"></i> ${r.vehicle_label || r.vehicle}</div>
        <div class="ride-time">${new Date(r.timestamp).toLocaleString('vi-VN')}</div>
      </div>
      <div class="ride-route">
        <div class="ride-row"><span class="dot-mini start"></span> <span>${r.pickup}</span></div>
        ${r.stop ? `<div class="ride-row"><span class="dot-mini stop"></span> <span>${r.stop}</span></div>` : ''}
        <div class="ride-row"><span class="dot-mini end"></span> <span>${r.dest}</span></div>
      </div>
      <div class="ride-foot">
        <div class="ride-meta">
          <span><i class="fa-solid fa-route"></i> ${(r.distance_km || 0).toFixed(2)} km</span>
          <span><i class="fa-solid fa-credit-card"></i> ${r.payment}</span>
          ${r.insurance_level ? `<span><i class="fa-solid fa-shield"></i> Bảo hiểm L${r.insurance_level}</span>` : ''}
          ${r.tip ? `<span><i class="fa-solid fa-star"></i> Tip ${fmtMoney(r.tip)}</span>` : ''}
          ${r.promo_code ? `<span><i class="fa-solid fa-ticket"></i> ${r.promo_code}</span>` : ''}
        </div>
        <div class="ride-total">${fmtMoney(r.total)}</div>
      </div>
    </div>`
  ).join('');
}

async function loadStatsView() {
  const wrap = $('#stats-cards');
  wrap.innerHTML = '<div class="history-empty">Đang tải...</div>';
  const res = await api('/api/stats'); if (!res.ok) return;
  const s = res.data;
  wrap.innerHTML = `
    <div class="stat-card"><div class="lbl">Tổng số chuyến</div><div class="val">${s.trips || 0}</div></div>
    <div class="stat-card"><div class="lbl">Tổng quãng đường</div><div class="val">${s.total_km || 0} km</div></div>
    <div class="stat-card"><div class="lbl">Tổng đã chi</div><div class="val">${fmtMoney(s.total_spent || 0)}</div></div>
    <div class="stat-card"><div class="lbl">Tổng tiết kiệm</div><div class="val" style="color:var(--green)">${fmtMoney(s.savings || 0)}</div></div>
    <div class="stat-card"><div class="lbl">Đánh giá trung bình</div><div class="val" style="color:var(--orange)">${(s.rating || 5).toFixed(1)} ★</div></div>`;
}

/* ====================== TAB SWITCHING ====================== */
function switchView(view) {
  $$('.nav-pill').forEach(p => p.classList.toggle('active', p.dataset.view === view));
  $$('.mbn-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $('#view-book').classList.toggle('hidden', view !== 'book');
  $('#confirm-bar').classList.toggle('hidden', view !== 'book');
  $('#view-history').classList.toggle('hidden', view !== 'history');
  $('#view-stats').classList.toggle('hidden', view !== 'stats');
  if (view === 'history') loadHistoryView();
  if (view === 'stats')   loadStatsView();
  if (view === 'book')    setTimeout(() => map.invalidateSize(), 100);
}

$$('.nav-pill').forEach(pill => {
  pill.addEventListener('click', () => switchView(pill.dataset.view));
});
$$('.mbn-btn').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

/* ====================== CĂNH VIỀN PANEL ====================== */
function alignBorders() {
  const confirmBar = document.querySelector('.confirm-section');
  const rightPanel = document.querySelector('.right-panel');
  if (!confirmBar || !rightPanel) return;
  const h = confirmBar.offsetHeight;
  if (h > 0) rightPanel.style.gridTemplateRows = `1fr ${h}px`;
}
window.addEventListener('load',   alignBorders);
window.addEventListener('resize', alignBorders);

/* ====================== INIT ====================== */
loadConditions();
setInterval(loadConditions, 5 * 60 * 1000);
setTimeout(() => map.invalidateSize(), 200);

/* ====================== PWA SERVICE WORKER ====================== */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  });
}

})();
