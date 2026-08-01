(() => {
  const cfg = window.PUBLIC_VIEWER_CONFIG || {};
  const TOKEN_KEY = "kmv_admin_token";
  const TOKEN_EXP_KEY = "kmv_admin_token_exp";
  const DEFAULT_SESSION_TTL_MS = 10 * 60 * 1000;
  let apiBase = String(cfg.ADMIN_API_BASE_URL || "").replace(/\/+$/, "");
  let logoutTimer = null;
  let countdownTimer = null;

  const loginPanel = document.getElementById("loginPanel");
  const menuPanel = document.getElementById("menuPanel");
  const loginForm = document.getElementById("loginForm");
  const passwordInput = document.getElementById("passwordInput");
  const togglePasswordBtn = document.getElementById("togglePasswordBtn");
  const loginStatus = document.getElementById("loginStatus");
  const menuStatus = document.getElementById("menuStatus");
  const sessionHint = document.getElementById("sessionHint");
  const loginBtn = document.getElementById("loginBtn");
  const btnMorningBulk = document.getElementById("btnMorningBulk");
  const btnModemReboot = document.getElementById("btnModemReboot");
  const btnOpsLogs = document.getElementById("btnOpsLogs");
  const btnLogout = document.getElementById("btnLogout");
  const logsPanel = document.getElementById("logsPanel");
  const logsList = document.getElementById("logsList");
  const logsMeta = document.getElementById("logsMeta");
  const logsStatus = document.getElementById("logsStatus");
  const btnLogsRefresh = document.getElementById("btnLogsRefresh");
  const btnLogsClose = document.getElementById("btnLogsClose");

  // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
  const btnTenkaiSim = document.getElementById("btnTenkaiSim");
  const tenkaiSimPanel = document.getElementById("tenkaiSimPanel");
  const tenkaiSimMeta = document.getElementById("tenkaiSimMeta");
  const tenkaiSimStatus = document.getElementById("tenkaiSimStatus");
  const tenkaiVenueTabs = document.getElementById("tenkaiVenueTabs");
  const tenkaiJumpButtons = document.getElementById("tenkaiJumpButtons");
  const btnTenkaiClose = document.getElementById("btnTenkaiClose");
  const adminShell = document.getElementById("adminApp");
  let tenkaiSnap = null;
  let tenkaiPlace = null;
  let tenkaiUrlTemplate = "";
  let discoveryCache = null;
  // --- END TEMP: TENKAI_SIM_LAUNCH ---

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("is-error", "is-ok");
    if (kind === "error") el.classList.add("is-error");
    if (kind === "ok") el.classList.add("is-ok");
  }

  /** 全角英数・空白を半角へ（IME誤入力対策）。大文字小文字は維持。 */
  function normalizePassword(raw) {
    return String(raw || "")
      .replace(/[\uFF01-\uFF5E]/g, (ch) =>
        String.fromCharCode(ch.charCodeAt(0) - 0xfee0)
      )
      .replace(/\u3000/g, " ")
      .replace(/[\r\n]+/g, "");
  }

  function getToken() {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  }

  function getTokenExp() {
    try {
      return Number(sessionStorage.getItem(TOKEN_EXP_KEY) || 0) || 0;
    } catch {
      return 0;
    }
  }

  function setToken(token, expiresInSec) {
    try {
      if (token) {
        sessionStorage.setItem(TOKEN_KEY, token);
        const ttl = Math.max(1, Number(expiresInSec) || DEFAULT_SESSION_TTL_MS / 1000);
        sessionStorage.setItem(TOKEN_EXP_KEY, String(Date.now() + ttl * 1000));
      } else {
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem(TOKEN_EXP_KEY);
      }
    } catch {
      /* ignore */
    }
  }

  function clearSessionTimers() {
    if (logoutTimer) {
      clearTimeout(logoutTimer);
      logoutTimer = null;
    }
    if (countdownTimer) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function updateSessionHint() {
    if (!sessionHint) return;
    const exp = getTokenExp();
    const leftMs = exp - Date.now();
    if (!getToken() || leftMs <= 0) {
      sessionHint.textContent =
        "セッションはログインから10分で自動ログアウトします。開始した処理はログアウト後もサーバー上で継続します。";
      return;
    }
    const sec = Math.ceil(leftMs / 1000);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    sessionHint.textContent =
      `自動ログアウトまで 残り ${m}:${String(s).padStart(2, "0")}。` +
      "開始した処理はログアウト後もサーバー上で継続します。";
  }

  function armSessionExpiry(reason) {
    clearSessionTimers();
    const exp = getTokenExp();
    const left = exp - Date.now();
    if (!getToken() || left <= 0) {
      forceLogout(reason || "セッションの有効期限が切れました。再ログインしてください。");
      return;
    }
    updateSessionHint();
    countdownTimer = setInterval(updateSessionHint, 1000);
    logoutTimer = setTimeout(() => {
      forceLogout("ログインから10分経過したため自動ログアウトしました。開始済みの処理はサーバー上で継続しています。");
    }, left);
  }

  function showLogin() {
    loginPanel.hidden = false;
    menuPanel.hidden = true;
    if (logsPanel) logsPanel.hidden = true;
    // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
    hideTenkaiSimPanel();
    // --- END TEMP: TENKAI_SIM_LAUNCH ---
  }

  function showMenu() {
    loginPanel.hidden = true;
    menuPanel.hidden = false;
    if (logsPanel) logsPanel.hidden = true;
  }

  function showLogsPanel() {
    loginPanel.hidden = true;
    menuPanel.hidden = false;
    if (logsPanel) logsPanel.hidden = false;
    // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
    hideTenkaiSimPanel();
    // --- END TEMP: TENKAI_SIM_LAUNCH ---
  }

  function eventLabel(event) {
    const map = {
      admin_login: "ログイン",
      admin_logout: "ログアウト",
      admin_morning_bulk_rerun: "一斉予想再実行",
      admin_modem_reboot: "モデム再起動",
    };
    return map[event] || event || "(不明)";
  }

  function statusClass(status) {
    const s = String(status || "").toLowerCase();
    if (s === "ok" || s === "info") return s === "ok" ? "is-ok" : "";
    if (s === "error" || s === "fail" || s === "banned") return `is-${s === "banned" ? "banned" : s === "fail" ? "fail" : "error"}`;
    if (s === "warn" || s === "warning") return "is-warn";
    return "";
  }

  function renderOpsLogs(entries) {
    if (!logsList) return;
    logsList.innerHTML = "";
    if (!entries.length) {
      logsList.innerHTML = '<p class="admin-hint">該当するログはありません。</p>';
      return;
    }
    const frag = document.createDocumentFragment();
    for (const row of entries) {
      const item = document.createElement("article");
      item.className = "admin-log-item";
      const meta = document.createElement("div");
      meta.className = "admin-log-meta";
      const ts = document.createElement("span");
      ts.textContent = row.ts || "";
      const ev = document.createElement("span");
      ev.className = "admin-log-event";
      ev.textContent = eventLabel(row.event);
      const st = document.createElement("span");
      st.className = `admin-log-status ${statusClass(row.status)}`.trim();
      st.textContent = row.status || "";
      const src = document.createElement("span");
      src.textContent = row.source || "";
      meta.append(ts, ev, st, src);
      if (row.ip) {
        const ip = document.createElement("span");
        ip.textContent = row.ip;
        meta.append(ip);
      }
      const detail = document.createElement("p");
      detail.className = "admin-log-detail";
      detail.textContent = row.detail || "";
      item.append(meta, detail);
      frag.append(item);
    }
    logsList.append(frag);
  }

  async function loadOpsLogs() {
    setStatus(logsStatus, "読み込み中…");
    if (logsMeta) logsMeta.textContent = "過去24時間の動作を取得しています…";
    btnOpsLogs.disabled = true;
    btnLogsRefresh.disabled = true;
    try {
      const token = getToken();
      if (!token) {
        await forceLogout("セッションがありません。再ログインしてください。");
        return;
      }
      const { res, data } = await api("/admin/ops-logs", { token });
      if (res.status === 401) {
        await forceLogout("セッションが切れました。再ログインしてください。");
        return;
      }
      if (!res.ok || !data.ok) {
        setStatus(logsStatus, data.message || "ログ取得に失敗しました", "error");
        return;
      }
      const entries = Array.isArray(data.entries) ? data.entries : [];
      renderOpsLogs(entries);
      if (logsMeta) {
        logsMeta.textContent = `過去${data.hours || 24}時間 / ${data.count ?? entries.length}件（新しい順）`;
      }
      setStatus(logsStatus, "", "ok");
    } catch (e) {
      setStatus(logsStatus, e.message || String(e), "error");
    } finally {
      btnOpsLogs.disabled = false;
      btnLogsRefresh.disabled = false;
    }
  }

  async function forceLogout(message) {
    const token = getToken();
    clearSessionTimers();
    setToken("");
    showLogin();
    if (token) {
      try {
        await api("/admin/logout", { method: "POST", token, silent: true });
      } catch {
        /* ignore */
      }
    }
    setStatus(loginStatus, message || "ログアウトしました", "ok");
  }

  async function resolveApiBase({ force = false } = {}) {
    if (apiBase && !force) return apiBase;
    const configured = String(cfg.ADMIN_API_BASE_URL || "").replace(/\/+$/, "");
    if (configured && !force) {
      apiBase = configured;
      return apiBase;
    }
    const discovery = String(cfg.ADMIN_API_DISCOVERY_URL || "").trim();
    if (!discovery) {
      throw new Error("管理APIのURLが未設定です（ADMIN_API_BASE_URL / DISCOVERY）。");
    }
    const res = await fetch(`${discovery}${discovery.includes("?") ? "&" : "?"}t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(
        "管理API接続情報を取得できませんでした。サーバーのトンネルサービスを確認してください。"
      );
    }
    const data = await res.json();
    // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
    discoveryCache = data && typeof data === "object" ? data : null;
    // --- END TEMP: TENKAI_SIM_LAUNCH ---
    const url = String((data && data.base_url) || "").replace(/\/+$/, "");
    if (!url) {
      throw new Error("管理API接続情報に base_url がありません。");
    }
    apiBase = url;
    return apiBase;
  }

  // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
  function tenkaiEnabled() {
    return cfg.SHOW_TENKAI_SIM_LAUNCH !== false;
  }

  function hideTenkaiSimPanel() {
    if (tenkaiSimPanel) tenkaiSimPanel.hidden = true;
    if (adminShell) adminShell.classList.remove("is-tenkai-open");
  }

  function jumpClass(rank) {
    const r = Number(rank);
    if (r >= 1 && r <= 5) return "jump rank-hi";
    if (r >= 6 && r <= 10) return "jump rank-mid";
    return "jump";
  }

  async function resolveTenkaiUrlTemplate() {
    const fromCfg = String(cfg.TENKAI_SIM_URL_TEMPLATE || "").trim();
    if (fromCfg) return fromCfg;
    try {
      await resolveApiBase();
    } catch {
      /* ignore */
    }
    if (discoveryCache && discoveryCache.tenkai_sim_url_template) {
      return String(discoveryCache.tenkai_sim_url_template).trim();
    }
    if (discoveryCache && discoveryCache.tenkai_sim_base_url) {
      const base = String(discoveryCache.tenkai_sim_base_url).replace(/\/+$/, "");
      return `${base}/tenkai?race_id={race_id}`;
    }
    if (apiBase) return `${apiBase}/tenkai?race_id={race_id}`;
    return "";
  }

  function buildTenkaiSimUrl(race) {
    const tpl = tenkaiUrlTemplate || "";
    if (!tpl || !race) return "";
    const scheduleDate =
      (tenkaiSnap && tenkaiSnap.schedule_date) ||
      String((race && race.schedule_date) || "");
    const rn = String(race.R || "").replace(/[Rr]$/, "");
    const place = String(race.place || tenkaiPlace || "");
    const raceId = String(race.race_id || "");
    const enc = {
      "{race_id}": encodeURIComponent(raceId),
      "{place}": encodeURIComponent(place),
      "{venue}": encodeURIComponent(place),
      "{R}": encodeURIComponent(rn),
      "{race_no}": encodeURIComponent(rn),
      "{schedule_date}": encodeURIComponent(scheduleDate),
      "{kaisai_date}": encodeURIComponent(scheduleDate),
    };
    return Object.keys(enc).reduce((out, key) => out.split(key).join(enc[key]), tpl);
  }

  function openTenkaiSim(race) {
    const url = buildTenkaiSimUrl(race);
    if (!url) {
      setStatus(
        tenkaiSimStatus,
        "シミュレーションURLが未設定です。config.js の TENKAI_SIM_URL_TEMPLATE か discovery の tenkai_sim_url_template を設定してください。",
        "error"
      );
      return;
    }
    const win = window.open(url, "_blank", "noopener,noreferrer");
    if (!win) {
      setStatus(tenkaiSimStatus, "ポップアップがブロックされました。許可して再試行してください。", "error");
      return;
    }
    const rn = String(race.R || "").replace(/[Rr]$/, "") || "-";
    setStatus(tenkaiSimStatus, `${race.place || ""} ${rn}R を別タブで開きました`, "ok");
  }

  function renderTenkaiVenueTabs() {
    if (!tenkaiVenueTabs) return;
    tenkaiVenueTabs.innerHTML = "";
    const venues = (tenkaiSnap && tenkaiSnap.venues) || [];
    if (!venues.length) {
      tenkaiVenueTabs.innerHTML = "<span class='hint'>会場データがありません</span>";
      return;
    }
    if (!tenkaiPlace || !venues.some((v) => v.place === tenkaiPlace)) {
      tenkaiPlace = venues[0].place;
    }
    for (const v of venues) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tab" + (v.place === tenkaiPlace ? " active" : "");
      b.textContent = v.place;
      b.setAttribute("aria-pressed", v.place === tenkaiPlace ? "true" : "false");
      b.addEventListener("click", () => {
        tenkaiPlace = v.place;
        renderTenkaiVenueTabs();
        renderTenkaiJumps();
      });
      tenkaiVenueTabs.appendChild(b);
    }
  }

  function renderTenkaiJumps() {
    if (!tenkaiJumpButtons) return;
    tenkaiJumpButtons.innerHTML = "";
    const venues = (tenkaiSnap && tenkaiSnap.venues) || [];
    const venue = venues.find((v) => v.place === tenkaiPlace) || null;
    const races = (venue && venue.races) || [];
    if (!races.length) {
      tenkaiJumpButtons.innerHTML = "<p class='hint'>この会場のレースがありません</p>";
      return;
    }
    for (const r of races) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = jumpClass(r.holmes_index_rank);
      const rn = String(r.R || "").replace(/[Rr]$/, "") || "-";
      b.textContent = `${rn}R`;
      const tip =
        r.holmes_rank_text && r.holmes_rank_text !== "算出前"
          ? `${r.place} ${rn}R（${r.holmes_rank_text}）`
          : `${r.place} ${rn}R`;
      b.title = tip;
      b.addEventListener("click", () => openTenkaiSim(r));
      tenkaiJumpButtons.appendChild(b);
    }
  }

  async function loadTenkaiSnapshot() {
    const url = String(cfg.SNAPSHOT_URL || "").trim();
    if (!url || url.includes("YOUR_")) {
      throw new Error("SNAPSHOT_URL が未設定です");
    }
    const res = await fetch(`${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`予想データ取得失敗 (HTTP ${res.status})`);
    const data = await res.json();
    const venues = Array.isArray(data.venues) ? data.venues : [];
    const raceCount = Number(data.race_count || 0);
    const nRaces = venues.reduce((acc, v) => acc + ((v && v.races) || []).length, 0);
    if (!nRaces || raceCount === 0) {
      const err = new Error("当日予想データがありません（race_count=0）");
      err.code = "no_races";
      throw err;
    }
    return data;
  }

  async function showTenkaiSimPanel() {
    if (!tenkaiEnabled() || !tenkaiSimPanel) return;
    if (logsPanel) logsPanel.hidden = true;
    tenkaiSimPanel.hidden = false;
    if (adminShell) adminShell.classList.add("is-tenkai-open");
    setStatus(tenkaiSimStatus, "読み込み中…");
    if (tenkaiSimMeta) {
      tenkaiSimMeta.textContent =
        "当日予想データから会場・レースを選ぶと、別タブでシミュレーションを開きます。";
    }
    try {
      tenkaiUrlTemplate = await resolveTenkaiUrlTemplate();
      tenkaiSnap = await loadTenkaiSnapshot();
      renderTenkaiVenueTabs();
      renderTenkaiJumps();
      const n = Number(tenkaiSnap.race_count || 0);
      if (tenkaiSimMeta) {
        tenkaiSimMeta.textContent =
          `開催日 ${tenkaiSnap.schedule_date || "-"} / ${n}レース` +
          (tenkaiUrlTemplate ? "" : "（URLテンプレート未解決）");
      }
      setStatus(
        tenkaiSimStatus,
        tenkaiUrlTemplate
          ? "レースボタンを押すと別タブで開きます"
          : "URLテンプレート未設定です。TENKAI_SIM_URL_TEMPLATE を確認してください。",
        tenkaiUrlTemplate ? "ok" : "error"
      );
    } catch (e) {
      tenkaiSnap = null;
      if (tenkaiVenueTabs) tenkaiVenueTabs.innerHTML = "";
      if (tenkaiJumpButtons) tenkaiJumpButtons.innerHTML = "";
      const msg =
        e && e.code === "no_races"
          ? "当日予想データがありません。一斉予想後に再度お試しください。"
          : e.message || String(e);
      if (tenkaiSimMeta) tenkaiSimMeta.textContent = msg;
      setStatus(tenkaiSimStatus, msg, "error");
    }
  }

  function initTenkaiSimLaunch() {
    if (!tenkaiEnabled()) {
      if (btnTenkaiSim) btnTenkaiSim.hidden = true;
      hideTenkaiSimPanel();
      return;
    }
    if (btnTenkaiSim) {
      btnTenkaiSim.hidden = false;
      btnTenkaiSim.addEventListener("click", async () => {
        await showTenkaiSimPanel();
      });
    }
    if (btnTenkaiClose) {
      btnTenkaiClose.addEventListener("click", () => {
        hideTenkaiSimPanel();
        setStatus(menuStatus, "");
      });
    }
  }
  // --- END TEMP: TENKAI_SIM_LAUNCH ---

  async function api(path, { method = "GET", body, token, silent = false, retryDiscover = true } = {}) {
    const base = await resolveApiBase();
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    let res;
    try {
      res = await fetch(`${base}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        mode: "cors",
        cache: "no-store",
      });
    } catch (err) {
      if (retryDiscover) {
        apiBase = "";
        await resolveApiBase({ force: true });
        return api(path, { method, body, token, silent, retryDiscover: false });
      }
      const msg = silent
        ? String(err)
        : `通信エラー: ${err && err.message ? err.message : err}（API: ${base}）`;
      throw new Error(msg);
    }
    let data = {};
    const text = await res.text();
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = {
        ok: false,
        message: `サーバー応答が不正です (HTTP ${res.status}): ${text.slice(0, 120)}`,
      };
    }
    return { res, data };
  }

  async function refreshSession() {
    const token = getToken();
    if (!token) {
      showLogin();
      return false;
    }
    if (getTokenExp() && Date.now() >= getTokenExp()) {
      await forceLogout("セッションの有効期限が切れました。再ログインしてください。");
      return false;
    }
    try {
      const { res, data } = await api("/admin/session", { token });
      if (!res.ok || !data.ok) {
        await forceLogout("セッションが無効です。再ログインしてください。");
        return false;
      }
      if (typeof data.expires_in === "number" && data.expires_in >= 0) {
        setToken(token, data.expires_in);
      }
      showMenu();
      armSessionExpiry();
      return true;
    } catch (e) {
      showLogin();
      setStatus(loginStatus, e.message || String(e), "error");
      return false;
    }
  }

  togglePasswordBtn.addEventListener("click", () => {
    const show = passwordInput.type === "password";
    passwordInput.type = show ? "text" : "password";
    togglePasswordBtn.textContent = show ? "隠す" : "表示";
    togglePasswordBtn.setAttribute("aria-pressed", show ? "true" : "false");
    togglePasswordBtn.setAttribute("aria-label", show ? "パスワードを隠す" : "パスワードを表示");
    passwordInput.focus();
  });

  loginForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    setStatus(loginStatus, "ログイン中…");
    loginBtn.disabled = true;
    try {
      // 毎回最新のトンネルURLを取り直す
      apiBase = String(cfg.ADMIN_API_BASE_URL || "").replace(/\/+$/, "");
      await resolveApiBase({ force: !apiBase });
      const password = normalizePassword(passwordInput.value);
      if (!password) {
        setStatus(loginStatus, "パスワードを入力してください", "error");
        return;
      }
      const { res, data } = await api("/admin/login", {
        method: "POST",
        body: { password },
        retryDiscover: true,
      });
      if (!res.ok || !data.ok) {
        let detail = data.message || `ログインに失敗しました (HTTP ${res.status})`;
        if (data.error === "ip_banned") {
          detail = data.message || "連続失敗のためこのIPは一時的にアクセス禁止です";
        } else if (data.error === "session_held_by_other_ip") {
          detail =
            data.message ||
            "別のIPでログイン中のため、この端末ではログインできません。";
        }
        setStatus(loginStatus, detail, "error");
        return;
      }
      if (!data.token) {
        setStatus(loginStatus, "ログイン応答にトークンがありません", "error");
        return;
      }
      const ttl = Number(data.session_ttl_sec || data.expires_in || 600);
      setToken(data.token, ttl);
      passwordInput.value = "";
      passwordInput.type = "password";
      togglePasswordBtn.textContent = "表示";
      setStatus(menuStatus, "ログインしました", "ok");
      showMenu();
      armSessionExpiry();
    } catch (e) {
      setStatus(loginStatus, e.message || String(e), "error");
    } finally {
      loginBtn.disabled = false;
    }
  });

  async function runAction(btn, path, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setStatus(menuStatus, "実行中…");
    btn.disabled = true;
    try {
      const token = getToken();
      if (!token) {
        await forceLogout("セッションがありません。再ログインしてください。");
        return;
      }
      const { res, data } = await api(path, { method: "POST", token });
      if (res.status === 401) {
        await forceLogout("セッションが切れました。開始済みの処理はサーバー上で継続している場合があります。再ログインしてください。");
        return;
      }
      if (!res.ok || !data.ok) {
        setStatus(menuStatus, data.message || "実行に失敗しました", "error");
        return;
      }
      setStatus(menuStatus, data.message || "完了しました", "ok");
    } catch (e) {
      setStatus(menuStatus, e.message || String(e), "error");
    } finally {
      btn.disabled = false;
    }
  }

  btnMorningBulk.addEventListener("click", () => {
    runAction(
      btnMorningBulk,
      "/admin/morning-bulk-rerun",
      "一斉予想を再実行します。ログアウト後もサーバー上で処理は継続します。よろしいですか？"
    );
  });

  btnModemReboot.addEventListener("click", () => {
    runAction(
      btnModemReboot,
      "/admin/modem-reboot",
      "モデムを再起動します。通信が一時的に切れます。ログアウト後も再起動処理は継続します。よろしいですか？"
    );
  });

  // --- BEGIN TEMP: TENKAI_SIM_LAUNCH ---
  initTenkaiSimLaunch();
  // --- END TEMP: TENKAI_SIM_LAUNCH ---

  btnOpsLogs.addEventListener("click", async () => {
    showLogsPanel();
    await loadOpsLogs();
  });

  btnLogsRefresh.addEventListener("click", async () => {
    await loadOpsLogs();
  });

  btnLogsClose.addEventListener("click", () => {
    if (logsPanel) logsPanel.hidden = true;
    setStatus(menuStatus, "");
  });

  btnLogout.addEventListener("click", async () => {
    await forceLogout(
      "ログアウトしました。開始済みの処理はサーバー上で継続しています。"
    );
  });

  showLogin();
  setStatus(loginStatus, "接続準備中…");
  resolveApiBase({ force: true })
    .then(() => {
      setStatus(loginStatus, "");
      return refreshSession();
    })
    .catch((e) => {
      showLogin();
      setStatus(loginStatus, e.message || String(e), "error");
    });
})();
