const headers = () => ({ "Content-Type": "application/json" });

let connected = false;
let refreshTimer = null;
let clockTimer = null;
let authPollTimer = null;
let heartbeatTimer = null;
let launchDefaults = {};
let savedHosts = [];
let defaultCursorBin = "~/cursor-tunnel/cursor";
let launchPresets = [];
/** Path set by Generate SSH key (not shown in the manual path field). */
let autofillKeyPath = "";
/** Public key line for Copy button (not shown in the UI). */
let cachedPublicKey = "";
/** @type {Record<string, {code:string,url:string,session_id:string,status:string,tunnel_name:string}>} */
const cardAuth = {};
/** @type {Record<string, { seconds: number, syncedAt: number }>} */
const runningClocks = {};

function formatDuration(totalSeconds) {
  let s = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(s / 86400);
  s %= 86400;
  const hours = Math.floor(s / 3600);
  s %= 3600;
  const minutes = Math.floor(s / 60);
  const seconds = s % 60;
  if (days) {
    return `${days}-${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function syncRunningClocks(jobs) {
  const now = Date.now();
  const active = new Set();
  for (const j of jobs) {
    if (j.is_history) continue;
    active.add(String(j.job_id));
    if (j.remaining_seconds != null) {
      runningClocks[j.job_id] = { seconds: j.remaining_seconds, syncedAt: now };
    }
  }
  Object.keys(runningClocks).forEach((id) => {
    if (!active.has(id)) delete runningClocks[id];
  });
}

function liveRemainingDisplay(job) {
  const clock = runningClocks[job.job_id];
  if (clock) {
    const rem = Math.max(0, clock.seconds - Math.floor((Date.now() - clock.syncedAt) / 1000));
    return formatDuration(rem);
  }
  return job.remaining || "—";
}

function tickRunningTimers() {
  if (!connected || !document.getElementById("panel-running")?.classList.contains("active")) return;
  document.querySelectorAll(".tunnel-card[data-job-id]:not(.stopped) .tunnel-timer").forEach((el) => {
    const card = el.closest(".tunnel-card");
    const jobId = card?.dataset.jobId;
    const clock = jobId && runningClocks[jobId];
    if (!clock) return;
    const next = formatDuration(Math.max(0, clock.seconds - Math.floor((Date.now() - clock.syncedAt) / 1000)));
    if (el.textContent !== next) el.textContent = next;
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

let setupPollTimer = null;

function showSetupStatus(msg) {
  const el = document.getElementById("setup-status");
  if (el) {
    el.textContent = msg;
    el.classList.remove("hidden");
  }
}

function hideSetupStatus() {
  document.getElementById("setup-status")?.classList.add("hidden");
}

function startSetupPoll(onMessage) {
  stopSetupPoll();
  setupPollTimer = setInterval(async () => {
    try {
      const s = await fetch("/api/setup-status").then((r) => r.json());
      if (s.active && s.message) onMessage(s.message);
    } catch {
      /* ignore poll errors */
    }
  }, 400);
}

function stopSetupPoll() {
  if (setupPollTimer) clearInterval(setupPollTimer);
  setupPollTimer = null;
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

function confirmDialog(message, { confirmLabel = "OK", danger = false } = {}) {
  return new Promise((resolve) => {
    const overlay = document.getElementById("confirm-overlay");
    const msg = document.getElementById("confirm-message");
    const okBtn = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");
    if (!overlay || !msg || !okBtn || !cancelBtn) {
      resolve(window.confirm(message));
      return;
    }

    msg.textContent = message;
    okBtn.textContent = confirmLabel;
    okBtn.classList.toggle("danger", danger);
    okBtn.classList.toggle("primary", !danger);
    overlay.classList.remove("hidden");

    const cleanup = (result) => {
      overlay.classList.add("hidden");
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      overlay.removeEventListener("click", onBackdrop);
      resolve(result);
    };
    const onOk = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onBackdrop = (e) => {
      if (e.target === overlay) cleanup(false);
    };

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    overlay.addEventListener("click", onBackdrop);
  });
}

function setConn(state, text) {
  const pill = document.getElementById("conn-pill");
  pill.textContent = text;
  pill.classList.remove("ok", "err");
  if (state === "ok") pill.classList.add("ok");
  if (state === "err") pill.classList.add("err");
}

function updateGates() {
  const on = connected;
  ["running", "launch"].forEach((tab) => {
    document.getElementById(`${tab}-gate`)?.classList.toggle("hidden", on);
    document.getElementById(`${tab}-content`)?.classList.toggle("hidden", !on);
  });
}

function showTab(name) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  document.getElementById(`panel-${name}`)?.classList.add("active");
  document.querySelector(`.nav-btn[data-tab="${name}"]`)?.classList.add("active");
  if (name === "running" && connected) refreshRunning();
  if (name === "launch" && connected) refreshLaunchFormForTab();
}

document.querySelectorAll(".nav-btn, [data-tab]").forEach((btn) => {
  btn.addEventListener("click", () => showTab(btn.dataset.tab));
});

function setConnected(yes) {
  connected = yes;
  updateGates();
}

function disconnect() {
  connected = false;
  if (refreshTimer) clearInterval(refreshTimer);
  if (clockTimer) clearInterval(clockTimer);
  Object.keys(runningClocks).forEach((k) => delete runningClocks[k]);
  Object.keys(cardAuth).forEach((k) => delete cardAuth[k]);
  fetch("/api/disconnect", { method: "POST" }).catch(() => {});
  updateGates();
  setConn("", "Not connected");
  showTab("connect");
  toast("Disconnected");
}

function remoteDirForUser() {
  return "~/cursor-tunnel";
}

function isGenericRemoteDir(path) {
  const p = (path || "").trim().replace(/\/+$/, "");
  return (
    !p ||
    p === "~/cursor-tunnel" ||
    p === "$HOME/cursor-tunnel" ||
    /^~\/cursor-tunnel(\/[\w.-]+)?$/.test(p) ||
    /^\$HOME\/cursor-tunnel(\/[\w.-]+)?$/.test(p)
  );
}

function syncRemoteDirFromUser() {
  const connect = document.getElementById("connect-form");
  const settings = document.getElementById("settings-form");
  const current = settings.remote_dir.value.trim();
  if (isGenericRemoteDir(current)) {
    settings.remote_dir.value = remoteDirForUser(connect.ssh_user.value);
  }
}

function baseTunnelName(user) {
  const u = (user || "").trim();
  return u ? `ct_${u}` : "ct_user";
}

function populateHostSelect(hosts, selected) {
  const sel = document.getElementById("host-select");
  const customRow = document.getElementById("host-custom-row");
  const customInput = document.getElementById("host-custom-input");
  if (!sel) return;
  savedHosts = [...hosts];
  sel.innerHTML = "";
  for (const h of hosts) {
    const opt = document.createElement("option");
    opt.value = h;
    opt.textContent = h;
    sel.appendChild(opt);
  }
  const customOpt = document.createElement("option");
  customOpt.value = "__custom__";
  customOpt.textContent = "Custom hostname…";
  sel.appendChild(customOpt);
  if (selected && hosts.includes(selected)) {
    sel.value = selected;
    customRow?.classList.add("hidden");
  } else if (selected) {
    sel.value = "__custom__";
    if (customInput) customInput.value = selected;
    customRow?.classList.remove("hidden");
  } else if (hosts.length) {
    sel.value = hosts[0];
    customRow?.classList.add("hidden");
  } else {
    sel.value = "__custom__";
    customRow?.classList.remove("hidden");
  }
}

function getSelectedHost() {
  const sel = document.getElementById("host-select");
  if (!sel) return "";
  if (sel.value === "__custom__") {
    return document.getElementById("host-custom-input")?.value.trim() || "";
  }
  return sel.value;
}

function onHostSelectChange() {
  const sel = document.getElementById("host-select");
  const customRow = document.getElementById("host-custom-row");
  if (!sel || !customRow) return;
  customRow.classList.toggle("hidden", sel.value !== "__custom__");
}

function suggestNextTunnelName(base, existingNames = []) {
  const taken = new Set(existingNames.map((n) => String(n).trim()));
  const b = base.replace(/_+$/, "");
  if (!taken.has(b)) return b;
  for (let i = 1; ; i++) {
    const candidate = `${b}_${i}`;
    if (!taken.has(candidate)) return candidate;
  }
}

function tunnelBaseName(name) {
  const n = String(name || "").trim().replace(/_+$/, "");
  const m = n.match(/^(.*)_(\d+)$/);
  return m ? m[1] : n;
}

function resolveTunnelName(desired, takenNames) {
  const taken = new Set(takenNames.map((n) => String(n).trim()));
  const want = String(desired || "").trim();
  if (want && !taken.has(want)) return want;
  const user = document.getElementById("connect-form")?.ssh_user?.value;
  const base = want ? tunnelBaseName(want) : baseTunnelName(user);
  return suggestNextTunnelName(base, [...taken]);
}

async function getTakenTunnelNames() {
  if (!connected) return [];
  try {
    const res = await api("/api/status");
    return (res.jobs || []).filter((j) => !j.is_history).map((j) => j.tunnel_name);
  } catch {
    return [];
  }
}

function readLaunchForm() {
  const form = document.getElementById("launch-form");
  return {
    tunnel_name: form.tunnel_name.value.trim(),
    cpus: form.cpus.value,
    mem_gib: form.mem_gib.value,
    time: form.time.value.trim(),
    account: form.account.value.trim(),
    partition: form.partition.value.trim() || "public",
    qos: form.qos.value.trim(),
    gpus: form.gpus.value.trim(),
    extra_sbatch: form.extra_sbatch.value.trim(),
    cursor_bin: form.cursor_bin.value.trim(),
  };
}

function applyLaunchParams(params, { updateName = true } = {}) {
  const form = document.getElementById("launch-form");
  if (!form || !params) return;
  if (params.cpus != null && params.cpus !== "") form.cpus.value = params.cpus;
  if (params.mem_gib != null && params.mem_gib !== "") form.mem_gib.value = params.mem_gib;
  if (params.time) form.time.value = params.time;
  if (params.account != null) form.account.value = params.account;
  if (params.partition != null) form.partition.value = params.partition;
  if (params.qos != null) form.qos.value = params.qos;
  if (params.gpus != null) form.gpus.value = params.gpus;
  if (params.extra_sbatch != null) form.extra_sbatch.value = params.extra_sbatch;
  if (params.cursor_bin != null) form.cursor_bin.value = params.cursor_bin;
  if (updateName && params.tunnel_name) form.tunnel_name.value = params.tunnel_name;
}

function jobLaunchParams(j) {
  const p = { ...(j.params || {}) };
  return {
    tunnel_name: j.tunnel_name || p.tunnel_name || "",
    cpus: p.cpus ?? launchDefaults.cpus ?? "4",
    mem_gib: p.mem_gib || String(p.mem || launchDefaults.mem_gib || "8").replace(/G$/i, ""),
    time: p.time || launchDefaults.time || "04:00:00",
    account: p.account ?? launchDefaults.account ?? "",
    qos: p.qos ?? launchDefaults.qos ?? "public",
    gpus: p.gpus || "",
    extra_sbatch: p.extra_sbatch || "",
    cursor_bin: p.cursor_bin || "",
    partition: p.partition || launchDefaults.partition || "public",
  };
}

function encodeJobParams(j) {
  return encodeURIComponent(JSON.stringify(jobLaunchParams(j)));
}

async function saveLaunchDefaultsFromForm() {
  const launch = readLaunchForm();
  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      defaults: {
        cpus: launch.cpus,
        mem_gib: launch.mem_gib,
        mem: launch.mem_gib,
        time: launch.time,
        account: launch.account,
        qos: launch.qos,
        gpus: launch.gpus,
        extra_sbatch: launch.extra_sbatch,
        cursor_bin: launch.cursor_bin,
        partition: launch.partition,
        tunnel_name: launch.tunnel_name,
        auth_provider: "github",
      },
    }),
  });
  Object.assign(launchDefaults, launch);
}

async function submitLaunchParams(params, { successVerb = "Started" } = {}) {
  const taken = await getTakenTunnelNames();
  const requested = params.tunnel_name;
  const tunnel_name = resolveTunnelName(requested, taken);
  const body = { ...params, tunnel_name };
  const launchBtn = document.querySelector("#launch-form button[type=submit]");
  const prevLabel = launchBtn?.textContent;
  if (launchBtn) {
    launchBtn.disabled = true;
    launchBtn.textContent = "Starting…";
  }
  startSetupPoll((msg) => {
    if (launchBtn) launchBtn.textContent = msg;
    showSetupStatus(msg);
  });
  try {
    const res = await api("/api/submit", { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) throw new Error(res.error);
    const form = document.getElementById("launch-form");
    if (form) form.tunnel_name.value = tunnel_name;
    applyLaunchParams(body, { updateName: false });
    launchDefaults.tunnel_name = tunnel_name;
    await saveLaunchDefaultsFromForm();
    if (tunnel_name !== requested) {
      toast(`${successVerb} as "${res.tunnel_name}" (${requested} in use)`);
    } else {
      toast(`${successVerb} "${res.tunnel_name}"`);
    }
    await loadLaunchPresets();
    return res;
  } finally {
    stopSetupPoll();
    hideSetupStatus();
    if (launchBtn) {
      launchBtn.disabled = false;
      launchBtn.textContent = prevLabel || "Start tunnel";
    }
  }
}

async function runAgainFromParams(params) {
  if (!connected) {
    toast("Connect first");
    showTab("connect");
    return;
  }
  try {
    await submitLaunchParams(params, { successVerb: "Started" });
    showTab("running");
    refreshRunning();
  } catch (err) {
    toast(err.message);
  }
}

async function editAndRunFromParams(params) {
  if (!connected) {
    toast("Connect first");
    showTab("connect");
    return;
  }
  applyLaunchParams(params, { updateName: false });
  const taken = await getTakenTunnelNames();
  document.getElementById("launch-form").tunnel_name.value = resolveTunnelName(params.tunnel_name, taken);
  showTab("launch");
  toast("Original keeps running — edit settings, then Start tunnel for a new one");
}

async function loadLaunchPresets() {
  const sel = document.getElementById("launch-preset-select");
  if (!sel) return;
  try {
    const res = await api("/api/launch-presets");
    launchPresets = res.presets || [];
    sel.innerHTML = '<option value="">— use current values —</option>';
    launchPresets.forEach((p, i) => {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = p.label || `Setup ${i + 1}`;
      sel.appendChild(opt);
    });
  } catch {
    /* ignore */
  }
}

async function refreshLaunchFormForTab() {
  const connect = document.getElementById("connect-form");
  const launch = document.getElementById("launch-form");
  if (!launch) return;
  applyLaunchParams(launchDefaults, { updateName: false });
  const desired =
    launchDefaults.tunnel_name ||
    launch.tunnel_name.value.trim() ||
    baseTunnelName(connect?.ssh_user?.value);
  const taken = await getTakenTunnelNames();
  launch.tunnel_name.value = resolveTunnelName(desired, taken);
  await loadLaunchPresets();
}

async function updateLaunchTunnelNameDefault() {
  await refreshLaunchFormForTab();
}

async function loadConfigIntoForms() {
  const res = await api("/api/config");
  const c = res.config;
  defaultCursorBin = c.default_cursor_bin || "~/cursor-tunnel/cursor";
  populateHostSelect(c.ssh_hosts || [], c.ssh_host || "");
  const connect = document.getElementById("connect-form");
  connect.ssh_user.value = c.ssh_user || "";
  connect.ssh_key_path_manual.value = "";
  autofillKeyPath = "";
  const savedKeyPath = (c.ssh_key_path || "").trim();
  connect.ssh_password.value = c.ssh_password === "********" ? "" : c.ssh_password || "";
  await loadSshKeyPanel(savedKeyPath);
  syncConnectAuthUi();

  const settings = document.getElementById("settings-form");
  settings.ssh_port.value = c.ssh_port || 22;
  settings.remote_dir.value = c.remote_dir || remoteDirForUser(c.ssh_user);
  settings.listen_host.value = c.listen_host || "127.0.0.1";
  settings.listen_port.value = c.listen_port || 8765;
  settings.shutdown_when_idle.checked = c.shutdown_when_idle !== false;
  const redeploy = document.getElementById("redeploy-on-connect");
  if (redeploy) redeploy.checked = !!c.redeploy_on_connect;
  syncRemoteDirFromUser();
  showDashboardUrls();

  const d = await api("/api/defaults");
  launchDefaults = d;
  const launch = document.getElementById("launch-form");
  launch.cpus.value = d.cpus || 4;
  launch.mem_gib.value = d.mem_gib || parseInt(String(d.mem || "8"), 10) || 8;
  launch.time.value = d.time || "04:00:00";
  launch.account.value = d.account || "";
  launch.partition.value = d.partition || "public";
  launch.qos.value = d.qos || "public";
  launch.gpus.value = d.gpus || "";
  launch.extra_sbatch.value = d.extra_sbatch || "";
  launch.cursor_bin.value = d.cursor_bin || "";
  launch.cursor_bin.placeholder = defaultCursorBin;
  if (connected) await updateLaunchTunnelNameDefault();
  else launch.tunnel_name.value = d.tunnel_name || baseTunnelName(c.ssh_user);
  await loadLaunchPresets();
}

async function showDashboardUrls() {
  const el = document.getElementById("dashboard-urls");
  if (!el) return;
  try {
    const info = await api("/api/info");
    if (info.dashboard_urls?.length) {
      el.textContent = `Open at: ${info.dashboard_urls.join(" · ")}`;
    }
  } catch {
    el.textContent = "";
  }
}

async function loadSshKeyPanel(savedKeyPath = "") {
  const statusEl = document.getElementById("ssh-key-status");
  const copyBtn = document.getElementById("ssh-key-copy-btn");
  const manualInput = document.querySelector("#connect-form [name=ssh_key_path_manual]");
  if (!statusEl) return;
  try {
    const info = await api("/api/ssh-key");
    if (info.exists) {
      statusEl.textContent = "In-app key ready — copy the public key to the cluster.";
      cachedPublicKey = info.public_key || "";
      copyBtn?.classList.remove("hidden");
      const appPath = (info.private_path || "").trim();
      if (savedKeyPath && appPath && savedKeyPath === appPath && !(manualInput?.value.trim())) {
        autofillKeyPath = appPath;
      } else if (!manualInput?.value.trim() && !autofillKeyPath && appPath && !savedKeyPath) {
        autofillKeyPath = appPath;
      } else if (savedKeyPath && savedKeyPath !== appPath && manualInput) {
        manualInput.value = savedKeyPath;
      }
    } else {
      statusEl.textContent = "Generate a key here, or enter a custom SSH key path below.";
      cachedPublicKey = "";
      copyBtn?.classList.add("hidden");
      if (savedKeyPath && manualInput) manualInput.value = savedKeyPath;
    }
    syncConnectAuthUi();
  } catch (err) {
    statusEl.textContent = err.message || "Could not load key status";
  }
}

function connectForm() {
  return document.getElementById("connect-form");
}

function usesPasswordAuth() {
  return !!connectForm()?.ssh_password?.value.trim();
}

function manualKeyPath() {
  return connectForm()?.ssh_key_path_manual?.value.trim() || "";
}

function effectiveKeyPath() {
  const manual = manualKeyPath();
  if (manual) return manual;
  return autofillKeyPath || "";
}

function storedKeyPath() {
  return effectiveKeyPath();
}

function syncConnectAuthUi() {
  const autofillEl = document.getElementById("ssh-key-path-autofill");
  const pwdHint = document.getElementById("ssh-password-hint");
  const manualHint = document.getElementById("ssh-key-path-manual-hint");
  const manual = manualKeyPath();
  if (autofillEl) {
    autofillEl.classList.toggle("hidden", !(autofillKeyPath && !manual));
  }
  if (manualHint) {
    manualHint.textContent = manual
      ? "Overrides the generated in-app key (if any)."
      : "";
  }
  if (pwdHint) {
    pwdHint.textContent = usesPasswordAuth()
      ? "Password will be used; SSH key is ignored."
      : "";
  }
}

async function generateDeviceSshKey(force = false) {
  if (
    force &&
    !(await confirmDialog(
      "Replace the existing key? You must update authorized_keys on the cluster.",
      { confirmLabel: "Replace", danger: true },
    ))
  ) {
    return;
  }
  try {
    const res = await api("/api/ssh-key/generate", {
      method: "POST",
      body: JSON.stringify({ force }),
    });
    autofillKeyPath = res.private_path || "";
    cachedPublicKey = res.public_key || "";
    const manualInput = document.querySelector("#connect-form [name=ssh_key_path_manual]");
    if (manualInput) manualInput.value = "";
    await loadSshKeyPanel(autofillKeyPath);
    syncConnectAuthUi();
    toast(res.message || "SSH key ready");
  } catch (err) {
    toast(err.message);
  }
}

document.getElementById("ssh-key-generate-btn")?.addEventListener("click", async () => {
  try {
    const info = await api("/api/ssh-key");
    await generateDeviceSshKey(info.exists);
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("ssh-key-copy-btn")?.addEventListener("click", async () => {
  let text = cachedPublicKey.trim();
  if (!text) {
    try {
      const info = await api("/api/ssh-key");
      text = (info.public_key || "").trim();
      cachedPublicKey = text;
    } catch {
      /* fall through */
    }
  }
  if (!text) {
    toast("No public key to copy — generate a key first");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toast("Public key copied — paste into authorized_keys on the cluster");
  } catch {
    toast("Copy failed — try again");
  }
});

document.querySelector("#connect-form [name=ssh_key_path_manual]")?.addEventListener("input", syncConnectAuthUi);
document.querySelector("#connect-form [name=ssh_password]")?.addEventListener("input", syncConnectAuthUi);

async function saveConnectFields() {
  syncRemoteDirFromUser();
  const c = document.getElementById("connect-form");
  const s = document.getElementById("settings-form");
  const launch = document.getElementById("launch-form");
  const host = getSelectedHost();
  if (!host) throw new Error("Choose a login node hostname");
  await api("/api/config", {
    method: "POST",
    body: JSON.stringify({
      ssh_host: host,
      ssh_hosts: savedHosts,
      ssh_user: c.ssh_user.value.trim(),
      ssh_port: Number(s.ssh_port.value),
      ssh_key_path: storedKeyPath(),
      ssh_password: c.ssh_password.value,
      remote_dir: s.remote_dir.value.trim(),
      listen_host: s.listen_host.value.trim() || "127.0.0.1",
      listen_port: Number(s.listen_port.value) || 8765,
      shutdown_when_idle: s.shutdown_when_idle.checked,
      redeploy_on_connect: document.getElementById("redeploy-on-connect")?.checked || false,
      defaults: {
        cpus: launch.cpus.value,
        mem_gib: launch.mem_gib.value,
        mem: launch.mem_gib.value,
        time: launch.time.value,
        tunnel_name: launch.tunnel_name.value,
        account: launch.account.value,
        partition: launch.partition.value.trim() || "public",
        qos: launch.qos.value,
        gpus: launch.gpus.value.trim(),
        extra_sbatch: launch.extra_sbatch.value.trim(),
        cursor_bin: launch.cursor_bin.value.trim(),
        auth_provider: "github",
      },
    }),
  });
}

document.getElementById("host-select")?.addEventListener("change", onHostSelectChange);

document.getElementById("host-add-btn")?.addEventListener("click", async () => {
  const host = document.getElementById("host-custom-input")?.value.trim();
  if (!host) {
    toast("Enter a hostname first");
    return;
  }
  try {
    const hosts = [...new Set([...savedHosts, host])];
    await api("/api/config", {
      method: "POST",
      body: JSON.stringify({ ssh_hosts: hosts, ssh_host: host }),
    });
    populateHostSelect(hosts, host);
    toast(`Added ${host}`);
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("connect-form").ssh_user.addEventListener("input", () => {
  syncRemoteDirFromUser();
  updateLaunchTunnelNameDefault();
});

document.getElementById("connect-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("connect-btn");
  btn.disabled = true;
  btn.textContent = "Connecting…";
  setConn("", "Connecting…");
  startSetupPoll((msg) => {
    btn.textContent = msg;
    setConn("", msg);
    showSetupStatus(msg);
  });
  try {
    await saveConnectFields();
    const forceDeploy = document.getElementById("redeploy-on-connect")?.checked || false;
    const res = await api("/api/test", {
      method: "POST",
      body: JSON.stringify({ force_deploy: forceDeploy }),
    });
    if (!res.ok) throw new Error(res.error);
    setConnected(true);
    setConn("ok", "Connected");
    const parts = [res.message, res.scripts, res.cursor_cli, res.scripts_error].filter(Boolean);
    toast(parts.join(" · ") || "Connected");
    showTab("running");
    startAutoRefresh();
    updateLaunchTunnelNameDefault();
    loadLaunchPresets();
  } catch (err) {
    setConnected(false);
    setConn("err", "Failed");
    toast(err.message);
  } finally {
    stopSetupPoll();
    hideSetupStatus();
    btn.disabled = false;
    btn.textContent = "Connect";
  }
});

function startHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  const ping = () => fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
  ping();
  heartbeatTimer = setInterval(ping, 8000);
}

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await saveConnectFields();
    showDashboardUrls();
    toast("Advanced settings saved (restart the app if you changed dashboard address/port)");
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("deploy-btn").addEventListener("click", async () => {
  const btn = document.getElementById("deploy-btn");
  btn.disabled = true;
  try {
    await saveConnectFields();
    const res = await api("/api/deploy", { method: "POST", body: JSON.stringify({ force: true }) });
    if (!res.ok) throw new Error(res.error);
    toast(res.message || "Scripts deployed");
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("launch-preset-select")?.addEventListener("change", async (e) => {
  const idx = e.target.value;
  if (idx === "") return;
  const preset = launchPresets[Number(idx)];
  if (!preset?.params) return;
  applyLaunchParams(preset.params, { updateName: false });
  const taken = await getTakenTunnelNames();
  const user = document.getElementById("connect-form")?.ssh_user?.value;
  document.getElementById("launch-form").tunnel_name.value = resolveTunnelName(
    preset.params.tunnel_name || baseTunnelName(user),
    taken
  );
});

document.getElementById("launch-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!connected) {
    toast("Connect first");
    showTab("connect");
    return;
  }
  const btn = document.getElementById("launch-btn");
  btn.disabled = true;
  btn.textContent = "Starting…";
  try {
    await submitLaunchParams(readLaunchForm(), { successVerb: "Started" });
    showTab("running");
    refreshRunning();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Start tunnel";
  }
});

function slurmStateLabel(state) {
  const labels = {
    R: "Running",
    PD: "Pending",
    CG: "Completing",
    CD: "Completed",
    F: "Failed",
    TO: "Timeout",
  };
  return labels[state] || state || "—";
}

function formatStoppedAgo(ts) {
  if (!ts) return "Recently stopped";
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return "Stopped just now";
  if (sec < 3600) return `Stopped ${Math.floor(sec / 60)}m ago`;
  return `Stopped ${Math.floor(sec / 3600)}h ago`;
}

function renderRerunActions(paramsEnc) {
  return `
          <button type="button" class="btn primary run-again-btn" data-params="${paramsEnc}">Run again</button>
          <button type="button" class="btn secondary edit-run-btn" data-params="${paramsEnc}">Edit &amp; run again</button>`;
}

function wireRerunButtons(list) {
  list.querySelectorAll(".run-again-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      try {
        runAgainFromParams(JSON.parse(decodeURIComponent(btn.dataset.params)));
      } catch {
        toast("Could not read saved tunnel settings");
      }
    });
  });
  list.querySelectorAll(".edit-run-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      try {
        editAndRunFromParams(JSON.parse(decodeURIComponent(btn.dataset.params)));
      } catch {
        toast("Could not read saved tunnel settings");
      }
    });
  });
}

function renderRegistrationSection(jobId, tunnelName, tunnelAuth, auth) {
  if (auth?.code && auth?.status === "pending") {
    return `
    <div class="card-register">
      <p class="code-label">GitHub device code</p>
      <div class="device-code-sm">${escapeHtml(auth.code)}</div>
      <button type="button" class="btn primary copy-open-card-btn" data-job-id="${jobId}">Copy code &amp; open GitHub</button>
      <p class="hint tiny">Paste the code on GitHub — this page updates when registration completes.</p>
    </div>`;
  }

  if (auth?.status === "failed") {
    return "";
  }

  if (tunnelAuth?.registered === true) {
    return `
    <div class="card-register card-register-success">
      <p class="register-status-title">Registered on GitHub</p>
      <p class="hint tiny">Open Cursor desktop → <strong>Remote-Tunnels</strong> → ${escapeHtml(tunnelName)}</p>
    </div>`;
  }

  return "";
}

async function refreshRunning() {
  if (!connected) return;
  try {
    const res = await api("/api/status");
    const list = document.getElementById("running-list");
    if (res.ok === false) {
      const msg = res.error || "Could not load tunnel status";
      toast(msg);
      if (!list.querySelector(".tunnel-card")) {
        list.innerHTML = `<p class="hint empty-state">${escapeHtml(msg)}<br>Try <strong>Connect</strong> again or re-deploy scripts.</p>`;
      }
      return;
    }
    const tunnelAuth = res.tunnel_auth || {};
    const running = (res.jobs || []).filter((j) => !j.is_history);
    if (tunnelAuth.registered === true) {
      running.forEach((j) => {
        if (cardAuth[j.job_id]) delete cardAuth[j.job_id];
      });
    }
    const stopped = (res.jobs || []).filter((j) => j.is_history);
    syncRunningClocks(res.jobs || []);
    if (!running.length && !stopped.length) {
      list.innerHTML =
        '<p class="hint empty-state">No tunnels running yet.<br>Tap <strong>Launch</strong> to start one.</p>';
      return;
    }

    const renderRunning = (j) => {
      const name = escapeHtml(j.tunnel_name);
      const rawName = String(j.tunnel_name).replace(/"/g, "&quot;");
      const paramsEnc = encodeJobParams(j);
      const auth = cardAuth[j.job_id];
      const registering = auth?.code && auth?.status === "pending";
      const clusterRegistered = tunnelAuth.registered === true;
      const timerMain = liveRemainingDisplay(j);
      const timerSub =
        j.elapsed && j.time_limit
          ? `${j.elapsed} elapsed · ${j.time_limit} limit`
          : j.elapsed
            ? `${j.elapsed} elapsed`
            : j.time_limit
              ? `${j.time_limit} limit`
              : "";
      return `
      <article class="tunnel-card" data-job-id="${j.job_id}" data-params="${paramsEnc}">
        <div class="tunnel-card-top">
          <div>
            <div class="tunnel-name">${name}</div>
            <div class="tunnel-meta">Job ${j.job_id} · ${escapeHtml(j.partition)} · ${escapeHtml(j.state_label || slurmStateLabel(j.state))}</div>
          </div>
        </div>
        <div class="tunnel-timer">${escapeHtml(timerMain)}</div>
        <div class="tunnel-timer-label">time remaining</div>
        ${timerSub ? `<div class="tunnel-timer-sub">${escapeHtml(timerSub)}</div>` : ""}
        <div class="card-actions card-actions-wrap">
          ${renderRerunActions(paramsEnc)}
          <button type="button" class="btn secondary copy-name-btn" data-name="${rawName}">Copy tunnel name</button>
          ${
            !clusterRegistered && !registering
              ? `<button type="button" class="btn secondary register-github-btn" data-job-id="${j.job_id}" data-tunnel="${rawName}">Register on GitHub</button>`
              : ""
          }
          <button type="button" class="btn danger stop-job-btn" data-job-id="${j.job_id}">Stop</button>
        </div>
        ${renderRegistrationSection(j.job_id, j.tunnel_name, tunnelAuth, auth)}
      </article>`;
    };

    const renderStopped = (j) => {
      const name = escapeHtml(j.tunnel_name);
      const rawName = String(j.tunnel_name).replace(/"/g, "&quot;");
      const paramsEnc = encodeJobParams(j);
      const spec = [
        j.params?.cpus ? `${j.params.cpus} CPUs` : "",
        j.params?.mem_gib || j.params?.mem ? `${j.params.mem_gib || j.params.mem} mem` : "",
        j.params?.time ? j.params.time : "",
      ]
        .filter(Boolean)
        .join(" · ");
      return `
      <article class="tunnel-card stopped" data-job-id="${j.job_id}" data-params="${paramsEnc}">
        <div class="tunnel-card-top">
          <div>
            <div class="tunnel-name">${name}</div>
            <div class="tunnel-meta">Job ${j.job_id} · stopped</div>
          </div>
          <div class="tunnel-card-top-actions">
            <span class="state state-stopped">Stopped</span>
            <button type="button" class="dismiss-card-btn" data-job-id="${j.job_id}" title="Remove from list" aria-label="Remove">×</button>
          </div>
        </div>
        <div class="tunnel-timer stopped-label">${escapeHtml(formatStoppedAgo(j.stopped_at))}</div>
        <div class="tunnel-timer-label">recent tunnel</div>
        ${spec ? `<div class="tunnel-timer-sub">${escapeHtml(spec)}</div>` : ""}
        <div class="card-actions card-actions-wrap">
          ${renderRerunActions(paramsEnc)}
          <button type="button" class="btn secondary copy-name-btn" data-name="${rawName}">Copy tunnel name</button>
        </div>
      </article>`;
    };

    let html = "";
    if (running.length) {
      html += running.map(renderRunning).join("");
    }
    if (stopped.length) {
      html += '<p class="section-label">Recent Tunnels</p>';
      html += stopped.map(renderStopped).join("");
    }
    if (!running.length && stopped.length) {
      html =
        '<p class="hint empty-state">No tunnels running.<br>Resubmit a recent one below or use <strong>Launch</strong>.</p>' +
        html;
    }
    list.innerHTML = html;

    list.querySelectorAll(".copy-name-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(btn.dataset.name);
          toast("Tunnel name copied — paste in Cursor Remote-Tunnels");
        } catch {
          toast(`Copy: ${btn.dataset.name}`);
        }
      });
    });

    list.querySelectorAll(".register-github-btn").forEach((btn) => {
      btn.addEventListener("click", () => registerOnCard(btn.dataset.jobId, btn.dataset.tunnel, btn));
    });

    list.querySelectorAll(".copy-open-card-btn").forEach((btn) => {
      btn.addEventListener("click", () => copyOpenCardAuth(btn.dataset.jobId));
    });

    list.querySelectorAll(".stop-job-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest(".tunnel-card");
        let params = null;
        try {
          if (card?.dataset.params) params = JSON.parse(decodeURIComponent(card.dataset.params));
        } catch { /* ignore */ }
        stopTunnel(
          btn.dataset.jobId,
          {
            tunnel_name: card?.querySelector(".tunnel-name")?.textContent?.trim() || "",
            params,
          },
          btn,
        );
      });
    });

    list.querySelectorAll(".dismiss-card-btn").forEach((btn) => {
      btn.addEventListener("click", () => dismissStoppedCard(btn.dataset.jobId));
    });

    wireRerunButtons(list);
  } catch (err) {
    toast(err.message);
  }
}

async function registerOnCard(jobId, tunnelName, btn) {
  btn.disabled = true;
  btn.textContent = "Getting code…";
  startSetupPoll((msg) => {
    btn.textContent = msg;
  });
  try {
    const res = await api("/api/auth/start", {
      method: "POST",
      body: JSON.stringify({ provider: "github" }),
    });
    if (!res.ok) throw new Error(res.error);
    cardAuth[jobId] = {
      code: res.code,
      url: res.url,
      session_id: res.session_id,
      status: "pending",
      tunnel_name: tunnelName,
      notified: false,
    };
    startAuthPoll();
    refreshRunning();
  } catch (err) {
    toast(err.message);
    btn.disabled = false;
    btn.textContent = "Register on GitHub";
  } finally {
    stopSetupPoll();
  }
}

async function copyOpenCardAuth(jobId) {
  const auth = cardAuth[jobId];
  if (!auth?.code) return toast("Get a code first");
  try {
    await navigator.clipboard.writeText(auth.code);
    toast("Code copied");
  } catch {
    toast(`Copy manually: ${auth.code}`);
  }
  window.open(auth.url || "https://github.com/login/device", "_blank", "noopener,noreferrer");
}

function startAuthPoll() {
  if (authPollTimer) return;
  authPollTimer = setInterval(pollAuthSessions, 3000);
}

async function pollAuthSessions() {
  const sessions = Object.entries(cardAuth).filter(([, a]) => a.session_id && a.status === "pending");
  if (!sessions.length) {
    if (authPollTimer) {
      clearInterval(authPollTimer);
      authPollTimer = null;
    }
    return;
  }
  for (const [jobId, auth] of sessions) {
    try {
      const res = await api(`/api/auth/status?session_id=${encodeURIComponent(auth.session_id)}`);
      if (res.status === "complete" || res.status === "failed") {
        cardAuth[jobId].status = res.status;
        if (res.status === "complete" && !cardAuth[jobId].notified) {
          cardAuth[jobId].notified = true;
          toast(`GitHub registration complete — connect to ${cardAuth[jobId].tunnel_name || "your tunnel"}`);
        } else if (res.status === "failed" && !cardAuth[jobId].notified) {
          cardAuth[jobId].notified = true;
          toast("GitHub registration failed — try again");
        }
        refreshRunning();
      }
    } catch { /* ignore */ }
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function stopTunnel(jobId, meta = {}, btn = null) {
  const ok = await confirmDialog(`Stop tunnel job ${jobId}?`, { confirmLabel: "Stop", danger: true });
  if (!ok) return;
  const prevLabel = btn?.textContent;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Stopping…";
  }
  try {
    const res = await api("/api/stop", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, ...meta }),
    });
    if (!res.ok) throw new Error(res.error);
    delete cardAuth[jobId];
    toast(res.message);
    refreshRunning();
  } catch (err) {
    toast(err.message);
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevLabel || "Stop";
    }
  }
}

async function dismissStoppedCard(jobId) {
  try {
    const res = await api("/api/history/dismiss", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId }),
    });
    if (!res.ok) throw new Error(res.error);
    toast("Removed from recent tunnels");
    refreshRunning();
  } catch (err) {
    toast(err.message);
  }
}

document.getElementById("refresh-btn").addEventListener("click", refreshRunning);
document.getElementById("disconnect-btn").addEventListener("click", disconnect);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && Object.values(cardAuth).some((a) => a?.status === "pending")) {
    pollAuthSessions();
    startAuthPoll();
  }
});

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  if (clockTimer) clearInterval(clockTimer);
  refreshTimer = setInterval(() => {
    if (connected && document.getElementById("panel-running").classList.contains("active")) {
      refreshRunning();
    }
  }, 12000);
  clockTimer = setInterval(tickRunningTimers, 1000);
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister()));
}

loadConfigIntoForms()
  .then(() => {
    updateGates();
    showTab("connect");
    startHeartbeat();
  })
  .catch((err) => toast(err.message));
