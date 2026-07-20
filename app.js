(() => {
  const cfg = window.PUBLIC_VIEWER_CONFIG || {};
  const state = {
    data: null,
    place: null,
    raceId: null,
  };

  const $ = (id) => document.getElementById(id);

  function setCtas() {
    const line = $("lineCta");
    const disc = $("discordCta");
    if (cfg.BRAND_NAME) $("brandName").textContent = cfg.BRAND_NAME;
    if (cfg.LINE_FRIEND_URL && !String(cfg.LINE_FRIEND_URL).includes("YOUR_")) {
      line.href = cfg.LINE_FRIEND_URL;
    } else {
      line.setAttribute("aria-disabled", "true");
      line.title = "config.js の LINE_FRIEND_URL を設定してください";
    }
    if (cfg.DISCORD_INVITE_URL && !String(cfg.DISCORD_INVITE_URL).includes("YOUR_")) {
      disc.href = cfg.DISCORD_INVITE_URL;
    } else {
      disc.setAttribute("aria-disabled", "true");
      disc.title = "config.js の DISCORD_INVITE_URL を設定してください";
    }
  }

  function venues() {
    return (state.data && state.data.venues) || [];
  }

  function findRace(raceId) {
    for (const v of venues()) {
      for (const r of v.races || []) {
        if (String(r.race_id) === String(raceId)) return { venue: v, race: r };
      }
    }
    return null;
  }

  function renderTop5() {
    const ol = $("top5List");
    ol.innerHTML = "";
    const items = (state.data && state.data.top5) || [];
    if (!items.length) {
      ol.innerHTML = "<li>候補なし（予想済みレースを待ってください）</li>";
      return;
    }
    for (const it of items) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = "#raceDetailCard";
      a.textContent = it.line || `${it.place} ${it.R}R`;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        selectRace(it.race_id, it.place);
      });
      li.appendChild(a);
      ol.appendChild(li);
    }
  }

  function renderTabs() {
    const tabs = $("venueTabs");
    tabs.innerHTML = "";
    const list = venues();
    if (!list.length) {
      tabs.innerHTML = "<span class='hint'>会場データがありません</span>";
      return;
    }
    if (!state.place || !list.some((v) => v.place === state.place)) {
      state.place = list[0].place;
    }
    for (const v of list) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tab" + (v.place === state.place ? " active" : "");
      b.textContent = v.place;
      b.addEventListener("click", () => {
        state.place = v.place;
        renderTabs();
        renderMatrix();
        renderJumps();
      });
      tabs.appendChild(b);
    }
  }

  function currentVenue() {
    return venues().find((v) => v.place === state.place) || null;
  }

  function renderMatrix() {
    const wrap = $("matrixWrap");
    const v = currentVenue();
    if (!v || !(v.matrix || []).length) {
      wrap.innerHTML = "<p class='hint'>マトリクスなし</p>";
      return;
    }
    const cols = ["race", "dev", "sui", "holmes_index", "ワ", "アイ", "モ", "ハ/ホプ"];
    const labels = {
      race: "Race",
      dev: "偏差",
      sui: "ホームズ推",
      holmes_index: "ホームズ指数",
      ワ: "ワトソン",
      アイ: "アイリーン",
      モ: "モーリアティ",
      "ハ/ホプ": "ハンター/ホプキンス",
    };
    let table = "<div class='matrix-desktop'><div class='table-wrap'><table class='matrix'><thead><tr>";
    for (const c of cols) table += `<th>${labels[c] || c}</th>`;
    table += "</tr></thead><tbody>";
    let cards = "<div class='matrix-mobile'>";
    for (const row of v.matrix) {
      const sel = String(row.race_id) === String(state.raceId) ? " selected" : "";
      table += `<tr class="${sel}" data-rid="${row.race_id}">`;
      for (const c of cols) {
        table += `<td>${escapeHtml(row[c] ?? "-")}</td>`;
      }
      table += "</tr>";
      cards += `
        <button type="button" class="matrix-card${sel}" data-rid="${escapeAttr(row.race_id)}">
          <p class="matrix-card-title">${escapeHtml(row.race || "-")}</p>
          <div class="matrix-card-grid">
            <div><span>偏差</span><strong>${escapeHtml(row.dev ?? "-")}</strong></div>
            <div><span>ホームズ推</span><strong>${escapeHtml(row.sui ?? "-")}</strong></div>
            <div class="matrix-card-full"><span>ホームズ指数</span><strong>${escapeHtml(row.holmes_index ?? "-")}</strong></div>
            <div><span>ワトソン</span><strong>${escapeHtml(row["ワ"] ?? "-")}</strong></div>
            <div><span>アイリーン</span><strong>${escapeHtml(row["アイ"] ?? "-")}</strong></div>
            <div><span>モーリアティ</span><strong>${escapeHtml(row["モ"] ?? "-")}</strong></div>
            <div><span>ハンター/ホプキンス</span><strong>${escapeHtml(row["ハ/ホプ"] ?? "-")}</strong></div>
          </div>
        </button>`;
    }
    table += "</tbody></table></div></div>";
    cards += "</div>";
    wrap.innerHTML = table + cards;
    wrap.querySelectorAll("[data-rid]").forEach((el) => {
      el.addEventListener("click", () => selectRace(el.getAttribute("data-rid"), state.place));
    });
  }

  function jumpClass(rank) {
    const r = Number(rank);
    if (r >= 1 && r <= 5) return "jump rank-hi";
    if (r >= 6 && r <= 10) return "jump rank-mid";
    return "jump";
  }

  function renderJumps() {
    const box = $("jumpButtons");
    box.innerHTML = "";
    const v = currentVenue();
    if (!v) return;
    for (const r of v.races || []) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = jumpClass(r.holmes_index_rank);
      const rn = String(r.R || "").replace(/[Rr]$/, "") || "-";
      b.textContent = `${rn}R`;
      const tip = r.holmes_rank_text && r.holmes_rank_text !== "算出前"
        ? `${r.place} ${rn}R（${r.holmes_rank_text}）`
        : `${r.place} ${rn}R`;
      b.title = tip;
      b.addEventListener("click", () => selectRace(r.race_id, state.place, { scroll: false }));
      box.appendChild(b);
    }
  }

  function selectRace(raceId, place, opts = {}) {
    state.raceId = raceId;
    if (place) state.place = place;
    renderTabs();
    renderMatrix();
    renderJumps();
    renderDetail();
    openAccordion("race");
    if (opts.scroll !== false) {
      $("raceDetailCard").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function renderDetail() {
    const box = $("raceDetail");
    const found = findRace(state.raceId);
    if (!found) {
      box.innerHTML = "<p class='hint'>マトリクスの行またはジャンプボタンでレースを選ぶと表示されます。</p>";
      return;
    }
    const r = found.race;
    const marks = r.marks || {};
    const cells = r.cells || {};
    let html = `
      <h3>${escapeHtml(r.place)} ${escapeHtml(r.R)}R ${escapeHtml(r.name || "")}</h3>
      <p class="meta">発走 ${escapeHtml(r.start_time || "-")} ／ 天気:${escapeHtml(r.weather || "-")} 馬場:${escapeHtml(r.baba || "-")}</p>
      <p class="meta">期待値偏差: <strong>${escapeHtml(r.dev)}</strong>（ランク ${escapeHtml(r.rank || "-")}）</p>
      <p class="meta">ホームズ指数: <strong>${escapeHtml(r.holmes_index)}</strong> ／ 当日レース内順位: <strong>${escapeHtml(r.holmes_rank_text || "算出前")}</strong></p>
      <p class="meta">ホームズ推奨: ${escapeHtml(r.best_logic_label || "-")}</p>
      <div class="marks">
    `;
    for (const [k, label] of [["ワ", "ワトソン"], ["アイ", "アイリーン"], ["モ", "モーリアティ"], ["ハ/ホプ", "ハンター/ホプキンス"]]) {
      html += `<div class="mark-box"><strong>${label}</strong>${escapeHtml(cells[k] || "-")}<br/><span>${escapeHtml(marks[k] || "-")}</span></div>`;
    }
    html += "</div><div class='pdf-links'>";
    if (r.pdf_url) html += `<a href="${escapeAttr(r.pdf_url)}" target="_blank" rel="noopener">予想詳細PDF</a>`;
    if (r.help_pdf_url) html += `<a href="${escapeAttr(r.help_pdf_url)}" target="_blank" rel="noopener">項目説明PDF</a>`;
    if (!r.pdf_url && !r.help_pdf_url) html += "<span class='hint'>PDFはまだ公開されていません</span>";
    html += "</div>";
    box.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function applyData(data, { flash = false } = {}) {
    const prevUpdated = state.data && state.data.updated_at;
    state.data = data;
    const el = $("updatedAt");
    const text = data.updated_at
      ? `最終更新: ${data.updated_at}（開催日 ${data.schedule_date || "-"}）`
      : "更新時刻不明";
    el.textContent = text;
    if (flash && prevUpdated && data.updated_at && prevUpdated !== data.updated_at) {
      el.classList.add("just-updated");
      window.setTimeout(() => el.classList.remove("just-updated"), 2500);
    }
    renderTop5();
    renderTabs();
    renderMatrix();
    renderJumps();
    if (state.raceId) renderDetail();
  }

  async function loadSnapshot({ silent = false } = {}) {
    const url = cfg.SNAPSHOT_URL;
    if (!url || String(url).includes("YOUR_PROJECT")) {
      $("updatedAt").innerHTML = "<span class='error'>config.js の SNAPSHOT_URL を設定してください</span>";
      return;
    }
    try {
      const resp = await fetch(url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(), {
        cache: "no-store",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      applyData(data, { flash: silent });
    } catch (e) {
      if (!silent) {
        $("updatedAt").innerHTML = `<span class="error">スナップショット取得失敗: ${escapeHtml(e.message || e)}</span>`;
      }
    }
  }

  const ACC_STORAGE_KEY = "pv_acc_state_v1";
  const ACC_MQ = window.matchMedia("(max-width: 720px)");

  function isMobileAcc() {
    return ACC_MQ.matches;
  }

  function isPcCollapsible(section) {
    return !!(section && section.classList.contains("acc-pc"));
  }

  function canToggleAcc(section) {
    return isMobileAcc() || isPcCollapsible(section);
  }

  function readAccPrefs() {
    try {
      return JSON.parse(sessionStorage.getItem(ACC_STORAGE_KEY) || "{}") || {};
    } catch (_) {
      return {};
    }
  }

  function writeAccPrefs(prefs) {
    try {
      sessionStorage.setItem(ACC_STORAGE_KEY, JSON.stringify(prefs));
    } catch (_) {}
  }

  function setAccordionOpen(section, open, persist) {
    if (!section) return;
    section.classList.toggle("is-open", open);
    section.classList.toggle("is-closed", !open);
    const btn = section.querySelector(".acc-toggle");
    if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
    if (persist && canToggleAcc(section)) {
      const key = section.getAttribute("data-acc");
      if (!key) return;
      const prefs = readAccPrefs();
      prefs[key] = open;
      writeAccPrefs(prefs);
    }
  }

  function openAccordion(key) {
    if (!isMobileAcc()) return;
    const section = document.querySelector(`.acc[data-acc="${key}"]`);
    setAccordionOpen(section, true, true);
  }

  function applyAccordionDefaults() {
    const toolbar = $("accToolbar");
    const prefs = readAccPrefs();
    document.querySelectorAll(".acc[data-acc]").forEach((section) => {
      const key = section.getAttribute("data-acc");
      let open;
      if (!isMobileAcc() && !isPcCollapsible(section)) {
        open = true;
      } else if (Object.prototype.hasOwnProperty.call(prefs, key)) {
        open = !!prefs[key];
      } else {
        open = section.getAttribute("data-default") !== "closed";
      }
      setAccordionOpen(section, open, false);
    });
    if (toolbar) toolbar.hidden = !isMobileAcc();
  }

  function initAccordion() {
    document.querySelectorAll(".acc[data-acc]").forEach((section) => {
      const btn = section.querySelector(".acc-toggle");
      if (!btn) return;
      btn.addEventListener("click", () => {
        if (!canToggleAcc(section)) return;
        const next = !section.classList.contains("is-open");
        setAccordionOpen(section, next, true);
      });
    });
    const openAll = $("accOpenAll");
    const closeSecondary = $("accCloseSecondary");
    if (openAll) {
      openAll.addEventListener("click", () => {
        document.querySelectorAll(".acc[data-acc]").forEach((section) => {
          setAccordionOpen(section, true, true);
        });
      });
    }
    if (closeSecondary) {
      closeSecondary.addEventListener("click", () => {
        document.querySelectorAll('.acc[data-default="closed"]').forEach((section) => {
          setAccordionOpen(section, false, true);
        });
        document.querySelectorAll('.acc[data-default="open"]').forEach((section) => {
          setAccordionOpen(section, true, true);
        });
      });
    }
    applyAccordionDefaults();
    const onChange = () => applyAccordionDefaults();
    if (ACC_MQ.addEventListener) ACC_MQ.addEventListener("change", onChange);
    else if (ACC_MQ.addListener) ACC_MQ.addListener(onChange);
  }

  setCtas();
  initAccordion();
  loadSnapshot();
  const poll = Number(cfg.POLL_INTERVAL_MS) || 30000;
  if (poll > 0) {
    window.setInterval(() => loadSnapshot({ silent: true }), poll);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadSnapshot({ silent: true });
  });
})();
