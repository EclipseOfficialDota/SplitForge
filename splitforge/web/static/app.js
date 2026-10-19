"use strict";
const $ = (selector, root = document) => root.querySelector(selector);
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const e = escapeHTML;
const pages = {
  overview: "Overview",
  router: "App router",
  profiles: "Tunnel profiles",
  security: "Security & DNS",
  cores: "Core installer",
  logs: "Live logs",
  help: "Quick start",
  traffic: "Traffic & quotas",
};
let state = null,
  csrf = "",
  authenticated = false,
  page = "overview",
  timer,
  search = "",
  helpLanguage = window.SplitForgeLocale.language,
  fileDraft = {},
  fileMode = "app";
let seenJobs = new Map(),
  toastTimer;

async function api(path, body) {
  const options = { credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    options.method = "POST";
    options.headers = {
      "Content-Type": "application/json",
      "X-SplitForge-CSRF": csrf,
    };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && authenticated) lockScreen();
    throw new Error(result.error || `Request failed (${response.status})`);
  }
  return result;
}

function toast(message, error = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.hidden = true), error ? 10000 : 5500);
}

function bytes(value) {
  let n = Number(value) || 0;
  for (const unit of ["B", "KiB", "MiB", "GiB", "TiB"]) {
    if (n < 1024 || unit === "TiB")
      return `${n.toFixed(unit === "B" ? 0 : 1)} ${unit}`;
    n /= 1024;
  }
}
function flag(country) {
  return /^[A-Z]{2}$/.test(country)
    ? [...country]
        .map((c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
        .join("")
    : "◉";
}
function badge(active, yes = "ONLINE", no = "STOPPED") {
  return `<span class="badge ${active ? "" : "offline"}"><i class="dot ${active ? "green" : ""}"></i>${active ? yes : no}</span>`;
}
function button(label, action, id = "", kind = "", disabled = false) {
  return `<button type="button" class="button small ${kind}" data-action="${action}" data-id="${e(id)}" ${disabled ? "disabled" : ""}>${label}</button>`;
}
function profileName(id) {
  return state.profiles.find((p) => p.id === id)?.name || "Direct server";
}
function route(app, interactive = true) {
  const label = `<span>${app.profile_id ? "↗" : "◌"}</span>${app.profile_id ? `<span data-no-translate>${e(profileName(app.profile_id))}</span>` : e(profileName(app.profile_id))}${interactive ? "<span>⌄</span>" : ""}`;
  const current = interactive
    ? `<button type="button" class="route-pill ${app.profile_id ? "" : "direct"}" data-action="route" data-id="${e(app.id)}">${label}</button>`
    : `<span class="route-pill ${app.profile_id ? "" : "direct"}">${label}</span>`;
  return (
    current +
    (app.failover_enabled
      ? `<div class="field-hint">Auto: ${e(profileName(app.primary_profile_id))} → ${e(profileName(app.backup_profile_id))}<br>Failover restarts this app</div>`
      : "")
  );
}
function appIdentity(app) {
  const shell = app.name.endsWith(".sh"),
    service = !!app.service;
  return `<div class="identity"><span class="avatar ${shell ? "amber" : service ? "teal" : ""}">${service ? "svc" : shell ? "sh" : "py"}</span><div><strong>${e(app.name)}</strong><small title="${e(app.service || app.command)}">${e(app.service || app.command)}</small></div></div>`;
}
function header(title, subtitle, actions = "", eyebrow = "CONTROL PLANE") {
  return `<div class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${subtitle}</p></div>${actions ? `<div class="heading-actions">${actions}</div>` : ""}</div>`;
}
function empty(title, description, action = "") {
  return `<div class="empty"><strong>${title}</strong><p>${description}</p>${action}</div>`;
}
function operations() {
  return `<div class="operations" id="operation-list">${state.jobs
    .slice(0, 6)
    .map(
      (job) =>
        `<div class="operation ${e(job.state)}"><strong>${e(job.action)} · ${e(job.state.toUpperCase())}</strong>${job.progress ? `<progress class="download-progress" max="100" ${Number.isFinite(job.progress.percent) ? `value="${Math.max(0, Math.min(100, job.progress.percent))}"` : ""} aria-label="Download progress"></progress>` : ""}<p>${e(job.error || job.progress?.phase || (job.state === "success" ? "Operation completed." : "Working…"))}</p><details><summary>Technical details</summary><pre>${e([job.error, ...job.messages].filter(Boolean).join("\n"))}</pre></details></div>`,
    )
    .join("")}${state.jobs
    .filter(
      (job) =>
        job.action === "backup.export" &&
        job.result?.download &&
        job.state === "success",
    )
    .map((job) =>
      button(
        "Download encrypted backup",
        "backup-download",
        job.result.download,
      ),
    )
    .join("")}</div>`;
}

function overview() {
  const active = state.profiles.filter((p) => p.active).length,
    running = state.apps.filter((a) => a.running).length;
  const transfer = state.profiles.reduce(
    (sum, p) => sum + (p.bandwidth?.rx || 0) + (p.bandwidth?.tx || 0),
    0,
  );
  return (
    header(
      "Your apps. <span>Your network.</span>",
      "Every workload, exactly where it belongs. Your host keeps its existing route.",
      `<button class="button" data-action="add-app">＋ Register app</button><button class="button primary" data-action="add-profile">＋ Import profile</button>`,
      "WORKSPACE / OVERVIEW",
    ) +
    `<div class="metrics">
      <div class="metric"><div class="metric-label">ACTIVE TUNNELS <span>◎</span></div><div class="metric-value green-text">${active} <span class="denominator">/ ${state.profiles.length}</span></div><div class="metric-note">${state.profiles.length - active} stopped · lifecycle status</div></div>
      <div class="metric"><div class="metric-label">RUNNING APPS <span>⇄</span></div><div class="metric-value">${running.toString().padStart(2, "0")} <span class="denominator">/ ${state.apps.length}</span></div><div class="metric-note">${state.apps.filter((a) => a.profile_id).length} assigned to a tunnel</div></div>
      <div class="metric"><div class="metric-label">TUNNEL TRANSFER <span>↗</span></div><div class="metric-value teal-text">${bytes(transfer)}</div><div class="metric-note">Shared interface RX + TX</div></div>
      <div class="metric"><div class="metric-label">HOST MAIN ROUTE <span>◇</span></div><div class="metric-value ${state.route_unchanged ? "green-text" : ""}">${state.route_unchanged ? "Intact" : "Changed"}</div><div class="metric-note">Compared to panel startup</div></div>
    </div>
    <section class="panel"><div class="panel-header"><h2><span>◎</span> Tunnel health</h2><div class="meta">LIFECYCLE + LAST EGRESS CHECK</div><button class="text-button" data-page="profiles">Manage tunnels ↗</button></div>
    ${state.profiles.length ? `<div class="table-wrap"><table><thead><tr><th>TUNNEL PROFILE</th><th>PROTOCOL</th><th>LAST EXIT IP</th><th>HTTPS ELAPSED</th><th>STATE</th></tr></thead><tbody>${state.profiles.map((p) => `<tr><td><div class="identity"><span class="avatar teal">${flag(p.country)}</span><div><strong>${e(p.name)}</strong><small>ns-${e(p.id)}</small></div></div></td><td><span class="protocol">${e(p.protocol.toUpperCase())}</span></td><td class="mono muted">${e(p.exit_ip || "—")}</td><td><span class="latency">${p.latency_ms !== null ? `<span class="signal" aria-hidden="true"><i></i><i></i><i></i><i></i></span>${Math.round(p.latency_ms)} ms` : "Not tested"}</span></td><td>${badge(p.active)}</td></tr>`).join("")}</tbody></table></div>` : empty("No tunnels yet", "Import a provider profile to build your first isolated network.", button("＋ Import profile", "add-profile", "", "primary"))}
    <div class="panel-foot"><span class="dot green"></span> HTTPS timings include DNS and retries. Test egress for a fresh measurement.</div></section>
    <section class="panel"><div class="panel-header"><h2><span>⇄</span> Application routes</h2><button class="text-button" data-page="router">Open app router ↗</button></div>${appTable(state.apps.slice(0, 5), false)}<div class="panel-foot">↳ &nbsp; Route changes restart the managed application. Existing connections close.</div></section>`
  );
}

function appTable(apps, actions = true) {
  if (!apps.length)
    return empty(
      "No matching workloads",
      "Register a script, executable or existing systemd service.",
      button("＋ Register app", "add-app", "", "primary"),
    );
  return `<div class="table-wrap"><table><thead><tr><th>APPLICATION / SCRIPT</th><th>ASSIGNED ROUTE</th><th>USER</th><th>STATE</th>${actions ? "<th>CONTROLS</th>" : ""}</tr></thead><tbody>${apps.map((app) => `<tr><td>${appIdentity(app)}${appProbe(app)}</td><td>${route(app)}</td><td class="mono muted">${e(app.user)}</td><td>${badge(app.running, "RUNNING")}</td>${actions ? `<td><div class="row-actions">${button(app.running ? "Stop" : "Start", "app-toggle", app.id, "", state.busy)}${button("Test route", "app.test", app.id, "", state.busy || !app.running)}${button("Remove", "app-remove", app.id, "danger", state.busy)}</div></td>` : ""}</tr>`).join("")}</tbody></table></div>`;
}
function appProbe(app) {
  const result = state.app_tests?.[app.id];
  if (!result) return "";
  return `<div class="field-hint mono">Last process-route test: ${e(new Date(result.checked_at * 1000).toLocaleString())}<br>IP ${e(result.exit_ip)} · DNS ${e(result.dns_servers.join(", "))}<br>HTTPS connected · PID ${e(result.pid)} · ${e(Math.round(result.latency_ms))} ms<br>Route at test: ${e(profileName(result.profile_id))}</div>`;
}
function routerPage() {
  return (
    header(
      "App <span>router.</span>",
      "One application. One route. Pick the tunnel each workload uses.",
      `<button class="button primary" data-action="add-app">＋ Register app</button>`,
      "WORKSPACE / APP ROUTER",
    ) +
    `<div class="toolbar"><input class="search" id="search" type="search" placeholder="Search apps, commands or users…" aria-label="Search applications" value="${e(search)}"><small>${state.apps.length} registered workloads</small></div><section class="panel">${appTable(state.apps.filter((a) => `${a.name} ${a.command} ${a.user}`.toLowerCase().includes(search.toLowerCase())))}</section><div class="notice green">◇ Root workloads are supported with capabilities removed. Run trusted programs. A network namespace is not a complete filesystem sandbox.</div>`
  );
}
function profilesPage() {
  const profiles = state.profiles.filter((p) =>
    `${p.name} ${p.protocol}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    header(
      "Tunnel <span>profiles.</span>",
      "Multiple protocols. Separate namespaces. A single control plane.",
      `<button class="button primary" data-action="add-profile">＋ Import profile</button>`,
      "WORKSPACE / TUNNELS",
    ) +
    `<div class="toolbar"><input class="search" id="search" type="search" placeholder="Search profiles or protocols…" aria-label="Search profiles" value="${e(search)}"><small>Active does not mean freshly tested</small></div>` +
    (profiles.length
      ? `<div class="profile-grid">${profiles.map((p) => `<article class="profile-card"><div class="profile-card-top"><span class="protocol">${e(p.protocol.toUpperCase())}</span>${badge(p.active)}</div><h2>${flag(p.country)} ${e(p.name)}</h2><div class="mono">ns-${e(p.id)}</div><dl class="profile-details"><div><dt>Last exit address</dt><dd>${e(p.exit_ip || "Not tested")}</dd></div><div><dt>HTTPS elapsed</dt><dd>${p.latency_ms === null ? "—" : `${Math.round(p.latency_ms)} ms`}</dd></div><div><dt>Received</dt><dd>${bytes(p.bandwidth?.rx)}</dd></div><div><dt>Sent</dt><dd>${bytes(p.bandwidth?.tx)}</dd></div></dl><div class="row-actions">${button(p.active ? "Stop" : "Start", p.active ? "profile.stop" : "profile.start", p.id, "", state.busy)}${button("Test egress", "profile.test", p.id, "", state.busy || !p.active)}${button("Edit source", "profile-edit", p.id, "", state.busy || p.active)}${button("Remove", "profile-remove", p.id, "danger", state.busy)}</div></article>`).join("")}</div>`
      : empty(
          "No matching profiles",
          "Import a URI or a server-side configuration file.",
          button("＋ Import profile", "add-profile", "", "primary"),
        ))
  );
}
function profileOptions(selected = "") {
  return `<option value="">Choose a profile…</option>${state.profiles.map((p) => `<option value="${e(p.id)}" ${selected === p.id ? "selected" : ""}>${e(p.name)} · ${p.active ? "active" : "stopped"}</option>`).join("")}`;
}
function securityPage() {
  return (
    header(
      "Security <span>& DNS.</span>",
      "Fail closed. Resolve privately. Keep the host's existing network path.",
      "",
      "WORKSPACE / GUARDS",
    ) +
    `<div class="two-column"><section class="panel"><div class="panel-header"><h2><span>◇</span> Namespace policy</h2><span class="badge">ENFORCED</span></div><ul class="guard-list"><li><span>✓</span><div><strong>Kill switch enabled</strong><p>Managed tunnel namespaces deny fallback through the host underlay.</p></div></li><li><span>✓</span><div><strong>Verified DNS-over-HTTPS</strong><p>A local stub forwards resolver requests through the assigned tunnel.</p></div></li><li><span>✓</span><div><strong>IPv6 disabled in managed namespaces</strong><p>This release uses an IPv4 data plane.</p></div></li><li><span>✓</span><div><strong>Shared profile, shared guard</strong><p>Apps in one namespace cannot disable its protection independently.</p></div></li></ul></section>
    <section class="panel"><div class="panel-header"><h2><span>↗</span> Encrypted DNS settings</h2></div><form id="dns-form" class="form-panel stack"><div><label for="dns-profile">Profile</label><select id="dns-profile" name="id" required>${profileOptions()}</select></div><div><label for="dns-url">DNS-over-HTTPS URL</label><input id="dns-url" name="url" type="url" value="https://cloudflare-dns.com/dns-query" required></div><div><label for="dns-bootstrap">Bootstrap IPv4</label><input id="dns-bootstrap" name="bootstrap" value="1.1.1.1" required><p class="field-hint">Must serve this hostname with a valid TLS certificate.</p></div><div class="notice">Stop the profile before editing DNS. Dependent workloads may stop with it.</div><button class="button primary" type="submit">Save encrypted DNS</button></form></section></div>` +
    backupPanel()
  );
}
function backupPanel() {
  return `<section class="panel"><div class="panel-header"><h2>Encrypted backup & recovery</h2></div><div class="form-panel two-column"><form id="backup-export-form" class="stack"><h3>Export configuration</h3><p>Includes profiles, app routes, DNS, failover and web settings. Keep your password separately; it cannot be recovered.</p><label for="backup-password">Backup password (12+ characters)</label><input id="backup-password" name="password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required><label for="backup-confirm">Confirm password</label><input id="backup-confirm" name="confirmation" type="password" minlength="12" maxlength="1024" autocomplete="new-password" required><button class="button primary" type="submit">Create encrypted backup</button></form><form id="backup-restore-form" class="stack"><h3>Restore configuration</h3><p>Replaces current registrations and stops workloads. Imported commands remain stopped. Current web access is retained; use the CLI to apply saved web settings or restart trusted workloads.</p><label for="backup-file">Encrypted .sfb file</label><input id="backup-file" name="archive" type="file" accept=".sfb" required><label for="restore-password">Backup password</label><input id="restore-password" name="password" type="password" autocomplete="current-password" required><label class="check-inline"><input type="checkbox" name="confirm" required> I trust this backup and accept replacement of current registrations</label><button class="button danger" type="submit">Restore and keep workloads stopped</button></form></div><div class="panel-foot">Version rollback: splitforge rollback --list / splitforge rollback --backup ID. Updates retain a private installation snapshot on the server.</div></section>${operations()}`;
}
function coresPage() {
  return (
    header(
      "Your <span>core toolkit.</span>",
      "Install only what your protocols need. Required helpers are included automatically.",
      "",
      "WORKSPACE / DEPENDENCIES",
    ) +
    `<form id="cores-form"><div class="component-list">${state.components.map((c) => `<label class="component"><input type="checkbox" name="core" value="${e(c.id)}"><span><strong>${e(c.id)}</strong><small>${e(c.description.split(" / ")[0])}</small><span class="badge ${c.installed ? "" : "offline"}">${c.installed ? "✓ INSTALLED · WILL SKIP" : "↓ NOT INSTALLED"}</span></span></label>`).join("")}</div><div class="notice">Binary downloads verify SHA-256. DNSTT builds from pinned source and can take several minutes. Installed tools are skipped; profiles are never started by installation.</div><p id="core-plan" class="field-hint">Select components to review the plan.</p><div class="heading-actions"><button type="submit" class="button primary" id="install-cores">↓ Install selected cores</button></div></form>${operations()}`
  );
}
function trafficGraph(history) {
  const points = [];
  for (let index = 1; index < history.length; index++) {
    const previous = history[index - 1],
      current = history[index],
      seconds = current[0] - previous[0];
    if (seconds > 0)
      points.push([
        Math.max(0, current[1] - previous[1]) / seconds,
        Math.max(0, current[2] - previous[2]) / seconds,
      ]);
  }
  if (points.length < 2)
    return '<div class="traffic-empty">Collecting rate history…</div>';
  const peak = Math.max(1, ...points.flat()),
    width = 400,
    height = 90;
  const line = (column) =>
    points
      .map(
        (point, index) =>
          `${((index / (points.length - 1)) * width).toFixed(2)},${(height - (point[column] / peak) * (height - 8)).toFixed(2)}`,
      )
      .join(" ");
  return `<svg class="traffic-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Receive and send rate history"><path class="traffic-grid" d="M0 30H400M0 60H400M0 89H400"/><polyline class="traffic-rx" points="${line(0)}"/><polyline class="traffic-tx" points="${line(1)}"/></svg><div class="traffic-legend"><span class="green-text">↓ Received</span><span class="teal-text">↑ Sent</span><span>Peak ${e(bytes(peak))}/s</span></div>`;
}
function trafficCard(kind, target) {
  const source = state.traffic?.[kind]?.[target.id],
    row = source ? { ...source } : null,
    supported = Boolean(row?.supported),
    quota = row?.quota;
  const used = supported ? Math.max(0, row.rx + row.tx - row.baseline) : 0;
  const percent = quota ? Math.min(100, (used / quota) * 100) : 0;
  if (row)
    row.available =
      row.available &&
      (kind === "apps" ? target.running : target.active) &&
      Date.now() / 1000 - row.updated < 20;
  return `<article class="profile-card traffic-card"><div class="profile-card-top"><span class="protocol">${kind === "apps" ? "APPLICATION" : "TUNNEL"}</span><span class="badge ${row?.blocked ? "offline" : ""}">${row?.blocked ? "BUDGET BLOCKED" : row?.available ? "COUNTERS LIVE" : "LAST READING"}</span></div><h2 data-no-translate>${e(target.name)}</h2><p class="field-hint">${kind === "apps" ? "Independent service kernel counters" : "Shared tunnel interface counters"}</p>${supported ? `<div class="traffic-total mono">${bytes(row.rx + row.tx)}</div>${trafficGraph(row.history)}<dl class="profile-details"><div><dt>Received</dt><dd>${bytes(row.rx)}</dd></div><div><dt>Sent</dt><dd>${bytes(row.tx)}</dd></div><div><dt>Budget usage</dt><dd>${bytes(used)} / ${quota ? bytes(quota) : "Unlimited"}</dd></div></dl>${quota ? `<progress class="download-progress" max="100" value="${percent.toFixed(2)}" aria-label="Traffic budget usage"></progress>` : ""}${row.warned ? '<div class="notice">Traffic warning threshold reached</div>' : ""}` : '<div class="traffic-empty">No verified counter reading yet</div>'}${row?.error ? `<p class="field-hint">${e(row.error)}</p>` : ""}<div class="row-actions">${button("Set budget", kind === "apps" ? "quota-app" : "quota-profile", target.id, "", state.busy || (!supported && !quota))}</div>${row?.updated ? `<small class="field-hint">Last sampled ${e(new Date(row.updated * 1000).toLocaleString())}</small>` : ""}</article>`;
}
function trafficPage() {
  const data = state.traffic || { apps: {}, profiles: {}, events: [] };
  return (
    header(
      "Traffic <span>& budgets.</span>",
      "Each application has its own counter. Follow tunnel usage and set a budget.",
      button("Enable collector", "traffic-enable", "", "primary"),
      "WORKSPACE / TRAFFIC",
    ) +
    badge(data.collector_active, "COLLECTOR ACTIVE", "COLLECTOR STOPPED") +
    '<div class="notice">Budgets stop workloads at the next sample (normally every 5 seconds). Bursts can exceed the limit before stopping. App counters include local IP traffic; tunnel counters include shared DNS and protocol traffic.</div>' +
    (data.error ? `<div class="notice">${e(data.error)}</div>` : "") +
    '<h2>Application traffic</h2><div class="profile-grid">' +
    state.apps.map((app) => trafficCard("apps", app)).join("") +
    "</div>" +
    '<h2>Tunnel traffic</h2><div class="profile-grid">' +
    state.profiles.map((profile) => trafficCard("profiles", profile)).join("") +
    "</div>" +
    `<section class="panel"><div class="panel-header"><h2>Budget alerts</h2></div><div class="form-panel">${
      data.events?.length
        ? data.events
            .slice()
            .reverse()
            .map(
              (event) =>
                `<p><span class="badge offline">${e(event.level)}</span> <span data-no-translate>${e((event.kind === "apps" ? state.apps : state.profiles).find((target) => target.id === event.id)?.name || event.id)}</span> · ${e(event.reason)} · ${e(new Date(event.time * 1000).toLocaleString())}</p>`,
            )
            .join("")
        : "<p>No budget alerts</p>"
    }</div></section>${operations()}`
  );
}
function quotaModal(kind, id) {
  const row = state.traffic?.[kind]?.[id],
    target = (kind === "apps" ? state.apps : state.profiles).find(
      (item) => item.id === id,
    );
  if (!target) return;
  openModal(
    "Traffic budget",
    `<form id="quota-form" class="stack"><input type="hidden" name="id" value="${e(id)}"><input type="hidden" name="kind" value="${kind}"><p data-no-translate>${e(target.name)}</p><label for="quota-mib">Limit in MiB (0 disables budget)</label><input id="quota-mib" type="number" min="0" max="8589934591" step="any" name="mib" value="${row?.quota ? row.quota / 1048576 : 0}" required><label for="quota-warning">Warning at percent</label><input id="quota-warning" type="number" min="1" max="99" name="warning" value="${row?.warn_percent || 80}" required><label class="check-inline"><input type="checkbox" name="reset"> Reset usage period from now</label><p class="notice">Changing routes or restarting does not reset usage. Resetting the period or increasing the limit permits a manual restart; it does not start a workload automatically.</p>${formActions("Save budget")}</form>`,
  );
}
function logsPage() {
  return (
    header(
      "The <span>live feed.</span>",
      "Follow SplitForge's systemd journal and recent control-plane operations.",
      "",
      "WORKSPACE / LOGS",
    ) +
    `<div id="diagnostics-panel">${diagnosticsPanel()}</div><section class="panel"><div class="panel-header"><h2><span>›_</span> journalctl · splitforge-*</h2><div class="log-toolbar"><label class="check-inline"><input type="checkbox" id="follow-logs" checked> Follow</label><button class="text-button" data-action="refresh-logs">Refresh ↻</button></div></div><pre class="log-output" id="journal-output">Reading journal…</pre></section>${operations()}`
  );
}
function diagnosticsPanel() {
  const result = state.diagnostics;
  return `<section class="panel"><div class="panel-header"><h2>◇ Health & repair / بررسی و تعمیر</h2><div class="row-actions">${button("Check health", "diagnostics-check", "", "", state.busy)}${button("Check & repair", "diagnostics-repair", "", "primary", state.busy)}</div></div><div class="form-panel"><p>Checks cores, DNS, tunnel guards, managed applications and web ports. Repair may restart managed workloads; open connections close. Host routing and SSH settings are never reset.</p>${result ? `<p class="mono">${e(result.errors)} errors · ${e(result.warnings)} warnings · ${e(new Date(result.updated * 1000).toLocaleString())}</p><div class="table-wrap"><table><thead><tr><th>Check / scope</th><th>State</th><th>Finding / next step</th></tr></thead><tbody>${result.checks.map((row) => `<tr><td>${e(row.category)}<div class="mono">${e(row.scope)}</div></td><td><span class="badge ${row.status === "ok" ? "" : "offline"}">${e(row.status.toUpperCase())}${row.repaired ? " · REPAIRED" : ""}</span></td><td>${e(row.message)}${row.remedy ? `<div class="field-hint">${e(row.remedy)}</div>` : ""}</td></tr>`).join("")}</tbody></table></div>` : '<p class="field-hint">Run a check to see actionable results. Checks do not install or restart anything unless repair is selected.</p>'}</div></section>`;
}
const lessons = {
  en: [
    [
      "Install your cores",
      "Open Core installer. WireGuard and OpenVPN use their own tools. Proxy profiles need Xray and tun2socks; DNSTT/Slipstream include those automatically.",
    ],
    [
      "Import and test a profile",
      "Add a URI or a server-side .conf, .ovpn or single-outbound .json file. DNS tunnels need a compatible remote SOCKS5 target. Start the profile, then test its HTTPS egress.",
    ],
    [
      "Register an application",
      "Choose a script, binary or systemd service. Set its Linux user and working directory; root is supported. Use the app's own Python venv when needed. Registration does not start it.",
    ],
    [
      "Assign a route",
      "Open App router, choose the app's route and apply. The managed process stops and restarts inside the chosen namespace. Open connections and memory do not migrate. Direct returns to the host network.",
    ],
    [
      "Observe and protect",
      "Inspect lifecycle and fresh egress separately. Guards and encrypted DNS are mandatory for tunnel profiles. Root workloads must be trusted. Namespace isolation is not a complete hostile-code sandbox.",
    ],
    [
      "Stop and recover",
      "Closing this panel leaves services running. Stop apps deliberately. Remove app/user references before deleting profiles. After an upgrade, splitforge restore reapplies saved enabled assignments.",
    ],
  ],
  fa: [
    [
      "نصب هسته‌ها",
      "در Core installer موارد لازم را انتخاب کنید. برای پروکسی به Xray و tun2socks نیاز دارید. پیش‌نیازهای DNSTT و Slipstream خودکار اضافه می‌شوند.",
    ],
    [
      "ثبت و تست پروفایل",
      "لینک یا مسیر فایل تنظیمات روی سرور را وارد کنید. تونل DNS به سرور سازگار با مقصد SOCKS5 نیاز دارد. ابتدا پروفایل را شروع و سپس خروجی را تست کنید.",
    ],
    [
      "ثبت اسکریپت یا سرویس",
      "فایل یا فرمان اجرا، کاربر لینوکس و پوشه کاری را انتخاب کنید؛ root پشتیبانی می‌شود. برای پایتون مسیر محیط خود برنامه را بدهید. ثبت به‌تنهایی برنامه را اجرا نمی‌کند.",
    ],
    [
      "انتخاب مسیر",
      "از App router مسیر برنامه را انتخاب و اعمال کنید. برنامه متوقف و در namespace جدید دوباره اجرا می‌شود؛ اتصال و حافظه قبلی حفظ نمی‌شوند. Direct یعنی اینترنت مستقیم میزبان.",
    ],
    [
      "بررسی و محافظت",
      "وضعیت سرویس با تست تازه خروجی فرق دارد. DNS رمزگذاری‌شده و Kill Switch برای تونل اجباری است. روی root فقط کد مورد اعتماد اجرا کنید؛ namespace یک sandbox کامل نیست.",
    ],
    [
      "توقف و بازیابی",
      "بستن پنل سرویس را متوقف نمی‌کند. برای توقف از Stop استفاده کنید. قبل از حذف پروفایل، ارجاع برنامه‌ها و کاربران را بردارید. بعد از ارتقا splitforge restore نگاشت‌های فعال ذخیره‌شده را بازیابی می‌کند.",
    ],
  ],
};
function helpPage() {
  return (
    header(
      "A little <span>guidance.</span>",
      "From your first profile to your first isolated workload.",
      `<button class="button" data-action="help-en">English</button><button class="button" data-action="help-fa">فارسی</button>`,
      "WORKSPACE / QUICK START",
    ) +
    `<div class="help-steps" ${helpLanguage === "fa" ? 'dir="rtl" lang="fa"' : ""}>${lessons[helpLanguage].map(([title, body]) => `<article class="help-step"><div><h2>${title}</h2><p>${body}</p></div></article>`).join("")}</div>`
  );
}

function renderMain() {
  if (!state) return;
  const content = $("#main-content");
  content.innerHTML = {
    overview,
    router: routerPage,
    profiles: profilesPage,
    security: securityPage,
    cores: coresPage,
    logs: logsPage,
    help: helpPage,
    traffic: trafficPage,
  }[page]();
  if (page === "logs") loadLogs();
  if (page === "cores") updateCorePlan();
}
function navigate(next) {
  page = Object.hasOwn(pages, next) ? next : "overview";
  search = "";
  $("#breadcrumb").textContent = page;
  document
    .querySelectorAll(".nav-item")
    .forEach((node) =>
      node.classList.toggle("active", node.dataset.page === page),
    );
  $(".sidebar").classList.remove("open");
  location.hash = page;
  renderMain();
}
function renderStatus() {
  $("#host-label").textContent = state.host;
  $("#workspace-host").textContent = state.host.toUpperCase();
  $("#version-label").textContent = `v${state.version} / CONTROL PLANE`;
  $("#mode-badge").textContent = state.demo
    ? "READ-ONLY DEMO"
    : "LOCAL SESSION";
  $("#mode-badge").classList.toggle("demo", state.demo);
  $("#cpu-label").textContent = `${state.cpu_percent.toFixed(0)}%`;
  $("#memory-label").textContent = `${state.memory_percent.toFixed(0)}%`;
  $("#memory-meter").style.width =
    `${Math.max(0, Math.min(100, state.memory_percent))}%`;
  $("#connection-label").textContent = state.demo
    ? "Demo · sample addresses"
    : "Connected to local control plane";
  $("#connection-dot").classList.add("green");
  $("#updated-label").textContent =
    `Updated ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
  const running = state.jobs.find((job) => job.state === "running");
  $("#job-banner").hidden = !running;
  if (running)
    $("#job-banner").textContent =
      `◌ ${running.action} · ${running.progress?.phase || "Working…"}`;
}
async function poll() {
  clearTimeout(timer);
  if (!authenticated) return;
  try {
    const previous = state;
    const next = await api("/api/state");
    if (!authenticated) return;
    state = next;
    $("#connection-banner").hidden = true;
    renderStatus();
    if (page === "logs" && $("#diagnostics-panel"))
      $("#diagnostics-panel").innerHTML = diagnosticsPanel();
    if (
      !previous ||
      ["overview", "router", "profiles", "traffic"].includes(page)
    ) {
      const focus = document.activeElement?.id,
        position = focus === "search" ? $("#search")?.selectionStart : null;
      renderMain();
      if (focus === "search") {
        $("#search")?.focus();
        $("#search")?.setSelectionRange(position, position);
      }
    }
    if (page === "logs" && previous) await loadLogs();
    const list = $("#operation-list");
    if (list) {
      const wrapper = document.createElement("div");
      wrapper.innerHTML = operations();
      list.replaceWith(wrapper.firstElementChild);
    }
    for (const job of state.jobs) {
      if (
        previous &&
        job.state !== "running" &&
        seenJobs.get(job.id) !== job.state
      )
        toast(job.error || `${job.action} completed`, job.state === "failed");
      seenJobs.set(job.id, job.state);
    }
  } catch (error) {
    if (authenticated) {
      $("#connection-banner").hidden = false;
      $("#connection-banner").textContent =
        `Connection issue: ${error.message}. Retrying…`;
      $("#connection-dot").classList.remove("green");
    }
  } finally {
    if (authenticated) timer = setTimeout(poll, 3000);
  }
}
async function loadLogs() {
  const output = $("#journal-output");
  if (!output || ($("#follow-logs") && !$("#follow-logs").checked)) return;
  try {
    const result = await api("/api/logs");
    output.textContent = result.text || "No SplitForge journal entries yet.";
    output.scrollTop = output.scrollHeight;
  } catch (error) {
    output.textContent = error.message;
  }
}
function lockScreen() {
  authenticated = false;
  csrf = "";
  state = null;
  seenJobs = new Map();
  clearTimeout(timer);
  $("#app-shell").hidden = true;
  $("#login-view").hidden = false;
  $("#modal").close();
}
async function sendAction(body) {
  await api("/api/action", body);
  $("#modal").close();
  toast("Operation started. Results will appear in the control plane.");
  await poll();
}

function openModal(title, body, eyebrow = "CONTROL PLANE") {
  $("#modal-title").textContent = title;
  $("#modal-eyebrow").textContent = eyebrow;
  $("#modal-body").innerHTML = body;
  if (!$("#modal").open) $("#modal").showModal();
}
function formActions(label = "Save", danger = false) {
  return `<p id="form-error" class="error-text" role="alert"></p><div class="modal-actions"><button type="button" class="button" data-action="cancel">Cancel</button><button type="submit" class="button ${danger ? "danger" : "primary"}">${label}</button></div>`;
}
function field(
  label,
  name,
  value = "",
  placeholder = "",
  type = "text",
  required = true,
) {
  return `<div><label for="field-${name}">${label}</label><input id="field-${name}" name="${name}" type="${type}" value="${e(value)}" placeholder="${e(placeholder)}" ${required ? "required" : ""}></div>`;
}
function addApp(draft = {}) {
  openModal(
    "Register a workload",
    `<form id="action-form" data-type="app.add" class="stack">${field("Application name", "name", draft.name, "telegram-bot")}${field("Command and arguments", "command", draft.command, "/usr/bin/python3 /srv/bot.py", "text", false)}<button class="button" type="button" data-action="browse-app">Browse server files ↗</button><div class="form-grid">${field("Linux user", "user", draft.user ?? "root")}${field("Working directory", "cwd", draft.cwd ?? "/")}</div>${field("Existing systemd service (optional)", "service", draft.service, "my-worker.service", "text", false)}<div class="notice">Registration saves a command. Assign a route to start it. Existing services must match the selected user. SSH and host network services are protected.</div>${formActions("Register workload")}</form>`,
    "APPLICATIONS / NEW",
  );
}
function addProfile(draft = {}) {
  const method = draft.method || "import";
  openModal(
    draft.id ? "Replace stopped profile" : "Import a tunnel profile",
    `<form id="action-form" data-type="profile" class="stack"><input type="hidden" name="id" value="${e(draft.id || "")}">${field("Profile name", "name", draft.name, "wg-europe")}<div><label for="profile-method">Import method</label><select id="profile-method" name="method"><option value="import" ${method === "import" ? "selected" : ""}>URI or server-side configuration file</option><option value="dnstt" ${method === "dnstt" ? "selected" : ""}>DNSTT wizard</option><option value="slipstream" ${method === "slipstream" ? "selected" : ""}>Slipstream wizard</option></select></div><div id="profile-import-fields" ${method !== "import" ? "hidden" : ""}>${field("URI or server-side file path", "source", draft.source, "vless://… or /root/profiles/client.conf", "password", false)}<p class="field-hint">Secrets are not saved in your browser. Native imports: .conf / .ovpn / single-outbound .json</p><button class="button" type="button" data-action="browse-profile">Browse server files ↗</button></div><div id="profile-dns-fields" class="stack" ${method === "import" ? "hidden" : ""}>${field("Delegated tunnel domain", "domain", draft.domain, "t.example.com", "text", false)}${field("Resolver", "resolver", draft.resolver, "udp://1.1.1.1:53 (DNSTT) or 1.1.1.1:53 (Slipstream)", "text", false)}${field("DNSTT hex public key", "public_key", draft.public_key, "32-byte public key in hex", "text", false)}${field("Slipstream server certificate path", "certificate", draft.certificate, "/root/server.pem", "text", false)}<p class="field-hint">A compatible remote server targeting SOCKS5 is required. These DNS adapters carry TCP.</p></div><div class="notice">Save does not start a tunnel. Replacing a profile requires it to be stopped and preserves its application assignments.</div>${formActions("Save profile")}</form>`,
    "TUNNELS / CONFIGURATION",
  );
}
function routeModal(id) {
  const app = state.apps.find((a) => a.id === id);
  if (!app) return;
  const primary = app.failover_enabled
    ? app.primary_profile_id
    : app.profile_id;
  openModal(
    `Assign route · ${app.name}`,
    `<form id="action-form" data-type="app.bind" class="stack"><input type="hidden" name="id" value="${e(id)}"><div><label for="route-profile">Primary network path</label><select id="route-profile" name="profile_id"><option value="" ${!primary ? "selected" : ""}>◌ Direct server internet</option>${state.profiles.map((p) => `<option value="${e(p.id)}" ${p.id === primary ? "selected" : ""}>${e(p.name)} · ${e(p.protocol.toUpperCase())} · ${p.active ? "active" : "auto start"}</option>`).join("")}</select></div><div><label for="route-backup">Automatic backup tunnel (optional)</label><select id="route-backup" name="backup_profile_id" ${!primary ? "disabled" : ""}><option value="">Disabled · keep this single route</option>${state.profiles.map((p) => `<option value="${e(p.id)}" ${p.id === primary ? "disabled" : ""} ${app.failover_enabled && p.id === app.backup_profile_id ? "selected" : ""}>${e(p.name)} · ${e(p.protocol.toUpperCase())}</option>`).join("")}</select><p class="field-hint">Two failed health checks trigger a restart into the backup. If both fail, the app stays stopped. Direct is never an automatic fallback. A healthy backup is retained until you reapply the primary or the backup fails.</p></div><div class="notice">This stops and restarts the managed workload. Automatic failover also restarts it: open connections and process memory will be lost.</div><div class="notice green">✓ Kill switch and encrypted DNS remain enforced for tunnel assignments.</div>${formActions("Apply & restart")}</form>`,
    "APP ROUTER / REASSIGN",
  );
}
function confirmAction(action, id, title, description) {
  openModal(
    title,
    `<form id="action-form" data-type="${action}" class="stack"><input type="hidden" name="id" value="${e(id)}"><div class="notice">${description}</div>${formActions("Confirm", true)}</form>`,
  );
}
function selectedCorePlan() {
  const selected = new Set(
    [...document.querySelectorAll('input[name="core"]:checked')].map(
      (n) => n.value,
    ),
  );
  if (
    [...selected].some((n) =>
      ["xray", "tun2socks", "dnstt-client", "slipstream-client"].includes(n),
    )
  ) {
    selected.add("xray");
    selected.add("tun2socks");
  }
  if (selected.size) selected.add("base");
  return [...selected];
}
function updateCorePlan() {
  const names = selectedCorePlan();
  if ($("#core-plan"))
    $("#core-plan").textContent = names.length
      ? `Plan: ${names.join(" → ")}`
      : "Select components to review the plan.";
  if ($("#install-cores")) $("#install-cores").disabled = !names.length;
}
function draftForm() {
  return Object.fromEntries(new FormData($("#action-form")));
}
async function browse(path = "/") {
  const result = await api(`/api/browse?path=${encodeURIComponent(path)}`);
  openModal(
    "Browse server files",
    `<form id="browse-form"><label for="browse-path">Absolute server directory</label><div class="browse-row"><input id="browse-path" name="path" value="${e(result.path)}"><button class="button" type="submit">Go</button></div></form><div class="file-list"><button type="button" class="file-entry" data-action="directory" data-path="${e(result.parent)}">↰ Parent directory</button>${result.entries.map((entry) => `<button type="button" class="file-entry" data-action="${entry.directory ? "directory" : "choose-file"}" data-path="${e(entry.path)}">${entry.directory ? "▸" : "·"} ${e(entry.name)}</button>`).join("")}</div><p class="field-hint">${fileMode === "app" ? "Choose a script or executable; this does not move a running process." : "Choose a provider .conf, .ovpn or .json file."} Up to 200 entries are displayed.</p><div class="modal-actions"><button class="button" data-action="back-to-form">Back to form</button></div>`,
  );
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-page]");
  if (nav && state) {
    navigate(nav.dataset.page);
    return;
  }
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action,
    id = target.dataset.id;
  try {
    if (action === "add-app") addApp();
    else if (action === "quota-app") quotaModal("apps", id);
    else if (action === "quota-profile") quotaModal("profiles", id);
    else if (action === "traffic-enable")
      await sendAction({ action: "traffic.enable" });
    else if (action === "backup-download") {
      const response = await fetch(`/api/backup?id=${encodeURIComponent(id)}`, {
        credentials: "same-origin",
      });
      if (!response.ok)
        throw new Error(
          (await response.json()).error || "Backup download failed",
        );
      const url = URL.createObjectURL(await response.blob()),
        anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "splitforge-backup.sfb";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else if (action === "add-profile") addProfile();
    else if (action === "profile-edit")
      addProfile(state.profiles.find((p) => p.id === id));
    else if (action === "route") routeModal(id);
    else if (action === "cancel") $("#modal").close();
    else if (action === "app-remove")
      confirmAction(
        "app.remove",
        id,
        "Remove application?",
        "The managed service will stop and its SplitForge registration will be removed. Original scripts and existing service definitions are retained.",
      );
    else if (action === "profile-remove")
      confirmAction(
        "profile.remove",
        id,
        "Remove tunnel profile?",
        "Remove all app and user references first. The profile and its owned network resources will be removed.",
      );
    else if (action === "profile.stop")
      confirmAction(
        action,
        id,
        "Stop tunnel profile?",
        "Dependent workloads may stop with this profile. They will not fall back to Direct.",
      );
    else if (action === "app-toggle") {
      const app = state.apps.find((a) => a.id === id);
      await sendAction(
        app.running ? { action: "app.stop", id } : { action: "app.start", id },
      );
    } else if (["profile.start", "profile.test", "app.test"].includes(action))
      await sendAction({ action, id });
    else if (action === "diagnostics-check")
      await sendAction({ action: "diagnostics.run", repair: false });
    else if (action === "diagnostics-repair")
      openModal(
        "Check & repair?",
        `<form id="diagnostics-repair-form"><p>Repairs required cores and SplitForge-owned tunnel/DNS/guard resources. Enabled managed apps may restart and their open connections will close. Host routing, SSH and provider firewall settings are retained.</p><div id="form-error" class="form-error"></div><div class="modal-actions"><button type="button" class="button" data-action="cancel">Cancel</button><button type="submit" class="button primary">Check & repair now</button></div></form>`,
      );
    else if (action === "refresh-logs") {
      if ($("#follow-logs")) $("#follow-logs").checked = true;
      await loadLogs();
    } else if (action.startsWith("help-")) {
      window.SplitForgeLocale.set(action.slice(5));
    } else if (action === "browse-app" || action === "browse-profile") {
      fileDraft = draftForm();
      fileMode = action === "browse-app" ? "app" : "profile";
      await browse(fileMode === "app" ? fileDraft.cwd || "/" : "/root");
    } else if (action === "directory") await browse(target.dataset.path);
    else if (action === "back-to-form") {
      fileMode === "app" ? addApp(fileDraft) : addProfile(fileDraft);
    } else if (action === "choose-file") {
      const path = target.dataset.path,
        q = (value) => "'" + value.replaceAll("'", "'\\''") + "'";
      if (fileMode === "app") {
        fileDraft.command = path.endsWith(".py")
          ? `/usr/bin/python3 ${q(path)}`
          : path.endsWith(".sh")
            ? `/bin/bash ${q(path)}`
            : q(path);
        fileDraft.cwd = path.slice(0, path.lastIndexOf("/")) || "/";
        if (!fileDraft.name) fileDraft.name = path.split("/").at(-1);
        addApp(fileDraft);
      } else {
        fileDraft.source = path;
        addProfile(fileDraft);
      }
    }
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target,
    formId = form.getAttribute("id");
  if (
    ![
      "action-form",
      "dns-form",
      "cores-form",
      "browse-form",
      "diagnostics-repair-form",
      "backup-export-form",
      "backup-restore-form",
      "quota-form",
    ].includes(formId)
  )
    return;
  event.preventDefault();
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  try {
    const data = Object.fromEntries(new FormData(form));
    if (formId === "quota-form") {
      const mib = Number(data.mib),
        limit = Math.round(mib * 1048576),
        warning = Number(data.warning);
      if (!Number.isSafeInteger(limit) || limit < 0)
        throw new Error("Budget must be a valid nonnegative MiB amount");
      await sendAction({
        action: "traffic.quota",
        id: data.id,
        kind: data.kind,
        limit: limit || null,
        warning,
        reset: data.reset === "on",
      });
      return;
    }
    if (formId === "backup-export-form") {
      if (data.password !== data.confirmation)
        throw new Error("Backup passwords do not match");
      await sendAction({ action: "backup.export", password: data.password });
      form.reset();
      return;
    }
    if (formId === "backup-restore-form") {
      const file = form.elements.archive.files[0];
      if (!file || file.size > 16 * 1024 * 1024)
        throw new Error("Backup file must be smaller than 16 MiB");
      await sendAction({
        action: "backup.restore",
        archive: await file.text(),
        password: data.password,
        confirm: data.confirm === "on",
      });
      form.reset();
      return;
    }
    if (formId === "browse-form") {
      await browse(data.path);
      return;
    }
    if (formId === "diagnostics-repair-form") {
      await sendAction({ action: "diagnostics.run", repair: true });
      return;
    }
    if (formId === "cores-form") {
      await sendAction({ action: "cores.install", names: selectedCorePlan() });
      return;
    }
    if (formId === "dns-form") {
      await sendAction({ action: "profile.dns", ...data });
      return;
    }
    let action = form.dataset.type;
    if (action === "profile") {
      action =
        data.method === "import" ? "profile.import" : "profile.dns-tunnel";
      data.protocol = data.method;
    }
    await sendAction({ ...data, action });
  } catch (error) {
    const errorNode = form.querySelector("#form-error");
    if (errorNode) errorNode.textContent = error.message;
    else toast(error.message, true);
  } finally {
    if (submit) submit.disabled = false;
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "route-profile" && $("#route-backup")) {
    const backup = $("#route-backup"),
      primary = event.target.value;
    backup.disabled = !primary;
    for (const option of backup.options)
      option.disabled = Boolean(option.value && option.value === primary);
    if (!primary || backup.value === primary) backup.value = "";
  }
  if (event.target.id === "profile-method") {
    $("#profile-import-fields").hidden = event.target.value !== "import";
    $("#profile-dns-fields").hidden = event.target.value === "import";
  }
  if (event.target.id === "dns-profile") {
    const p = state.profiles.find((p) => p.id === event.target.value);
    if (p) {
      $("#dns-url").value = p.doh_url;
      $("#dns-bootstrap").value = p.doh_ip;
    }
  }
  if (event.target.name === "core") updateCorePlan();
});
document.addEventListener("input", (event) => {
  if (event.target.id === "search") {
    const position = event.target.selectionStart;
    search = event.target.value;
    renderMain();
    $("#search").focus();
    $("#search").setSelectionRange(position, position);
  }
});
document.addEventListener("keydown", (event) => {
  if (
    !authenticated ||
    $("#modal").open ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
  )
    return;
  const keys = [
    "overview",
    "router",
    "profiles",
    "security",
    "cores",
    "logs",
    "help",
    "traffic",
  ];
  if (/^[1-8]$/.test(event.key)) {
    event.preventDefault();
    navigate(keys[Number(event.key) - 1]);
  }
});
$("#modal-close").addEventListener("click", () => $("#modal").close());
$("#refresh-button").addEventListener("click", poll);
$("#menu-toggle").addEventListener("click", () =>
  $(".sidebar").classList.toggle("open"),
);
$("#logout-button").addEventListener("click", async () => {
  try {
    await api("/api/logout", {});
    lockScreen();
  } catch (error) {
    toast(error.message, true);
  }
});
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-button").disabled = true;
  $("#login-error").textContent = "";
  try {
    const result = await api("/api/login", { token: $("#access-token").value });
    csrf = result.csrf;
    $("#access-token").value = "";
    authenticated = true;
    $("#login-view").hidden = true;
    $("#app-shell").hidden = false;
    page = Object.hasOwn(pages, location.hash.slice(1))
      ? location.hash.slice(1)
      : "overview";
    await poll();
    navigate(page);
  } catch (error) {
    $("#login-error").textContent = error.message;
  } finally {
    $("#login-button").disabled = false;
  }
});
async function boot() {
  try {
    const session = await api("/api/session");
    if (session.demo) {
      $("#access-token").hidden = true;
      $('label[for="access-token"]').hidden = true;
      $("#login-button").textContent = "Explore read-only demo ↗";
      $("#login-note").textContent =
        "Sample addresses and measurements. No server changes or downloads.";
    }
    if (session.authenticated) {
      csrf = session.csrf;
      authenticated = true;
      $("#login-view").hidden = true;
      $("#app-shell").hidden = false;
      page = Object.hasOwn(pages, location.hash.slice(1))
        ? location.hash.slice(1)
        : "overview";
      await poll();
      navigate(page);
    }
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
}
document.addEventListener("splitforge-language", (event) => {
  helpLanguage = event.detail;
  if (page === "help" && state) renderMain();
});
boot();
