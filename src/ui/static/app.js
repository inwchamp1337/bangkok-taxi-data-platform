/**
 * Bangkok Taxi Data Platform — Paper UI Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── Elements ──
  const scenarioCards = document.querySelectorAll('.scenario-item');
  const fleetSlider   = document.getElementById('num-taxis');
  const fleetVal      = document.getElementById('fleet-size-val');
  const daysSlider    = document.getElementById('num-days');
  const daysVal       = document.getElementById('days-val');
  const startDateInput = document.getElementById('start-date');

  const btnRunAll     = document.getElementById('btn-run-all');
  const btnGenerate   = document.getElementById('btn-generate');
  const btnLoad       = document.getElementById('btn-load');
  const btnDbt        = document.getElementById('btn-dbt');
  const btnReset      = document.getElementById('btn-reset');
  const btnClearLogs  = document.getElementById('btn-clear-logs');

  const terminalLogs  = document.getElementById('terminal-logs');
  const connStatus    = document.getElementById('connection-status');
  const statusText    = document.getElementById('status-text');

  // Stats Counters
  const statRawPings  = document.getElementById('stat-raw-pings');
  const statStgPings  = document.getElementById('stat-stg-pings');
  const statFactTrips = document.getElementById('stat-fact-trips');
  const statDimTaxi   = document.getElementById('stat-dim-taxi');

  // ── Slider Listeners ──
  fleetSlider.addEventListener('input', (e) => {
    fleetVal.textContent = `${e.target.value} taxis`;
  });

  daysSlider.addEventListener('input', (e) => {
    daysVal.textContent = `${e.target.value} day${e.target.value > 1 ? 's' : ''}`;
  });

  // ── Scenario Card Selection ──
  scenarioCards.forEach((card) => {
    card.addEventListener('click', (e) => {
      if (e.target.tagName.toLowerCase() === 'input') return;
      scenarioCards.forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      const radio = card.querySelector('input[type="radio"]');
      radio.checked = true;
      appendLog(`[scenario] Selected: ${card.dataset.scenario.toUpperCase()}`);
    });
  });

  // ── Logging Helper ──
  function appendLog(message) {
    const timestamp = new Date().toLocaleTimeString();
    terminalLogs.textContent += `\n[${timestamp}] ${message}`;
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }

  btnClearLogs.addEventListener('click', () => {
    terminalLogs.textContent = '[system] Logs cleared.';
  });

  // ── Toast Notification ──
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

  // ── Clipboard Copy ──
  window.copyToClipboard = function(text, typeName) {
    navigator.clipboard.writeText(text).then(() => {
      showToast(`Copied ${typeName}: ${text}`, 'success');
    }).catch(err => {
      showToast(`Copy failed: ${err}`, 'error');
    });
  };

  // ── Payload ──
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

  // ── Status Polling ──
  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error('Status endpoint unavailable');
      const data = await res.json();

      if (data.clickhouse.connected) {
        connStatus.className = 'status-pill status-online';
        statusText.textContent = 'ClickHouse Online';
      } else {
        connStatus.className = 'status-pill status-error';
        statusText.textContent = 'ClickHouse Offline';
      }

      const tables = data.clickhouse.tables;
      statRawPings.textContent  = Number(tables.raw_gps_pings || 0).toLocaleString();
      statStgPings.textContent  = Number(tables.stg_gps_pings || 0).toLocaleString();
      statFactTrips.textContent = Number(tables.fact_trips || 0).toLocaleString();
      statDimTaxi.textContent   = Number(tables.dim_taxi || 0).toLocaleString();
    } catch {
      connStatus.className = 'status-pill status-error';
      statusText.textContent = 'Connection Error';
    }
  }

  // ── API Call Wrapper ──
  async function executeAction(btn, actionName, endpoint, payload = null) {
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="pulse-dot"></span> Running ${actionName}…`;
    appendLog(`[action] Starting ${actionName}...`);
    const startTime = performance.now();

    try {
      const options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      };
      if (payload) options.body = JSON.stringify(payload);

      const res = await fetch(endpoint, options);
      const data = await res.json();

      if (!res.ok || (data && data.status === 'error')) {
        const errorMsg = data.detail || data.stderr || data.stdout || data.message || `Failed (${res.status})`;
        throw new Error(errorMsg);
      }

      const duration = ((performance.now() - startTime) / 1000).toFixed(2);
      appendLog(`[success] ${actionName} finished in ${duration}s: ${data.message || JSON.stringify(data.status || 'OK')}`);
      showToast(`${actionName} completed!`, 'success');
      await fetchStatus();
      return data;
    } catch (err) {
      appendLog(`[error] ${actionName} failed: ${err.message}`);
      showToast(`${actionName} failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }

  // ── Button Handlers ──
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
    await executeAction(btnGenerate, 'Data Generation', '/api/generate', getPayload());
  });

  btnLoad.addEventListener('click', async () => {
    await executeAction(btnLoad, 'ClickHouse Load', '/api/load');
  });

  btnDbt.addEventListener('click', async () => {
    await executeAction(btnDbt, 'dbt Run', '/api/dbt/run');
  });

  btnReset.addEventListener('click', async () => {
    if (confirm('Are you sure you want to truncate all ClickHouse tables and delete mock files?')) {
      await executeAction(btnReset, 'Database Reset', '/api/reset');
    }
  });

  // ── Init ──
  fetchStatus();
  setInterval(fetchStatus, 5000);
});
