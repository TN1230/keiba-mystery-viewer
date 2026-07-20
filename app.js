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
      sui: "推",
      holmes_index: "ホームズ指数",
      ワ: "ワ(ワトソン)",
      アイ: "アイ(アイリーン)",
      モ: "モ(モーリアティ)",
      "ハ/ホプ": "ハ/ホプ",
    };
    let html = "<table class='matrix'><thead><tr>";
    for (const c of cols) html += `<th>${labels[c] || c}</th>`;
    html += "</tr></thead><tbody>";
    for (const row of v.matrix) {
      const sel = String(row.race_id) === String(state.raceId) ? " selected" : "";
      html += `<tr class="${sel}" data-rid="${row.race_id}">`;
      for (const c of cols) {
        html += `<td>${escapeHtml(row[c] ?? "-")}</td>`;
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    wrap.innerHTML = html;
    wrap.querySelectorAll("tr[data-rid]").forEach((tr) => {
      tr.addEventListener("click", () => selectRace(tr.getAttribute("data-rid"), state.place));
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
      b.addEventListener("click", () => selectRace(r.race_id, state.place));
      box.appendChild(b);
    }
  }

  function selectRace(raceId, place) {
    state.raceId = raceId;
    if (place) state.place = place;
    renderTabs();
    renderMatrix();
    renderJumps();
    renderDetail();
    $("raceDetailCard").scrollIntoView({ behavior: "smooth", block: "start" });
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
      <p class="meta">推奨ロジック: ${escapeHtml(r.best_logic_label || "-")}</p>
      <div class="marks">
    `;
    for (const [k, label] of [["ワ", "ワトソン"], ["アイ", "アイリーン"], ["モ", "モーリアティ"], ["ハ/ホプ", "ハ/ホプ"]]) {
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

  function applyData(data) {
    state.data = data;
    $("updatedAt").textContent = data.updated_at
      ? `最終更新: ${data.updated_at}（開催日 ${data.schedule_date || "-"}）`
      : "更新時刻不明";
    renderTop5();
    renderTabs();
    renderMatrix();
    renderJumps();
    if (state.raceId) renderDetail();
  }

  async function loadSnapshot() {
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
      applyData(data);
    } catch (e) {
      $("updatedAt").innerHTML = `<span class="error">スナップショット取得失敗: ${escapeHtml(e.message || e)}</span>`;
    }
  }

  setCtas();
  loadSnapshot();
  const poll = Number(cfg.POLL_INTERVAL_MS) || 60000;
  if (poll > 0) setInterval(loadSnapshot, poll);
})();
