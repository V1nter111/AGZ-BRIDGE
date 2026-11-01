"""Interactive Web Dashboard for AGZ Bridge Host."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from agz_bridge.auth.pairing import get_pairing_manager
from agz_bridge.config.settings import get_settings
from agz_bridge.monitoring.metrics import get_metrics

router = APIRouter(tags=["Dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AGZ Bridge Host Dashboard</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <style>
    :root {
      --pico-primary: #1a73e8;
      --pico-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    body { padding: 1.5rem; background: #0f172a; color: #f8fafc; }
    main { max-width: 1200px; margin: 0 auto; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1.5rem; margin-bottom: 1.5rem; }
    .header-box { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 1rem; margin-bottom: 1.5rem; }
    .status-badge { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0.85rem; border-radius: 9999px; font-weight: bold; font-size: 0.875rem; }
    .badge-online { background: #065f46; color: #34d399; }
    .code-display { font-family: monospace; font-size: 1.75rem; font-weight: bold; letter-spacing: 2px; color: #38bdf8; background: #0f172a; padding: 0.75rem 1.25rem; border-radius: 8px; border: 1px dashed #0284c7; text-align: center; }
    .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; }
    .metric-box { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 1rem; text-align: center; }
    .metric-val { font-size: 1.85rem; font-weight: bold; color: #f8fafc; margin-top: 0.25rem; }
    .metric-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; }
    pre { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 1rem; font-size: 0.85rem; overflow-x: auto; color: #e2e8f0; }
    table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
    th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }
    th { color: #94a3b8; }
    .btn-sm { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
    .btn-copy { background: #0284c7; border: none; cursor: pointer; color: white; border-radius: 6px; padding: 0.5rem 1rem; font-weight: bold; }
    .btn-copy:hover { background: #0369a1; }
  </style>
</head>
<body>
<main>
  <div class="header-box">
    <div>
      <h2 style="margin: 0; color: #38bdf8;">AGZ BRIDGE HOST</h2>
      <p style="margin: 0.25rem 0 0 0; color: #94a3b8;">Autonomous Bridge: Antigravity 2.0 CLI &rarr; Agent Zero</p>
    </div>
    <div>
      <span class="status-badge badge-online">&bull; HOST ONLINE</span>
    </div>
  </div>

  <div class="grid">
    <!-- Pairing Section -->
    <div class="card">
      <h3 style="color: #38bdf8; margin-top: 0;">Device Pairing</h3>
      <p style="color: #94a3b8; font-size: 0.9rem;">
        Use this one-time code to connect Agent Zero from your SECOND PC. The code expires in 15 minutes.
      </p>
      <div id="code-container" style="margin: 1rem 0;">
        <div class="code-display" id="pairing-code">LOADING...</div>
      </div>
      <div style="display: flex; gap: 0.75rem;">
        <button class="btn-copy" onclick="copyCode()">Copy Code</button>
        <button class="btn-sm" style="background: #334155; border: none;" onclick="generateNewCode()">Generate New Code</button>
      </div>

      <div style="margin-top: 1.5rem;">
        <label style="font-weight: bold; font-size: 0.9rem; color: #94a3b8;">One-Command Worker Setup (PowerShell on SECOND PC):</label>
        <pre><code id="worker-cmd">Loading command...</code></pre>
        <button class="btn-copy" onclick="copyWorkerCmd()">Copy Command</button>
      </div>
    </div>

    <!-- System Info & Metrics -->
    <div class="card">
      <h3 style="color: #38bdf8; margin-top: 0;">Real-Time Metrics</h3>
      <div class="metric-grid">
        <div class="metric-box">
          <div class="metric-label">Total Requests</div>
          <div class="metric-val" id="metric-requests">-</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Total Tokens</div>
          <div class="metric-val" id="metric-tokens">-</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Avg Response Time</div>
          <div class="metric-val" id="metric-latency">-</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Active Workers</div>
          <div class="metric-val" id="metric-workers">-</div>
        </div>
      </div>

      <div style="margin-top: 1.5rem;">
        <h4 style="color: #94a3b8; font-size: 0.9rem; margin-bottom: 0.5rem;">Network Endpoints</h4>
        <div style="font-size: 0.85rem; line-height: 1.6; color: #cbd5e1;">
          <div><strong>LAN Endpoint:</strong> <code id="lan-url">-</code></div>
          <div><strong>Tailscale:</strong> <code id="ts-url">-</code></div>
          <div><strong>Default Model:</strong> <code id="def-model">-</code></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Paired Workers Table -->
  <div class="card">
    <h3 style="color: #38bdf8; margin-top: 0;">Connected Worker Devices</h3>
    <table id="workers-table">
      <thead>
        <tr>
          <th>Worker ID</th>
          <th>Name</th>
          <th>OS</th>
          <th>IP Address</th>
          <th>Last Seen</th>
          <th>Status</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="workers-body">
        <tr><td colspan="7" style="text-align: center; color: #64748b;">No workers paired yet.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Recent Requests -->
  <div class="card">
    <h3 style="color: #38bdf8; margin-top: 0;">Recent Request Activity</h3>
    <table>
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Worker</th>
          <th>Model</th>
          <th>Tokens (In/Out)</th>
          <th>Latency</th>
          <th>Mode</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody id="requests-body">
        <tr><td colspan="7" style="text-align: center; color: #64748b;">No requests recorded yet.</td></tr>
      </tbody>
    </table>
  </div>
</main>

<script>
let currentPairingCode = "";
let currentHostUrl = "";

async function refreshData() {
  try {
    // 1. Fetch status and code
    const statusRes = await fetch('/api/pair/status');
    const statusData = await statusRes.json();
    currentHostUrl = statusData.tailscale_ip ? `http://${statusData.tailscale_ip}:8765` : `http://${statusData.lan_ip}:8765`;
    document.getElementById('lan-url').innerText = `http://${statusData.lan_ip}:8765`;
    document.getElementById('ts-url').innerText = statusData.tailscale_ip ? `http://${statusData.tailscale_ip}:8765` : 'Disabled / Not connected';
    document.getElementById('def-model').innerText = statusData.default_model;

    // 2. Fetch active pairing code
    const pairRes = await fetch('/api/pair/generate', { method: 'POST' });
    const pairData = await pairRes.json();
    currentPairingCode = pairData.pairing_code;
    document.getElementById('pairing-code').innerText = currentPairingCode;

    // Update command snippet
    const rawUrl = "https://raw.githubusercontent.com/V1nter111/AGZ-BRIDGE/v1.0.0/scripts/install-worker.ps1";
    const cmd = `& ([scriptblock]::Create((irm "${rawUrl}"))) -HostUrl "${currentHostUrl}" -PairingCode "${currentPairingCode}"`;
    document.getElementById('worker-cmd').innerText = cmd;

    // 3. Fetch Metrics
    const metricsRes = await fetch('/api/metrics');
    const metrics = await metricsRes.json();
    document.getElementById('metric-requests').innerText = metrics.total_requests;
    document.getElementById('metric-tokens').innerText = metrics.total_tokens.toLocaleString();
    document.getElementById('metric-latency').innerText = metrics.avg_latency_seconds + 's';

    // 4. Fetch Workers
    const workersRes = await fetch('/api/pair/workers');
    const workers = await workersRes.json();
    document.getElementById('metric-workers').innerText = workers.filter(w => !w.revoked).length;

    const tbody = document.getElementById('workers-body');
    if (workers.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #64748b;">No workers paired yet.</td></tr>';
    } else {
      tbody.innerHTML = workers.map(w => `
        <tr>
          <td><code>${w.worker_id}</code></td>
          <td><strong>${w.name}</strong></td>
          <td>${w.os_info}</td>
          <td>${w.client_ip}</td>
          <td>${new Date(w.last_seen * 1000).toLocaleTimeString()}</td>
          <td><span style="color: ${w.revoked ? '#ef4444' : '#10b981'}; font-weight: bold;">${w.revoked ? 'REVOKED' : 'ACTIVE'}</span></td>
          <td>
            ${w.revoked ? '-' : `<button class="btn-sm" style="background: #dc2626; border: none;" onclick="revokeWorker('${w.worker_id}')">Revoke</button>`}
          </td>
        </tr>
      `).join('');
    }

    // 5. Update Recent Requests
    const reqBody = document.getElementById('requests-body');
    if (!metrics.recent_requests || metrics.recent_requests.length === 0) {
      reqBody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #64748b;">No requests recorded yet.</td></tr>';
    } else {
      reqBody.innerHTML = metrics.recent_requests.slice().reverse().map(r => `
        <tr>
          <td>${new Date(r.timestamp * 1000).toLocaleTimeString()}</td>
          <td>${r.client_id}</td>
          <td><code>${r.model}</code></td>
          <td>${r.input_tokens} / ${r.output_tokens}</td>
          <td>${r.duration_seconds}s</td>
          <td>${r.is_stream ? 'SSE' : 'JSON'}</td>
          <td><span style="color: ${r.status === 'SUCCESS' ? '#10b981' : '#ef4444'}; font-weight: bold;">${r.status}</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error("Failed to load dashboard data:", err);
  }
}

async function generateNewCode() {
  await fetch('/api/pair/generate', { method: 'POST' });
  refreshData();
}

async function revokeWorker(workerId) {
  if (confirm("Are you sure you want to revoke this worker? It will lose access immediately.")) {
    await fetch('/api/pair/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ worker_id: workerId })
    });
    refreshData();
  }
}

function copyCode() {
  navigator.clipboard.writeText(currentPairingCode);
  alert("Pairing code copied to clipboard: " + currentPairingCode);
}

function copyWorkerCmd() {
  const cmd = document.getElementById('worker-cmd').innerText;
  navigator.clipboard.writeText(cmd);
  alert("Worker installation command copied to clipboard!");
}

refreshData();
setInterval(refreshData, 10000);
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view():
    return HTMLResponse(content=DASHBOARD_HTML)
