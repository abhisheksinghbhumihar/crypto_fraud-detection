'use strict';

const CFG = {
  localApi: window.location.origin,
  pollInterval: 30000,
  timeoutMs: 5000,
};

const STATE = {
   refreshTimer: null,
   healthTimers: {},
   metrics: {
     total: 0,
     fraud: 0,
     approved: 0,
     responseMs: 0,
     activeAlerts: 0,
     transactions: [],
     alerts: [],
     evidence: [],
     daily: [],
   },
   allTables: [],
 };

const $ = (sel, ctx = document) => ctx.querySelector(sel);

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setText(id, value) {
  const el = $('#' + id);
  if (el) el.textContent = value;
}

function fmtMs(value) {
  const n = Number(value || 0);
  return n < 1000 ? Math.round(n) + 'ms' : (n / 1000).toFixed(2) + 's';
}

function pct(value) {
  const n = Number(value || 0);
  return (n > 1 ? n : n * 100).toFixed(1) + '%';
}

function riskPct(value) {
  const n = Number(value || 0);
  return Math.round(n > 1 ? n : n * 100) + '%';
}

function money(value) {
  return '$' + Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function time(value) {
  if (!value) return '-';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CFG.timeoutMs);
  const started = performance.now();
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    const ms = Math.round(performance.now() - started);
    let data;
    try {
      data = await res.json();
    } catch {
      data = { raw: await res.text() };
    }
    return { ok: res.ok, status: res.status, data, ms };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: { error: error.message },
      ms: Math.round(performance.now() - started),
    };
  } finally {
    clearTimeout(timer);
  }
}

async function firstWorking(candidates, options = {}) {
  let last = null;
  for (const url of candidates) {
    const result = await fetchJson(url, options);
    if (result.ok) return result;
    last = result;
  }
  return last || { ok: false, status: 0, data: {}, ms: 0 };
}

function api(path, options = {}) {
  return firstWorking([CFG.localApi + '/v1' + path, CFG.localApi + path], options);
}

function root(path) {
  return firstWorking([CFG.localApi + path]);
}

function normalizeTransactions(items) {
   if (!Array.isArray(items)) return [];
   return items.map((tx, index) => {
     const score = Number(tx.risk_score ?? tx.fraud_score ?? tx.score ?? 0);
     const isFraud = Boolean(tx.is_fraud ?? tx.is_fraudulent ?? tx.predicted_fraud ?? tx.fraud ?? score > 0.8);
     return {
       dataset: tx.dataset || tx.source || 'transactions',
       id: tx.transaction_id || tx.id || 'TX-' + String(index + 1).padStart(4, '0'),
       merchant: tx.merchant_name || tx.merchant || tx.merchant_id || 'Unknown Merchant',
       amount: Number(tx.amount || tx.converted_amount || 0),
       score,
       isFraud,
       decision: tx.decision || (isFraud ? 'BLOCK' : 'APPROVE'),
       evidenceHash: tx.evidence_hash || tx.hash || tx.evidence_cid || '',
       blockchainTx: tx.blockchain_tx || tx.tx_hash || '',
       createdAt: tx.created_at || tx.timestamp || tx.transaction_date || tx.date || '',
       details: tx,
     };
   });
 }

function normalizeAlerts(payload) {
  const items = Array.isArray(payload) ? payload : payload?.alerts || payload?.data || [];
  return items.map(item => ({
    id: item.alert_id || item.id || '-',
    symbol: item.symbol || '-',
    type: item.alert_type || item.type || '-',
    severity: String(item.severity ?? 'low'),
    description: item.description || '',
    status: item.status || (item.is_investigated ? 'resolved' : 'open'),
    createdAt: item.created_at || item.timestamp || '',
  }));
}

function evidenceFromTransactions(transactions) {
  return transactions
    .filter(tx => tx.evidenceHash || tx.blockchainTx)
    .map(tx => ({
      id: tx.id,
      evidenceHash: tx.evidenceHash,
      blockchainTx: tx.blockchainTx,
      verified: Boolean(tx.evidenceHash || tx.blockchainTx),
      amount: tx.amount,
      merchant: tx.merchant,
      decision: tx.decision,
      score: tx.score,
      details: tx.details || tx,
    }));
}

function updateKpis() {
  setText('kpi-tx-today', STATE.metrics.total.toLocaleString());
  setText('kpi-fraud-rate', pct(STATE.metrics.total ? STATE.metrics.fraud / STATE.metrics.total : 0));
  setText('kpi-avg-time', fmtMs(STATE.metrics.responseMs));
  setText('kpi-active-alerts', STATE.metrics.activeAlerts.toLocaleString());
  setText('last-updated', new Date().toLocaleTimeString('en-US', { hour12: false }));
}

function renderTransactions() {
  const wrap = $('#tx-table-wrap');
  if (!wrap) return;
  const rows = STATE.metrics.transactions.slice(0, 12).map(tx => {
    const riskClass = tx.score > 0.8 ? 'badge-high' : tx.score > 0.45 ? 'badge-med' : 'badge-low';
    const decisionClass = tx.decision === 'BLOCK' ? 'badge-high' : tx.decision === 'REVIEW' ? 'badge-med' : 'badge-low';
    const fraudClass = tx.isFraud ? 'badge-high' : 'badge-low';
    const fraudLabel = tx.isFraud ? 'FRAUD' : 'LEGITIMATE';
    const hash = tx.evidenceHash ? '<code title="' + escapeHtml(tx.evidenceHash) + '">' + escapeHtml(tx.evidenceHash.slice(0, 18)) + '...</code>' : '-';
    return '<tr>' +
      '<td><span class="badge badge-med">' + escapeHtml(tx.dataset) + '</span></td>' +
      '<td><code>' + escapeHtml(tx.id) + '</code></td>' +
      '<td>' + escapeHtml(tx.merchant) + '</td>' +
      '<td>' + money(tx.amount) + '</td>' +
      '<td><span class="badge ' + riskClass + '">' + riskPct(tx.score) + '</span></td>' +
      '<td><span class="badge ' + fraudClass + '">' + fraudLabel + '</span></td>' +
      '<td><span class="badge ' + decisionClass + '">' + escapeHtml(tx.decision) + '</span></td>' +
      '<td>' + hash + '</td>' +
      '</tr>';
  }).join('');
  wrap.innerHTML = rows
    ? '<table class="data-table"><thead><tr><th>Dataset</th><th>Transaction ID</th><th>Merchant</th><th>Amount</th><th>Risk Score</th><th>Fraud Status</th><th>Decision</th><th>Evidence Hash</th></tr></thead><tbody>' + rows + '</tbody></table>'
    : '<div class="empty-state">No predictions yet. Run a fraud check above to populate this table.</div>';
}

function renderAlerts() {
  const wrap = $('#alert-table-wrap');
  if (!wrap) return;
  const rows = STATE.metrics.alerts.slice(0, 12).map((alert, index) => {
    const sev = alert.severity.toLowerCase();
    const sevClass = sev === 'critical' || sev === 'high' || sev === '3' ? 'badge-high' : sev === 'medium' || sev === '2' ? 'badge-med' : 'badge-low';
    return '<tr>' +
      '<td><code>' + escapeHtml(alert.id) + '</code></td>' +
      '<td>' + escapeHtml(alert.symbol) + '</td>' +
      '<td>' + escapeHtml(alert.type) + '</td>' +
      '<td><span class="badge ' + sevClass + '">' + escapeHtml(alert.severity) + '</span></td>' +
      '<td><span class="badge ' + (String(alert.status).toLowerCase() === 'open' ? 'badge-high' : 'badge-low') + '">' + escapeHtml(alert.status) + '</span></td>' +
      '<td class="ts-cell">' + escapeHtml(time(alert.createdAt)) + '</td>' +
      '<td><button class="btn btn-sm" onclick="viewAlert(' + index + ')">View</button></td>' +
      '</tr>';
  }).join('');
  wrap.innerHTML = rows
    ? '<table class="data-table"><thead><tr><th>ID</th><th>Symbol</th><th>Alert Type</th><th>Severity</th><th>Status</th><th>Timestamp</th><th>Action</th></tr></thead><tbody>' + rows + '</tbody></table>'
    : '<div class="empty-state">No alerts returned from /v1/alerts/list.</div>';
}

function viewAlert(index) {
  const alert = STATE.metrics.alerts[index];
  const target = $('#alert-detail');
  if (alert && target) {
    target.innerHTML = '<pre class="resp-pre evidence-detail">' + escapeHtml(JSON.stringify(alert, null, 2)) + '</pre>';
  }
}

async function showEvidenceDetails(index) {
  const item = STATE.metrics.evidence[index];
  const target = $('#verify-status');
  if (!item || !target) return;
  target.innerHTML = '<div class="resp-loading"><span class="pulse-ring"></span>Verifying evidence...</div>';
  const result = item.evidenceHash ? await api('/evidence/verify/' + encodeURIComponent(item.evidenceHash)) : { ok: false, data: item.details };
  const payload = result.ok ? result.data : item.details;
  target.innerHTML =
    '<div class="verify-result ' + (result.ok ? 'v-ok' : 'v-fail') + '">' + (result.ok ? 'Evidence verified' : 'Evidence details from transaction response') + '</div>' +
    '<pre class="resp-pre evidence-detail">' + escapeHtml(JSON.stringify(payload, null, 2)) + '</pre>';
}

function renderEvidence() {
  const wrap = $('#bc-evidence-list');
  if (!wrap) return;
  const rows = STATE.metrics.evidence.slice(0, 8).map((item, index) => (
    '<div class="chain-entry">' +
      '<span class="chain-icon v-ok">&#10003;</span>' +
      '<div class="chain-info">' +
        '<code class="chain-hash" title="' + escapeHtml(item.evidenceHash) + '">' + escapeHtml(item.evidenceHash || '-') + '</code>' +
        '<span class="chain-context">Amount: ' + money(item.amount) + ' | Merchant: ' + escapeHtml(item.merchant) + ' | Decision: ' + escapeHtml(item.decision) + '</span>' +
        '<span class="chain-time">TX: ' + escapeHtml(item.blockchainTx || 'local evidence file') + '</span>' +
      '</div>' +
      '<span class="chain-badge v-ok">Anchored</span>' +
      '<button class="btn btn-sm" onclick="showEvidenceDetails(' + index + ')">View Full Evidence</button>' +
    '</div>'
  )).join('');
  wrap.innerHTML = rows || '<div class="empty-state">No evidence hashes yet. Fraudulent predictions will appear here.</div>';
  const firstHash = STATE.metrics.evidence[0]?.evidenceHash;
  const verifyInput = $('#bc-hash-verify');
  if (firstHash && verifyInput && !verifyInput.value) verifyInput.value = firstHash;
}

function renderTrend() {
  const wrap = $('#chart-trend');
  if (!wrap) return;
  const data = STATE.metrics.daily.slice(-7);
  if (!data.length) {
    wrap.innerHTML = '<div class="empty-state">No daily trend data returned from /v1/stats/daily.</div>';
    return;
  }
  const pointsData = data.map(row => {
    const total = Number(row.total_count ?? row.total ?? row.predictions ?? 0);
    const fraud = Number(row.fraud_count ?? row.frauds ?? row.fraud ?? 0);
    const rate = Number(row.fraud_rate ?? (total ? fraud / total : 0));
    return { date: row.date || '', rate };
  });
  const w = 760;
  const h = 230;
  const max = Math.max(...pointsData.map(p => p.rate), 0.01);
  const points = pointsData.map((p, index) => {
    const x = 42 + (index / Math.max(pointsData.length - 1, 1)) * (w - 84);
    const y = h - 38 - (p.rate / max) * (h - 76);
    return x + ',' + y;
  }).join(' ');
  const pointMarks = pointsData.map((p, index) => {
    const x = 42 + (index / Math.max(pointsData.length - 1, 1)) * (w - 84);
    const y = h - 38 - (p.rate / max) * (h - 76);
    return '<circle cx="' + x + '" cy="' + y + '" r="5" /><text class="trend-value" x="' + x + '" y="' + (y - 10) + '" text-anchor="middle">' + pct(p.rate) + '</text>';
  }).join('');
  const labels = pointsData.map((p, index) => {
    const x = 42 + (index / Math.max(pointsData.length - 1, 1)) * (w - 84);
    return '<text x="' + x + '" y="218" text-anchor="middle">' + escapeHtml(String(p.date).slice(5)) + '</text>';
  }).join('');
  wrap.innerHTML = '<svg viewBox="0 0 ' + w + ' ' + h + '" class="spark trend-chart">' +
    '<text class="axis-title" x="14" y="18">Fraud Rate (%)</text>' +
    '<text x="14" y="36">' + pct(max) + '</text>' +
    '<text x="20" y="194">0%</text>' +
    '<line x1="42" y1="192" x2="718" y2="192" />' +
    '<line x1="42" y1="28" x2="42" y2="192" />' +
    '<polyline points="' + points + '" />' +
    pointMarks +
    labels +
    '</svg>';
}

function merchantLabel(value) {
  const raw = String(value || '').toLowerCase();
  if (raw.includes('wire') || raw.includes('bank')) return 'Wire Transfer';
  if (raw.includes('crypto') || raw.includes('exchange')) return 'Crypto Exchange';
  if (raw.includes('unknown')) return 'Unknown Merchant';
  return value || 'Other';
}

function renderMerchantBars() {
  const wrap = $('#merchant-chart');
  if (!wrap) return;
  const buckets = {};
  STATE.metrics.transactions.forEach(tx => {
    if (tx.decision === 'BLOCK' || tx.score > 0.8) {
      const label = merchantLabel(tx.merchant);
      buckets[label] = (buckets[label] || 0) + 1;
    }
  });
  const entries = Object.entries(buckets).sort((a, b) => b[1] - a[1]).slice(0, 6);
  if (!entries.length) {
    wrap.innerHTML = '<div class="empty-state">No blocked transactions by merchant yet.</div>';
    return;
  }
  const max = Math.max(...entries.map(([, count]) => count), 1);
  wrap.innerHTML = entries.map(([name, count]) => (
    '<div class="bar-row">' +
      '<div class="bar-meta"><span>' + escapeHtml(name) + '</span><strong>' + count + '</strong></div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' + Math.round((count / max) * 100) + '%"></div></div>' +
    '</div>'
  )).join('');
}

async function runVerifyEvidence() {
  const hash = ($('#bc-hash-verify')?.value || '').trim();
  const status = $('#verify-status');
  if (!hash) {
    if (status) status.innerHTML = '<div class="verify-result v-fail">Enter an evidence hash</div>';
    return;
  }
  const result = await api('/evidence/verify/' + encodeURIComponent(hash));
  const ok = result.ok && (result.data.verified || result.data.exists);
  if (status) {
    status.innerHTML = '<div class="verify-result ' + (ok ? 'v-ok' : 'v-fail') + '">' + (ok ? 'Evidence verified' : 'Evidence not verified') + '</div>' +
      '<pre class="resp-pre evidence-detail">' + escapeHtml(JSON.stringify(result.data, null, 2)) + '</pre>';
  }
}

function applyStats(data) {
  const total = Number(data.total_predictions ?? data.total_transactions ?? 0);
  const fraud = Number(data.fraud_count ?? data.block_count ?? 0);
  STATE.metrics.total = total;
  STATE.metrics.fraud = fraud;
  STATE.metrics.approved = Number(data.approve_count ?? Math.max(total - fraud, 0));
  STATE.metrics.responseMs = Number(data.avg_response_time_ms ?? 0);
  STATE.metrics.transactions = normalizeTransactions(data.transactions || data.recent_transactions || data.predictions || []);
  STATE.metrics.evidence = evidenceFromTransactions(STATE.metrics.transactions);
}

async function refreshDashboard() {
   const stats = await api('/stats/overview');
   if (stats.ok) applyStats(stats.data);

   const tables = await api('/stats/tables');
   if (tables.ok && tables.data?.data) {
     const allRows = [];
     const data = tables.data.data;
     for (const tableName of Object.keys(data)) {
       for (const row of data[tableName].rows) {
         if (!row.dataset) row.dataset = tableName;
         allRows.push(row);
       }
     }
     STATE.allTables = allRows;
     STATE.metrics.transactions = normalizeTransactions(allRows);
     STATE.metrics.evidence = evidenceFromTransactions(STATE.metrics.transactions);
   }

   const alerts = await api('/alerts/list');
   if (alerts.ok) {
     STATE.metrics.alerts = normalizeAlerts(alerts.data);
     STATE.metrics.activeAlerts = STATE.metrics.alerts.filter(a => String(a.status).toLowerCase() === 'open').length;
   }

   const daily = await api('/stats/daily');
   if (daily.ok) STATE.metrics.daily = daily.data.data || daily.data.daily || daily.data.results || [];

   updateKpis();
   renderTrend();
   renderAlerts();
   renderTransactions();
   renderEvidence();
   renderMerchantBars();
 }

function setHealth(id, ok) {
  const dot = $('#' + id);
  if (dot) dot.className = 'health-dot ' + (ok ? 'health-up' : 'health-down');
}

function startHealthChecks() {
  const checks = {
    'hd-api': () => root('/health'),
    'hd-fraud': () => api('/fraud/health'),
    'hd-ks': () => api('/keystroke/health'),
    'hd-mouse': () => api('/mouse/health'),
    'hd-alerts': () => api('/alerts/health'),
    'hd-payment': () => api('/payment/health'),
    'hd-evidence': () => api('/evidence/verify/demo'),
  };
  Object.entries(checks).forEach(([id, fn]) => {
    const run = async () => {
      const result = await fn();
      setHealth(id, result.ok);
    };
    run();
    STATE.healthTimers[id] = setInterval(run, CFG.pollInterval);
  });
}

function renderPredictionResult(result, request, ms) {
  const target = $('#predict-result');
  if (!target) return;
  const score = Number(result.risk_score || 0);
  const cls = result.is_fraud ? 'v-fail' : 'v-ok';
  target.innerHTML =
    '<div class="predict-output ' + cls + '">' +
      '<strong>' + escapeHtml(result.decision || (result.is_fraud ? 'BLOCK' : 'APPROVE')) + '</strong>' +
      '<span>Risk score ' + riskPct(score) + ' in ' + fmtMs(ms) + '</span>' +
      (result.evidence_hash ? '<code>' + escapeHtml(result.evidence_hash) + '</code>' : '') +
    '</div>' +
    '<pre class="resp-pre evidence-detail">' + escapeHtml(JSON.stringify({ request, response: result }, null, 2)) + '</pre>';
}

async function createAlertForFraud(request, result) {
  if (!result.is_fraud) return;
  await api('/alerts/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      symbol: request.merchant_id,
      alert_type: 'fraud_prediction',
      severity: 3,
      description: 'Blocked transaction ' + request.transaction_id + ' with risk score ' + riskPct(result.risk_score),
    }),
  });
}

async function submitPrediction(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const request = {
    transaction_id: ($('#tx-id')?.value || 'TXN_' + Date.now()).trim(),
    amount: Number($('#tx-amount')?.value || 0),
    user_id: ($('#tx-user')?.value || '').trim(),
    merchant_id: ($('#tx-merchant')?.value || '').trim(),
  };
  if (button) button.disabled = true;
  const result = await api('/fraud/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (button) button.disabled = false;

  if (!result.ok) {
    const target = $('#predict-result');
    if (target) {
      target.innerHTML = '<div class="verify-result v-fail">Prediction failed</div><pre class="resp-pre evidence-detail">' + escapeHtml(JSON.stringify(result.data, null, 2)) + '</pre>';
    }
    return;
  }

  renderPredictionResult(result.data, request, result.ms);
  await createAlertForFraud(request, result.data);
  await refreshDashboard();
}

function initDashboard() {
  $('#predict-form')?.addEventListener('submit', submitPrediction);
  startHealthChecks();
  refreshDashboard();
  clearInterval(STATE.refreshTimer);
  STATE.refreshTimer = setInterval(refreshDashboard, CFG.pollInterval);
}

window.runVerifyEvidence = runVerifyEvidence;
window.showEvidenceDetails = showEvidenceDetails;
window.viewAlert = viewAlert;
window.refreshDashboard = refreshDashboard;

document.addEventListener('DOMContentLoaded', initDashboard);
