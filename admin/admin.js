(() => {
  const cfg = window.PUBLIC_VIEWER_CONFIG || {};
  const TOKEN_KEY = "kmv_admin_token";
  let apiBase = String(cfg.ADMIN_API_BASE_URL || "").replace(/\/+$/, "");

  const loginPanel = document.getElementById("loginPanel");
  const menuPanel = document.getElementById("menuPanel");
  const loginForm = document.getElementById("loginForm");
  const passwordInput = document.getElementById("passwordInput");
  const loginStatus = document.getElementById("loginStatus");
  const menuStatus = document.getElementById("menuStatus");
  const loginBtn = document.getElementById("loginBtn");
  const btnMorningBulk = document.getElementById("btnMorningBulk");
  const btnModemReboot = document.getElementById("btnModemReboot");
  const btnLogout = document.getElementById("btnLogout");

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("is-error", "is-ok");
    if (kind === "error") el.classList.add("is-error");
    if (kind === "ok") el.classList.add("is-ok");
  }

  function getToken() {
    try {
      return sessionStorage.getItem(TOKEN_KEY) || "";
    } catch {
      return "";
    }
  }

  function setToken(token) {
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  }

  function showLogin() {
    loginPanel.hidden = false;
    menuPanel.hidden = true;
  }

  function showMenu() {
    loginPanel.hidden = true;
    menuPanel.hidden = false;
  }

  async function resolveApiBase() {
    if (apiBase) return apiBase;
    const discovery = String(cfg.ADMIN_API_DISCOVERY_URL || "").trim();
    if (!discovery) {
      throw new Error("管理APIのURLが未設定です（ADMIN_API_BASE_URL / DISCOVERY）。");
    }
    const res = await fetch(discovery, { cache: "no-store" });
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

  async function api(path, { method = "GET", body, token } = {}) {
    const base = await resolveApiBase();
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${base}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      mode: "cors",
      cache: "no-store",
    });
    let data = {};
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    return { res, data };
  }

  async function refreshSession() {
    const token = getToken();
    if (!token) {
      showLogin();
      return false;
    }
    try {
      const { res, data } = await api("/admin/session", { token });
      if (!res.ok || !data.ok) {
        setToken("");
        showLogin();
        return false;
      }
      showMenu();
      return true;
    } catch (e) {
      showLogin();
      setStatus(loginStatus, e.message || String(e), "error");
      return false;
    }
  }

  loginForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    setStatus(loginStatus, "");
    loginBtn.disabled = true;
    try {
      const password = passwordInput.value;
      const { res, data } = await api("/admin/login", {
        method: "POST",
        body: { password },
      });
      if (!res.ok || !data.ok) {
        setStatus(loginStatus, data.message || "ログインに失敗しました", "error");
        return;
      }
      setToken(data.token || "");
      passwordInput.value = "";
      setStatus(menuStatus, "ログインしました", "ok");
      showMenu();
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
      const { res, data } = await api(path, { method: "POST", token });
      if (res.status === 401) {
        setToken("");
        showLogin();
        setStatus(loginStatus, "セッションが切れました。再ログインしてください。", "error");
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
      "一斉予想を再実行します。よろしいですか？"
    );
  });

  btnModemReboot.addEventListener("click", () => {
    runAction(
      btnModemReboot,
      "/admin/modem-reboot",
      "モデムを再起動します。通信が一時的に切れます。よろしいですか？"
    );
  });

  btnLogout.addEventListener("click", async () => {
    const token = getToken();
    try {
      if (token) await api("/admin/logout", { method: "POST", token });
    } catch {
      /* ignore */
    }
    setToken("");
    setStatus(loginStatus, "ログアウトしました", "ok");
    showLogin();
  });

  showLogin();
  setStatus(loginStatus, "接続準備中…");
  resolveApiBase()
    .then(() => {
      setStatus(loginStatus, "");
      return refreshSession();
    })
    .catch((e) => {
      showLogin();
      setStatus(loginStatus, e.message || String(e), "error");
    });
})();
