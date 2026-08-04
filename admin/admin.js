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
  const btnForcePublish = document.getElementById("btnForcePublish");
  const btnModemReboot = document.getElementById("btnModemReboot");
  const btnOpsLogs = document.getElementById("btnOpsLogs");
  const btnLogout = document.getElementById("btnLogout");
  const logsPanel = document.getElementById("logsPanel");
  const logsList = document.getElementById("logsList");
  const logsMeta = document.getElementById("logsMeta");
  const logsStatus = document.getElementById("logsStatus");
  const btnLogsRefresh = document.getElementById("btnLogsRefresh");
  const btnLogsClose = document.getElementById("btnLogsClose");
  const btnRaceSim = document.getElementById("btnRaceSim");
  const raceSimPanel = document.getElementById("raceSimPanel");
  const raceSimId = document.getElementById("raceSimId");
  const raceSimWeather = document.getElementById("raceSimWeather");
  const raceSimBaba = document.getElementById("raceSimBaba");
  const raceSimStatus = document.getElementById("raceSimStatus");
  const raceSimLog = document.getElementById("raceSimLog");
  const btnRaceSimRun = document.getElementById("btnRaceSimRun");
  const btnRaceSimOpen = document.getElementById("btnRaceSimOpen");
  const btnRaceSimClose = document.getElementById("btnRaceSimClose");
  const RACE_SIM_JOB_KEY = "kmv_admin_race_sim_job";
  const RACE_SIM_RACE_KEY = "kmv_admin_race_sim_race";
  let raceSimPollTimer = null;


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
    // 生成自体はサーバー側で続くので job_id は残し、画面と監視だけ止める
    if (raceSimPanel) raceSimPanel.hidden = true;
    stopRaceSimPoll();
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
  }

  function eventLabel(event) {
    const map = {
      admin_login: "ログイン",
      admin_logout: "ログアウト",
      admin_morning_bulk_rerun: "一斉予想再実行",
      admin_publish_public_snapshot: "閲覧サイト強制公開",
      admin_remote_bootstrap: "リモート bootstrap",
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
    const url = String((data && data.base_url) || "").replace(/\/+$/, "");
    if (!url) {
      throw new Error("管理API接続情報に base_url がありません。");
    }
    apiBase = url;
    return apiBase;
  }


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

  if (btnForcePublish) {
    btnForcePublish.addEventListener("click", async () => {
      const ok = window.confirm(
        "キャッシュから閲覧サイト（latest.json）を強制公開します。直前予想の取りこぼし解消に使います。よろしいですか？"
      );
      if (!ok) return;
      setStatus(menuStatus, "実行中…");
      btnForcePublish.disabled = true;
      try {
        const token = getToken();
        if (!token) {
          await forceLogout("セッションがありません。再ログインしてください。");
          return;
        }
        // フォールバック先だった /admin/remote-bootstrap は GitHub 上のスクリプトを
        // 実行するエンドポイントとして意図的に削除済みなので呼ばない。
        const { res, data } = await api("/admin/publish-public-snapshot", {
          method: "POST",
          token,
        });
        if (res.status === 401) {
          await forceLogout(
            "セッションが切れました。開始済みの処理はサーバー上で継続している場合があります。再ログインしてください。"
          );
          return;
        }
        if (!res.ok || !data.ok) {
          setStatus(
            menuStatus,
            data.message || data.error || "強制公開に失敗しました",
            "error"
          );
          return;
        }
        const raceCount = data.race_count ?? data.result?.race_count;
        const msg =
          raceCount != null
            ? `公開しました（race_count=${raceCount}）`
            : data.message || "閲覧サイトを公開しました";
        setStatus(menuStatus, msg, "ok");
      } catch (e) {
        setStatus(menuStatus, e.message || String(e), "error");
      } finally {
        btnForcePublish.disabled = false;
      }
    });
  }

  btnModemReboot.addEventListener("click", () => {
    runAction(
      btnModemReboot,
      "/admin/modem-reboot",
      "モデムを再起動します。通信が一時的に切れます。ログアウト後も再起動処理は継続します。よろしいですか？"
    );
  });


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

  /* ---------- ⑤ 展開シミュレーション ---------- */

  function stopRaceSimPoll() {
    if (raceSimPollTimer) {
      clearTimeout(raceSimPollTimer);
      raceSimPollTimer = null;
    }
  }

  /** 全角数字を半角にし、数字以外を落とす。 */
  function normalizeRaceId(raw) {
    return String(raw || "")
      .replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
      .replace(/\D/g, "");
  }

  /** 「展開を開く」は、生成済みジョブと入力欄のレースIDが一致するときだけ押せる。 */
  function syncRaceSimOpenButton() {
    if (!btnRaceSimOpen) return;
    const jobId = sessionStorage.getItem(RACE_SIM_JOB_KEY);
    const jobRace = sessionStorage.getItem(RACE_SIM_RACE_KEY) || "";
    const typed = normalizeRaceId(raceSimId && raceSimId.value);
    const ready = Boolean(jobId) && (!typed || !jobRace || typed === jobRace);
    btnRaceSimOpen.disabled = !ready;
    btnRaceSimOpen.textContent = jobRace ? `展開を開く（${jobRace}）` : "展開を開く";
  }

  function setRaceSimLog(text) {
    if (!raceSimLog) return;
    const t = String(text || "").trim();
    raceSimLog.textContent = t;
    raceSimLog.hidden = !t;
  }

  /** 別タブ表示用に HTML を取得する。認証は既存の Bearer をそのまま使う。 */
  async function fetchRaceSimHtml(jobId, token) {
    const base = await resolveApiBase();
    const res = await fetch(
      `${base}/admin/race-sim/result?job=${encodeURIComponent(jobId)}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        mode: "cors",
        cache: "no-store",
      }
    );
    if (res.status === 401) throw new Error("セッションが切れました。再ログインしてください。");
    if (!res.ok) throw new Error(`まだ生成が終わっていません (HTTP ${res.status})`);
    return res.text();
  }

  async function openRaceSimResult() {
    const jobId = sessionStorage.getItem(RACE_SIM_JOB_KEY);
    const jobRace = sessionStorage.getItem(RACE_SIM_RACE_KEY) || "";
    const token = getToken();
    if (!jobId || !token) {
      setStatus(raceSimStatus, "開ける結果がありません。先に生成してください。", "error");
      return;
    }
    // 入力欄のレースIDを変えただけでは中身は変わらない。取り違えを防ぐ。
    const typed = normalizeRaceId(raceSimId.value);
    if (typed && jobRace && typed !== jobRace) {
      setStatus(
        raceSimStatus,
        `入力欄は ${typed} ですが、生成済みなのは ${jobRace} です。` +
          "このレースを見るには「生成を開始」を押してください。",
        "error"
      );
      return;
    }
    // ポップアップブロック回避のためクリック直後に空タブを開いておく
    const tab = window.open("", "_blank");
    setStatus(raceSimStatus, "展開を読み込み中…");
    try {
      const html = await fetchRaceSimHtml(jobId, token);
      const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      if (tab) {
        tab.location = url;
      } else {
        setStatus(
          raceSimStatus,
          "別タブを開けませんでした。ポップアップを許可してもう一度お試しください。",
          "error"
        );
        return;
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setStatus(raceSimStatus, "別タブに展開を表示しました。", "ok");
    } catch (e) {
      if (tab) tab.close();
      setStatus(raceSimStatus, e.message || String(e), "error");
    }
  }

  async function pollRaceSim(jobId) {
    const token = getToken();
    if (!token) {
      stopRaceSimPoll();
      return;
    }
    const { res, data } = await api(
      `/admin/race-sim/status?job=${encodeURIComponent(jobId)}`,
      { token, silent: true }
    );
    if (res.status === 401) {
      stopRaceSimPoll();
      setStatus(
        raceSimStatus,
        "セッションが切れました。生成はサーバー上で継続しています。再ログイン後に「展開を開く」で表示できます。",
        "error"
      );
      return;
    }
    if (!data || !data.ok) {
      stopRaceSimPoll();
      setStatus(raceSimStatus, (data && data.message) || "状態を取得できませんでした", "error");
      return;
    }
    setRaceSimLog(data.log_tail);
    if (data.state === "done") {
      stopRaceSimPoll();
      btnRaceSimRun.disabled = false;
      syncRaceSimOpenButton();
      setStatus(
        raceSimStatus,
        `レース ${data.race_id} の生成が完了しました。「展開を開く」を押してください。`,
        "ok"
      );
      return;
    }
    if (data.state === "failed") {
      stopRaceSimPoll();
      btnRaceSimRun.disabled = false;
      setStatus(raceSimStatus, data.message || "生成に失敗しました", "error");
      return;
    }
    setStatus(raceSimStatus, data.message || "生成中…");
    raceSimPollTimer = setTimeout(() => pollRaceSim(jobId), 5000);
  }

  btnRaceSim.addEventListener("click", () => {
    if (raceSimPanel) raceSimPanel.hidden = false;
    if (logsPanel) logsPanel.hidden = true;
    setStatus(menuStatus, "");
    syncRaceSimOpenButton();
  });

  btnRaceSimClose.addEventListener("click", () => {
    stopRaceSimPoll();
    if (raceSimPanel) raceSimPanel.hidden = true;
  });

  btnRaceSimRun.addEventListener("click", async () => {
    const rid = normalizeRaceId(raceSimId.value);
    if (rid.length !== 12) {
      setStatus(raceSimStatus, "レースIDは12桁の数字で入力してください。", "error");
      return;
    }
    raceSimId.value = rid;
    const token = getToken();
    if (!token) {
      await forceLogout("セッションがありません。再ログインしてください。");
      return;
    }
    stopRaceSimPoll();
    btnRaceSimRun.disabled = true;
    btnRaceSimOpen.disabled = true;
    sessionStorage.removeItem(RACE_SIM_JOB_KEY);
    sessionStorage.removeItem(RACE_SIM_RACE_KEY);
    setRaceSimLog("");
    setStatus(raceSimStatus, "開始しています…");
    try {
      const { res, data } = await api("/admin/race-sim", {
        method: "POST",
        token,
        body: {
          race_id: rid,
          weather: raceSimWeather.value,
          baba: raceSimBaba.value,
        },
      });
      if (res.status === 401) {
        await forceLogout("セッションが切れました。再ログインしてください。");
        return;
      }
      if (!res.ok || !data.ok) {
        btnRaceSimRun.disabled = false;
        setStatus(raceSimStatus, data.message || "開始できませんでした", "error");
        return;
      }
      sessionStorage.setItem(RACE_SIM_JOB_KEY, data.job_id);
      sessionStorage.setItem(RACE_SIM_RACE_KEY, rid);
      setStatus(raceSimStatus, data.message || "生成中…");
      raceSimPollTimer = setTimeout(() => pollRaceSim(data.job_id), 5000);
    } catch (e) {
      btnRaceSimRun.disabled = false;
      setStatus(raceSimStatus, e.message || String(e), "error");
    }
  });

  btnRaceSimOpen.addEventListener("click", openRaceSimResult);
  raceSimId.addEventListener("input", syncRaceSimOpenButton);

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
