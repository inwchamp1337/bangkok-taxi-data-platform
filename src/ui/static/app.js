/**
 * Bangkok Taxi Data Engineering Platform — Control Panel Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const scenarioCards = document.querySelectorAll('.scenario-card');
  const fleetSlider = document.getElementById('num-taxis');
  const fleetVal = document.getElementById('fleet-size-val');
  const daysSlider = document.getElementById('num-days');
  const daysVal = document.getElementById('days-val');
  const startDateInput = document.getElementById('start-date');

  const btnRunAll = document.getElementById('btn-run-all');
  const btnGenerate = document.getElementById('btn-generate');
  const btnLoad = document.getElementById('btn-load');
  const btnDbt = document.getElementById('btn-dbt');
  const btnReset = document.getElementById('btn-reset');
  const btnClearLogs = document.getElementById('btn-clear-logs');

  const terminalLogs = document.getElementById('terminal-logs');
  const connStatus = document.getElementById('connection-status');
  const statusText = document.getElementById('status-text');

  // Stats Counters
  const statRawPings = document.getElementById('stat-raw-pings');
  const statStgPings = document.getElementById('stat-stg-pings');
  const statFactTrips = document.getElementById('stat-fact-trips');
  const statDimTaxi = document.getElementById('stat-dim-taxi');

  // Slider Listeners
  fleetSlider.addEventListener('input', (e) => {
    fleetVal.textContent = `${e.target.value} taxis`;
  });

  daysSlider.addEventListener('input', (e) => {
    daysVal.textContent = `${e.target.value} day${e.target.value > 1 ? 's' : ''}`;
  });

  // Scenario Card Selection
  scenarioCards.forEach((card) => {
    card.addEventListener('click', () => {
      scenarioCards.forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      const radio = card.querySelector('input[type="radio"]');
      radio.checked = true;
      appendLog(`[scenario] Selected: ${card.dataset.scenario.toUpperCase()}`);
    });
  });

  // Logging Helper
  function appendLog(message, isError = false) {
    const timestamp = new Date().toLocaleTimeString();
    const prefix = `[${timestamp}] `;
    terminalLogs.textContent += `\n${prefix}${message}`;
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  btnClearLogs.addEventListener('click', () => {
    terminalLogs.textContent = '[system] Logs cleared.';
  });

  // Toast Notification Helper
  function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${type === 'success' ? '✅' : '⚠️'}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Global clipboard copy helper
  window.copyToClipboard = function(text, typeName) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`Copied ${typeName} to clipboard: ${text}`, 'success');
    }).catch(err => {
      showToast(`Failed to copy: ${err}`, 'error');
    });
  };

  // Get Current Request Payload
  function getPayload() {
    const selectedScenario = document.querySelector('input[name="scenario"]:checked').value;
    return {
      num_taxis: parseInt(fleetSlider.value, 10),
      num_days: parseInt(daysSlider.value, 10),
      scenario: selectedScenario,
      chaos_rate: selectedScenario === 'chaos' ? 0.05 : 0.0,
      start_date: startDateInput.value,
    };
  }

  // Fetch Real-time System Status
  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error('Status endpoint unavailable');
      const data = await res.json();

      // Update Connection Status
      if (data.clickhouse.connected) {
        connStatus.className = 'status-badge status-online';
        statusText.textContent = 'ClickHouse Online';
      } else {
        connStatus.className = 'status-badge status-error';
        statusText.textContent = 'ClickHouse Offline';
      }

      // Update Table Counters
      const tables = data.clickhouse.tables;
      statRawPings.textContent = Number(tables.raw_gps_pings || 0).toLocaleString();
      statStgPings.textContent = Number(tables.stg_gps_pings || 0).toLocaleString();
      statFactTrips.textContent = Number(tables.fact_trips || 0).toLocaleString();
      statDimTaxi.textContent = Number(tables.dim_taxi || 0).toLocaleString();
    } catch (err) {
      connStatus.className = 'status-badge status-error';
      statusText.textContent = 'Connection Error';
    }
  }

  // API Call Wrapper with Button Loading States
  async function executeAction(btn, actionName, endpoint, payload = null) {
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="pulse-dot"></span> <span>Running ${actionName}...</span>`;
    appendLog(`[action] Starting ${actionName}...`);

    try {
      const options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      };
      if (payload) {
        options.body = JSON.stringify(payload);
      }

      const res = await fetch(endpoint, options);
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || `Action failed with status ${res.status}`);
      }

      appendLog(`[success] ${actionName} finished: ${data.message || JSON.stringify(data.status || 'OK')}`);
      showToast(`${actionName} completed successfully!`, 'success');
      await fetchStatus();
      return data;
    } catch (err) {
      appendLog(`[error] ${actionName} failed: ${err.message}`, true);
      showToast(`${actionName} failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }

  // Action Button Handlers
  btnRunAll.addEventListener('click', async () => {
    const payload = getPayload();
    appendLog(`[pipeline] Launching Full Pipeline (${payload.scenario.toUpperCase()}, ${payload.num_taxis} taxis, ${payload.num_days} days)`);
    await executeAction(btnRunAll, 'Selected Pipeline', '/api/pipeline/run-all', payload);
  });

  const btnRunAllScenarios = document.getElementById('btn-run-all-scenarios');
  btnRunAllScenarios.addEventListener('click', async () => {
    const payload = getPayload();
    appendLog(`[pipeline] Launching Full Pipeline for ALL 5 SCENARIOS (${payload.num_taxis} taxis, ${payload.num_days} days)`);
    await executeAction(btnRunAllScenarios, 'All Scenarios Pipeline', '/api/pipeline/run-all-scenarios', payload);
  });

  btnGenerate.addEventListener('click', async () => {
    const payload = getPayload();
    await executeAction(btnGenerate, 'Data Generation', '/api/generate', payload);
  });

  btnLoad.addEventListener('click', async () => {
    await executeAction(btnLoad, 'ClickHouse Load', '/api/load');
  });

  btnDbt.addEventListener('click', async () => {
    await executeAction(btnDbt, 'dbt Run', '/api/dbt/run');
  });

  btnReset.addEventListener('click', async () => {
    if (confirm('Are you sure you want to truncate all ClickHouse tables and mock files?')) {
      await executeAction(btnReset, 'Database Reset', '/api/reset');
    }
  });

  // Live Stream Logic
  const btnLiveStream = document.getElementById('btn-live-stream');
  const liveIcon = document.getElementById('live-icon');
  const liveText = document.getElementById('live-text');
  let isLive = false;

  async function checkLiveStatus() {
    try {
      const res = await fetch('/api/stream/status');
      const data = await res.json();
      isLive = data.is_running;
      if (isLive) {
        liveIcon.classList.add('pulse-dot');
        liveIcon.style.color = 'white';
        liveText.textContent = 'Stop Live Stream';
        btnLiveStream.style.backgroundColor = '#10b981'; // Green to stop
      } else {
        liveIcon.classList.remove('pulse-dot');
        liveText.textContent = 'Start Live Stream';
        btnLiveStream.style.backgroundColor = '#ef4444'; // Red to start
      }
    } catch (e) {
      console.error(e);
    }
  }

  let fetchIntervalId = null;

  btnLiveStream.addEventListener('click', async () => {
    if (isLive) {
      await fetch('/api/stream/stop', { method: 'POST' });
      // Revert to 5s polling when stopped
      if (fetchIntervalId) clearInterval(fetchIntervalId);
      fetchIntervalId = setInterval(fetchFleetLocations, 5000);
    } else {
      const intervalVal = parseInt(document.getElementById('live-interval').value) || 5;
      document.documentElement.style.setProperty('--stream-interval', `${intervalVal}s`);
      await fetch('/api/stream/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interval: intervalVal })
      });
      // Poll map at the same interval
      if (fetchIntervalId) clearInterval(fetchIntervalId);
      fetchIntervalId = setInterval(fetchFleetLocations, intervalVal * 1000);
    }
    await checkLiveStatus();
  });

  setInterval(checkLiveStatus, 5000);
  checkLiveStatus();

  // --- Live Fleet Tracking Map Setup ---
  let fleetMap = L.map('fleet-map').setView([13.7563, 100.5018], 11);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
  }).addTo(fleetMap);
  let markersLayer = L.layerGroup().addTo(fleetMap);
  const mapStatus = document.getElementById('map-status');

  let vehicleMarkers = {}; // Store markers by vehicle_id to animate them

  async function fetchFleetLocations() {
    try {
      const res = await fetch('/api/fleet/locations');
      if (!res.ok) return;
      const data = await res.json();
      
      if (data.data.length === 0) {
        mapStatus.textContent = 'No active fleet data';
        mapStatus.className = 'badge-pill';
        return;
      }

      mapStatus.textContent = `Live: ${data.data.length} vehicles`;
      mapStatus.className = 'badge-pill status-online';

      const seenIds = new Set();
      data.data.forEach(v => {
        seenIds.add(v.vehicle_id);
        const isVacant = v.passenger_lamp === 1;
        const color = isVacant ? '#10b981' : '#f59e0b';
        const popupContent = `<b>Taxi ID:</b> ${v.vehicle_id.substring(0,8)}...<br><b>Speed:</b> ${v.speed} km/h<br><b>Status:</b> ${isVacant ? 'Vacant (Green)' : 'Occupied (Orange)'}`;

        if (vehicleMarkers[v.vehicle_id]) {
          // Update existing marker position (CSS transition handles smooth gliding)
          const m = vehicleMarkers[v.vehicle_id];
          m.setLatLng([v.lat, v.lon]);
          m.getPopup().setContent(popupContent);
          // Update colors if status changed
          const div = m.getElement().querySelector('div');
          if (div) {
            div.style.backgroundColor = color;
            div.style.color = color;
          }
        } else {
          // Create new marker using divIcon to allow CSS transitions
          const icon = L.divIcon({
            className: 'taxi-marker',
            iconSize: [6, 6],
            html: `<div style="width: 100%; height: 100%; border-radius: 50%; background-color: ${color}; color: ${color}; box-shadow: 0 0 6px currentColor;"></div>`
          });
          const marker = L.marker([v.lat, v.lon], { icon: icon });
          marker.bindPopup(popupContent);
          marker.addTo(fleetMap);
          vehicleMarkers[v.vehicle_id] = marker;
        }
      });

      // Remove stale markers that haven't sent pings
      for (const id in vehicleMarkers) {
        if (!seenIds.has(id)) {
          fleetMap.removeLayer(vehicleMarkers[id]);
          delete vehicleMarkers[id];
        }
      }
    } catch (e) {
      console.error('Failed to update map', e);
    }
  }

  // Initial Poll & Interval
  fetchStatus();
  fetchFleetLocations();
  setInterval(fetchStatus, 3000);
  fetchIntervalId = setInterval(fetchFleetLocations, 5000);
});
