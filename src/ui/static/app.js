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

  // --- Live Fleet Tracking Map Setup ---
  let fleetMap = L.map('fleet-map').setView([13.7563, 100.5018], 11);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 20
  }).addTo(fleetMap);
  let markersLayer = L.layerGroup().addTo(fleetMap);
  const mapStatus = document.getElementById('map-status');

  async function fetchFleetLocations() {
    try {
      const res = await fetch('/api/fleet/locations');
      if (!res.ok) return;
      const data = await res.json();
      
      markersLayer.clearLayers();
      if (data.data.length === 0) {
        mapStatus.textContent = 'No active fleet data';
        mapStatus.className = 'badge-pill';
        return;
      }

      mapStatus.textContent = `Live: ${data.data.length} vehicles`;
      mapStatus.className = 'badge-pill status-online';

      data.data.forEach(v => {
        const isVacant = v.passenger_lamp === 1;
        const color = isVacant ? '#10b981' : '#f59e0b';
        const circle = L.circleMarker([v.lat, v.lon], {
          radius: 3,
          fillColor: color,
          color: color,
          weight: 1,
          opacity: 0.8,
          fillOpacity: 0.8
        });
        circle.bindPopup(`<b>Taxi ID:</b> ${v.vehicle_id.substring(0,8)}...<br><b>Speed:</b> ${v.speed} km/h<br><b>Status:</b> ${isVacant ? 'Vacant (Green)' : 'Occupied (Orange)'}`);
        markersLayer.addLayer(circle);
      });
    } catch (e) {
      console.error('Failed to update map', e);
    }
  }

  // Initial Poll & Interval
  fetchStatus();
  fetchFleetLocations();
  setInterval(fetchStatus, 3000);
  setInterval(fetchFleetLocations, 5000);
});
