(() => {
  const cfg = window.PUBLIC_VIEWER_CONFIG || {};
  const SHUTUBA_SORT_KEY = "mystery_viewer_shutuba_sort";
  const JUMP_LAYOUT_KEY = "mystery_viewer_jump_layout";

  function loadShutubaSort() {
    try {
      const v = localStorage.getItem(SHUTUBA_SORT_KEY);
      if (v === "umaban" || v === "default") return v;
    } catch (_) {
      /* ignore */
    }
    return "default";
  }

  function loadJumpLayout() {
    try {
      const v = localStorage.getItem(JUMP_LAYOUT_KEY);
      if (v === "timeline" || v === "venue") return v;
    } catch (_) {
      /* ignore */
    }
    return "venue";
  }

  const state = {
    data: null,
    place: null,
    raceId: null,
    shutubaSort: loadShutubaSort(),
    jumpLayout: loadJumpLayout(),
  };

  const $ = (id) => document.getElementById(id);

  function syncShutubaSortControls() {
    const sortDefault = state.shutubaSort !== "umaban";
    document.querySelectorAll("[data-shutuba-sort]").forEach((btn) => {
      const mode = btn.getAttribute("data-shutuba-sort");
      const active = sortDefault ? mode === "default" : mode === "umaban";
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const hint = $("shutubaSortHint");
    if (hint) {
      hint.textContent = sortDefault
        ? "推定3着内率の高い順"
        : "馬番の小さい順";
    }
  }

  function setShutubaSort(mode) {
    state.shutubaSort = mode === "umaban" ? "umaban" : "default";
    try {
      localStorage.setItem(SHUTUBA_SORT_KEY, state.shutubaSort);
    } catch (_) {
      /* ignore */
    }
    syncShutubaSortControls();
    renderShutuba();
  }

  function setCtas() {
    const disc = $("discordCta");
    if (cfg.BRAND_NAME) {
      const brand = $("brandName");
      if (brand) {
        const img = brand.querySelector("img.brand-logo-img");
        if (img) img.alt = cfg.BRAND_NAME;
        else brand.textContent = cfg.BRAND_NAME;
      }
    }
    if (!disc) return;
    if (cfg.DISCORD_INVITE_URL && !String(cfg.DISCORD_INVITE_URL).includes("YOUR_")) {
      disc.href = cfg.DISCORD_INVITE_URL;
      disc.removeAttribute("aria-disabled");
      disc.removeAttribute("title");
    } else {
      disc.href = "#";
      disc.setAttribute("aria-disabled", "true");
      disc.title = "config.js の DISCORD_INVITE_URL を設定してください";
    }
  }

  /** config.SHOW_CAST_ICONS=false で旧テキストのみ表示に戻せる */
  function applyCastIconMode() {
    const hide = cfg.SHOW_CAST_ICONS === false;
    document.documentElement.classList.toggle("hide-cast-icons", hide);
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

  function formatHolmesIndexDisplay(r) {
    if (!r) return "-";
    if (typeof r.holmes_index_display === "string" && r.holmes_index_display.trim()) {
      return r.holmes_index_display.trim();
    }
    const latest = r.holmes_index == null || r.holmes_index === "" ? "-" : String(r.holmes_index);
    const morning = r.morning_holmes_index;
    if (morning == null || morning === "") return latest;
    const d = r.holmes_index_delta;
    let dtxt = "　Δ±0";
    if (typeof d === "number" && Number.isFinite(d)) {
      dtxt = d > 0 ? `　Δ+${d}` : d < 0 ? `　Δ${d}` : "　Δ±0";
    } else if (String(morning) !== latest) {
      dtxt = "";
    }
    return `${latest}（朝一 ${morning}${dtxt}）`;
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
      const idxDisp = formatHolmesIndexDisplay(it);
      if (idxDisp && idxDisp !== "-") a.title = `ホームズ指数 ${idxDisp}`;
      a.addEventListener("click", (e) => {
        e.preventDefault();
        selectRace(it.race_id, it.place);
      });
      li.appendChild(a);
      ol.appendChild(li);
    }
  }

  function allRaces() {
    const out = [];
    for (const v of venues()) {
      const place = v && v.place;
      for (const r of v.races || []) {
        // 発走表グリッドは place 必須。レース側に無いときは会場名で補う
        out.push(r.place ? r : { ...r, place });
      }
    }
    return out;
  }

  function normalizeStartTime(st) {
    const m = String(st || "").trim().match(/^(\d{1,2}):(\d{2})/);
    if (!m) return "";
    return `${String(m[1]).padStart(2, "0")}:${m[2]}`;
  }

  function raceStartDate(race, scheduleDate) {
    const hm = normalizeStartTime(race && race.start_time);
    const day = String(scheduleDate || (state.data && state.data.schedule_date) || "").trim();
    if (!hm || !/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
    const d = new Date(`${day}T${hm}:00+09:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  /** 最終更新時刻以降で、最も近い未発走レース */
  function nearestPrepostRace(raceList) {
    const list = Array.isArray(raceList) ? raceList : allRaces();
    const updatedRaw = state.data && state.data.updated_at;
    let ref = updatedRaw ? new Date(updatedRaw) : new Date();
    if (Number.isNaN(ref.getTime())) ref = new Date();
    // updated_at がタイムゾーン無しのとき JST として扱う
    if (updatedRaw && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(String(updatedRaw))) {
      const m = String(updatedRaw).match(
        /^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)/
      );
      if (m) {
        const t = new Date(`${m[1]}T${m[2].length === 5 ? `${m[2]}:00` : m[2]}+09:00`);
        if (!Number.isNaN(t.getTime())) ref = t;
      }
    }
    const day = state.data && state.data.schedule_date;
    let best = null;
    let bestDiff = Infinity;
    for (const r of list) {
      const t = raceStartDate(r, day);
      if (!t) continue;
      const diff = t.getTime() - ref.getTime();
      if (diff > 0 && diff < bestDiff) {
        bestDiff = diff;
        best = r;
      }
    }
    return best;
  }

  function fillVenueTabs(container) {
    if (!container) return;
    container.innerHTML = "";
    const list = venues();
    if (!list.length) {
      container.innerHTML = "<span class='hint'>会場データがありません</span>";
      return;
    }
    if (!state.place || !list.some((v) => v.place === state.place)) {
      state.place = list[0].place;
    }
    const nearest = nearestPrepostRace();
    const nearestPlace = nearest && nearest.place;
    // 発走表モードでは会場タブはマトリクス用のため残す（ジャンプ本体は全場スコアボード）
    container.hidden = false;
    for (const v of list) {
      const b = document.createElement("button");
      b.type = "button";
      let cls = "tab" + (v.place === state.place ? " active" : "");
      if (nearestPlace && v.place === nearestPlace) cls += " is-nearest-prepost";
      b.className = cls;
      b.textContent = v.place;
      b.setAttribute("aria-pressed", v.place === state.place ? "true" : "false");
      b.addEventListener("click", () => {
        state.place = v.place;
        renderTabs();
        renderMatrix();
        renderJumps();
      });
      container.appendChild(b);
    }
  }

  function renderTabs() {
    fillVenueTabs($("venueTabs"));
    fillVenueTabs($("venueTabsSidebar"));
  }

  function currentVenue() {
    return venues().find((v) => v.place === state.place) || null;
  }

  function matrixSuiLabel(raw) {
    const s = String(raw || "").trim();
    if (!s || s === "-") return "-";
    const map = {
      ワ: "ワトソン",
      アイ: "アイリーン",
      モ: "モーリアティ",
      モリ: "モーリアティ",
      ハ: "ハンター",
      ホプ: "ホプキンス",
      "ハ/ホプ": "ハンター",
    };
    return map[s] || s;
  }

  function thirdDetectiveLabel(row) {
    const mapPresence = (raw) => {
      const s = String(raw || "").trim();
      if (!s || s === "-") return "";
      if (s === "モーリアティ" || s === "モリ" || s.includes("モーリ")) return "モーリアティ";
      if (s === "ホプキンス" || s === "ホプ" || s.includes("ホプキンス") || s.includes("新馬")) return "ホプキンス";
      if (s === "ハンター" || s === "ハ" || s.includes("ハンター") || s.includes("夏")) return "ハンター";
      // 旧スナップショットの買/様子ラベルはモーリアティ列由来とみなす
      if (s.includes("買") || s.includes("様子") || s.includes("見送")) return "モーリアティ";
      return "";
    };

    const cur = row && row["第3探偵"];
    const fromCur = mapPresence(cur);
    if (fromCur) return fromCur;

    const candidates = [
      row && row["モ"],
      row && (row["ハ/ホプ"] || row["ハ"] || row["ホプ"]),
      row && row.cells && (row.cells["モ"] || row.cells["モーリアティ"]),
      row && row.cells && (row.cells["ハ/ホプ"] || row.cells["ハンター"] || row.cells["ホプキンス"]),
    ];
    for (const c of candidates) {
      const n = mapPresence(c);
      if (n) return n;
    }
    return cur || "-";
  }

  function matrixCell(row, fullKey, shortKey) {
    const v = row && (row[fullKey] ?? row[shortKey]);
    return v == null || v === "" ? "-" : v;
  }

  function renderMatrix() {
    const wrap = $("matrixWrap");
    const v = currentVenue();
    if (!v || !(v.matrix || []).length) {
      wrap.innerHTML = "<p class='hint'>マトリクスなし</p>";
      return;
    }
    const cols = ["race", "dev", "sui", "holmes_index", "ワトソン", "アイリーン", "第3探偵"];
    const labels = {
      race: "Race",
      dev: "偏差",
      sui: "ホームズ推",
      holmes_index: "ホームズ指数",
      ワトソン: "ワトソン",
      アイリーン: "アイリーン",
      第3探偵: "第3探偵",
    };
    let table = "<div class='matrix-desktop'><div class='table-wrap'><table class='matrix'><thead><tr>";
    for (const c of cols) table += `<th>${labels[c] || c}</th>`;
    table += "</tr></thead><tbody>";
    let cards = "<div class='matrix-mobile'>";
    for (const row of v.matrix) {
      const sel = String(row.race_id) === String(state.raceId) ? " selected" : "";
      const third = thirdDetectiveLabel(row);
      const watson = matrixCell(row, "ワトソン", "ワ");
      const irene = matrixCell(row, "アイリーン", "アイ");
      const sui = matrixSuiLabel(row.sui);
      table += `<tr class="${sel}" data-rid="${row.race_id}">`;
      for (const c of cols) {
        let val = "-";
        if (c === "第3探偵") val = third;
        else if (c === "ワトソン") val = watson;
        else if (c === "アイリーン") val = irene;
        else if (c === "sui") val = sui;
        else if (c === "holmes_index") val = formatHolmesIndexDisplay(row);
        else val = row[c] ?? "-";
        table += `<td>${escapeHtml(val)}</td>`;
      }
      table += "</tr>";
      cards += `
        <button type="button" class="matrix-card${sel}" data-rid="${escapeAttr(row.race_id)}">
          <p class="matrix-card-title">${escapeHtml(row.race || "-")}</p>
          <div class="matrix-card-grid">
            <div><span>偏差</span><strong>${escapeHtml(row.dev ?? "-")}</strong></div>
            <div><span>ホームズ推</span><strong>${escapeHtml(sui)}</strong></div>
            <div class="matrix-card-full"><span>ホームズ指数</span><strong>${escapeHtml(formatHolmesIndexDisplay(row))}</strong></div>
            <div><span>ワトソン</span><strong>${escapeHtml(watson)}</strong></div>
            <div><span>アイリーン</span><strong>${escapeHtml(irene)}</strong></div>
            <div class="matrix-card-full"><span>第3探偵</span><strong>${escapeHtml(third)}</strong></div>
          </div>
        </button>`;
    }
    table += "</tbody></table></div></div>";
    cards += "</div>";
    wrap.innerHTML = table + cards;
    wrap.querySelectorAll("[data-rid]").forEach((el) => {
      el.addEventListener("click", () => selectRace(el.getAttribute("data-rid"), state.place, { scroll: false }));
    });
  }

  function jumpClass(rank) {
    const r = Number(rank);
    if (r >= 1 && r <= 5) return "jump rank-hi";
    if (r >= 6 && r <= 10) return "jump rank-mid";
    return "jump";
  }

  function syncJumpLayoutControls() {
    const mode = state.jumpLayout === "timeline" ? "timeline" : "venue";
    document.querySelectorAll("[data-jump-layout]").forEach((btn) => {
      const active = btn.getAttribute("data-jump-layout") === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function setJumpLayout(mode) {
    state.jumpLayout = mode === "timeline" ? "timeline" : "venue";
    try {
      localStorage.setItem(JUMP_LAYOUT_KEY, state.jumpLayout);
    } catch (_) {
      /* ignore */
    }
    syncJumpLayoutControls();
    renderJumps();
  }

  function makeJumpButton(r, { nearestId } = {}) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("data-rid", String(r.race_id || ""));
    b.setAttribute("data-place", String(r.place || ""));
    const selected = String(r.race_id) === String(state.raceId);
    const nearest = nearestId != null && String(r.race_id) === String(nearestId);
    let cls = jumpClass(r.holmes_index_rank);
    if (selected) cls += " is-selected";
    if (nearest) cls += " is-nearest-prepost";
    b.className = cls;
    const rn = String(r.R || "").replace(/[Rr]$/, "") || "-";
    b.textContent = `${rn}R`;
    b.setAttribute("aria-pressed", selected ? "true" : "false");
    const tip = r.holmes_rank_text && r.holmes_rank_text !== "算出前"
      ? `${r.place} ${rn}R ${normalizeStartTime(r.start_time)}（${r.holmes_rank_text}）`
      : `${r.place} ${rn}R ${normalizeStartTime(r.start_time)}`.trim();
    b.title = tip;
    b.addEventListener("click", () => selectRace(r.race_id, r.place, { scroll: false }));
    return b;
  }

  /** 選択状態だけ更新（発走表スクロール位置を維持） */
  function syncJumpSelection() {
    const rid = String(state.raceId || "");
    const place = String(state.place || "");
    document.querySelectorAll(".jump[data-rid]").forEach((b) => {
      const selected = String(b.getAttribute("data-rid") || "") === rid;
      b.classList.toggle("is-selected", selected);
      b.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    document.querySelectorAll(".jump-scoreboard-place").forEach((th) => {
      th.classList.toggle("is-active-place", th.textContent === place);
    });
  }

  function captureJumpScrollPositions() {
    const out = new Map();
    for (const id of ["jumpButtons", "jumpButtonsSidebar"]) {
      const el = $(id);
      if (!el) continue;
      const sc = el.querySelector(".jump-timeline-scroll");
      if (sc) out.set(id, { top: sc.scrollTop, left: sc.scrollLeft });
    }
    return out;
  }

  function restoreJumpScrollPositions(saved) {
    if (!saved || !saved.size) return;
    for (const [id, pos] of saved) {
      const el = $(id);
      const sc = el && el.querySelector(".jump-timeline-scroll");
      if (!sc || !pos) continue;
      sc.scrollTop = pos.top;
      sc.scrollLeft = pos.left;
    }
  }

  function renderJumpsVenue(box, { sidebar }) {
    box.className = sidebar ? "jump-row sidebar-jump-row" : "jump-row";
    box.innerHTML = "";
    const v = currentVenue();
    if (!v) return;
    const nearest = nearestPrepostRace(v.races || []);
    const nearestId = nearest && nearest.race_id;
    for (const r of v.races || []) {
      box.appendChild(makeJumpButton(r, { nearestId }));
    }
  }

  function renderJumpsTimeline(box, { sidebar }) {
    box.className = sidebar ? "jump-timeline sidebar-jump-timeline" : "jump-timeline";
    box.innerHTML = "";
    const placeList = venues().map((v) => v.place).filter(Boolean);
    const races = allRaces();
    if (!placeList.length || !races.length) {
      box.innerHTML = "<p class='hint'>発走表データがありません</p>";
      return;
    }
    const times = [];
    const seen = new Set();
    for (const r of races) {
      const t = normalizeStartTime(r.start_time);
      if (!t || seen.has(t)) continue;
      seen.add(t);
      times.push(t);
    }
    times.sort();
    if (!times.length) {
      box.innerHTML = "<p class='hint'>発走時刻がありません</p>";
      return;
    }

    const byKey = new Map();
    for (const r of races) {
      const t = normalizeStartTime(r.start_time);
      const place = r.place;
      if (!t || !place) continue;
      const key = `${t}||${place}`;
      // 同一時刻・同一場は R 昇順の先頭を採用
      const prev = byKey.get(key);
      if (!prev) {
        byKey.set(key, r);
        continue;
      }
      const rn = Number.parseInt(String(r.R || "").replace(/[Rr]$/, ""), 10);
      const pn = Number.parseInt(String(prev.R || "").replace(/[Rr]$/, ""), 10);
      if (Number.isFinite(rn) && (!Number.isFinite(pn) || rn < pn)) byKey.set(key, r);
    }

    const nearest = nearestPrepostRace(races);
    const nearestId = nearest && nearest.race_id;
    const nearestTime = nearest ? normalizeStartTime(nearest.start_time) : "";

    const scroll = document.createElement("div");
    scroll.className = "jump-timeline-scroll";
    const table = document.createElement("table");
    table.className = "jump-scoreboard";
    table.setAttribute("aria-label", "発走表順レースジャンプ");

    const thead = document.createElement("thead");
    const hr = document.createElement("tr");
    const corner = document.createElement("th");
    corner.className = "jump-scoreboard-corner";
    corner.textContent = "発走";
    hr.appendChild(corner);
    for (const place of placeList) {
      const th = document.createElement("th");
      th.className = "jump-scoreboard-place" + (place === state.place ? " is-active-place" : "");
      th.textContent = place;
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const t of times) {
      const tr = document.createElement("tr");
      if (nearestTime && t === nearestTime) tr.className = "is-nearest-row";
      const th = document.createElement("th");
      th.className = "jump-scoreboard-time";
      th.scope = "row";
      th.textContent = t;
      tr.appendChild(th);
      for (const place of placeList) {
        const td = document.createElement("td");
        const r = byKey.get(`${t}||${place}`);
        if (!r) {
          td.className = "jump-scoreboard-cell is-empty";
          const dot = document.createElement("span");
          dot.className = "jump-scoreboard-dot";
          dot.setAttribute("aria-hidden", "true");
          td.appendChild(dot);
        } else {
          td.className = "jump-scoreboard-cell";
          const inner = document.createElement("div");
          inner.className = "jump-scoreboard-cell-inner";
          inner.appendChild(makeJumpButton(r, { nearestId }));
          td.appendChild(inner);
        }
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    scroll.appendChild(table);
    box.appendChild(scroll);
  }

  function renderJumps() {
    syncJumpLayoutControls();
    const savedScroll = captureJumpScrollPositions();
    const targets = [
      { el: $("jumpButtons"), sidebar: false },
      { el: $("jumpButtonsSidebar"), sidebar: true },
    ];
    const timeline = state.jumpLayout === "timeline";
    for (const { el, sidebar } of targets) {
      if (!el) continue;
      if (timeline) renderJumpsTimeline(el, { sidebar });
      else renderJumpsVenue(el, { sidebar });
    }
    // 再描画で .jump-timeline-scroll が作り直されても位置を戻す
    restoreJumpScrollPositions(savedScroll);
  }

  function initJumpLayoutControls() {
    document.querySelectorAll("[data-jump-layout]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setJumpLayout(btn.getAttribute("data-jump-layout"));
      });
    });
    syncJumpLayoutControls();
  }

  function selectRace(raceId, place, opts = {}) {
    state.raceId = raceId;
    if (place) state.place = place;
    renderTabs();
    renderMatrix();
    // 発走表ボタン欄は全再描画せず選択だけ更新（スクロール位置ジャンプ防止）
    syncJumpSelection();
    renderDetail();
    renderShutuba();
    openAccordion("race");
    if (opts.scroll !== false) {
      $("raceDetailCard").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function castIconSrcForLogic(bestLogic, bestLogicLabel) {
    const label = String(bestLogicLabel || "");
    const bl = String(bestLogic || "").trim().toLowerCase();
    if (bl === "watson" || /ワトソン/.test(label)) return "assets/cast/watson.png";
    if (bl === "irene" || /アイリーン/.test(label)) return "assets/cast/irene.png";
    if (bl === "moriarty" || /モーリアティ/.test(label)) return "assets/cast/moriarty.png";
    if (/ホプキンス/.test(label)) return "assets/cast/hopkins.png";
    if (bl === "hunter" || /ハンター/.test(label)) return "assets/cast/hunter.png";
    return "";
  }

  function formatHolmesRecommendHtml(r) {
    const label = String((r && r.best_logic_label) || "-").trim() || "-";
    const icon = castIconSrcForLogic(r && r.best_logic, label);
    if (!icon || label === "-") {
      return `ホームズ推奨: ${escapeHtml(label)}`;
    }
    return (
      `ホームズ推奨: <span class="holmes-recommend">` +
      `<img class="logic-cast-icon holmes-recommend-icon" src="${escapeAttr(icon)}" alt="" width="34" height="34" decoding="async" />` +
      `<strong>${escapeHtml(label)}</strong></span>`
    );
  }

  function formatPredictedAtLabel(raw) {
    if (raw == null || raw === "") return "未更新";
    if (typeof raw === "number" && Number.isFinite(raw)) {
      const d = new Date(raw * (raw < 1e12 ? 1000 : 1));
      if (!Number.isNaN(d.getTime())) {
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
      }
    }
    const s = String(raw).trim();
    if (!s) return "未更新";
    const m = s.match(/^(\d{4}-\d{2}-\d{2})(?:[T\s]+)(\d{2}:\d{2})(?::\d{2})?/);
    if (m) return `${m[1]} ${m[2]}`;
    const m2 = s.match(/^(\d{4}-\d{2}-\d{2})[T\s]+(\d{1,2}:\d{2})/);
    if (m2) return `${m2[1]} ${m2[2]}`;
    return s;
  }

  /** 芝/ダート/障害 + 距離。例: ダート1000m（右）。（不明）はノイズなので付けない。 */
  function formatCourseDistanceLabel(race) {
    if (!race || typeof race !== "object") return "";
    const stripNoiseDiv = (label) =>
      String(label || "")
        .replace(/[（(]\s*(不明|未知|なし|unknown|n\/a|na|none|\?|？)\s*[）)]/gi, "")
        .trim();

    const ready = stripNoiseDiv(race.course_label);
    if (ready) return ready;

    const rawCourse = String(race.course || race.surface || "").trim();
    let surface = "";
    if (/障害|^障/.test(rawCourse)) surface = "障害";
    else if (/ダート|^ダ|dirt/i.test(rawCourse)) surface = "ダート";
    else if (/芝|turf/i.test(rawCourse)) surface = "芝";

    const distRaw = String(race.distance || "").trim() || rawCourse;
    const dm = distRaw.match(/(\d{3,4})\s*m?/i);
    const dist = dm ? dm[1] : "";

    let div = String(race.course_division || "").trim().replace(/^[（(【\[]|[）)】\]]$/g, "");
    if (/直線/.test(div)) div = "直線";
    else if (/右/.test(div)) div = "右";
    else if (/左/.test(div)) div = "左";
    else div = ""; // 不明などは付けない

    if (!surface && !dist) return "";
    let label = surface && dist ? `${surface}${dist}m` : surface || `${dist}m`;
    if ((div === "右" || div === "左" || div === "直線") && !label.includes(div)) {
      label = `${label}（${div}）`;
    }
    return label;
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
    const predictedAtLabel = formatPredictedAtLabel(r.predicted_at);
    const courseLabel = formatCourseDistanceLabel(r);
    const coursePart = courseLabel
      ? ` ／ <span class="race-course">${escapeHtml(courseLabel)}</span>`
      : "";
    const paceLabel = String(r.pace_label || "").trim();
    const paceLine = paceLabel
      ? `<p class="meta race-pace">予想ペース: <strong>${escapeHtml(paceLabel)}</strong></p>`
      : "";
    let html = `
      <h3>${escapeHtml(r.place)} ${escapeHtml(r.R)}R ${escapeHtml(r.name || "")}</h3>
      <p class="meta">発走 ${escapeHtml(r.start_time || "-")}${coursePart} ／ 天気:${escapeHtml(r.weather || "-")} 馬場:${escapeHtml(r.baba || "-")}</p>
      ${paceLine}
      <p class="meta race-predicted-at">予想更新時間: <strong>${escapeHtml(predictedAtLabel)}</strong></p>
      <p class="meta">期待値偏差: <strong>${escapeHtml(r.dev)}</strong>（ランク ${escapeHtml(r.rank || "-")}）</p>
      <p class="meta">ホームズ指数: <strong>${escapeHtml(formatHolmesIndexDisplay(r))}</strong> ／ 当日レース内順位: <strong>${escapeHtml(r.holmes_rank_text || "算出前")}</strong></p>
      <p class="meta">${formatHolmesRecommendHtml(r)}</p>
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

  function markHonmeiClass(col) {
    if (col === "ワトソン") return "mark-honmei mark-w";
    if (col === "アイリーン") return "mark-honmei mark-i";
    if (col === "モーリアティ") return "mark-honmei mark-m";
    return "mark-honmei mark-h";
  }

  function shutubaRowsForDisplay(rows) {
    const list = Array.isArray(rows) ? rows.slice() : [];
    if (state.shutubaSort !== "umaban") return list;
    return list.sort((a, b) => {
      const na = Number.parseInt(String(a && a["馬番"] != null ? a["馬番"] : ""), 10);
      const nb = Number.parseInt(String(b && b["馬番"] != null ? b["馬番"] : ""), 10);
      const va = Number.isFinite(na) ? na : 999;
      const vb = Number.isFinite(nb) ? nb : 999;
      return va - vb;
    });
  }

  function renderShutuba() {
    const box = $("shutubaDetail");
    if (!box) return;
    syncShutubaSortControls();
    const found = findRace(state.raceId);
    if (!found) {
      box.innerHTML = "<p class='hint'>レースを選ぶと出馬表が表示されます。</p>";
      return;
    }
    const shutuba = found.race.shutuba;
    if (!shutuba || !Array.isArray(shutuba.rows) || !shutuba.rows.length) {
      box.innerHTML =
        "<p class='hint'>このレースの出馬表はまだ公開されていません（本体アプリ再公開後に表示されます）。</p>";
      return;
    }
    const cols = Array.isArray(shutuba.columns) ? shutuba.columns : [];
    const markCols = new Set(Array.isArray(shutuba.mark_columns) ? shutuba.mark_columns : []);
    let html = '<div class="table-wrap"><table class="shutuba"><thead><tr>';
    for (const c of cols) {
      html += `<th>${escapeHtml(c)}</th>`;
    }
    html += "</tr></thead><tbody>";
    for (const row of shutubaRowsForDisplay(shutuba.rows)) {
      const st = row._style || {};
      const honmei = st.honmei || {};
      html += `<tr${st.cancel ? ' class="is-cancel"' : ""}>`;
      for (const c of cols) {
        const classes = [];
        let styleAttr = "";
        if (c === "枠番" && st.frame_bg) {
          classes.push("frame-cell");
          styleAttr = ` style="background:${escapeAttr(st.frame_bg)};color:${escapeAttr(st.frame_fg || "#000")}"`;
        }
        if (st.cancel && (c === "馬名" || c === "単勝")) classes.push("cancel-text");
        if (markCols.has(c) && honmei[c]) classes.push(markHonmeiClass(c));
        const cls = classes.length ? ` class="${classes.join(" ")}"` : "";
        html += `<td${cls}${styleAttr}>${escapeHtml(row[c] ?? "")}</td>`;
      }
      html += "</tr>";
    }
    html += "</tbody></table></div>";
    if (!shutuba.predicted) {
      html += '<p class="hint">予想前の出馬表です（印列は予想後に表示されます）。</p>';
    }
    box.innerHTML = html;
  }

  function initShutubaSortControls() {
    document.querySelectorAll("[data-shutuba-sort]").forEach((btn) => {
      btn.addEventListener("click", () => setShutubaSort(btn.getAttribute("data-shutuba-sort")));
    });
    syncShutubaSortControls();
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

  function formatUpdatedAtLabel(raw, scheduleDate) {
    const s = String(raw || "").trim();
    if (!s) return "";
    // ISO / "YYYY-MM-DD HH:MM:SS" / "YYYY-MM-DDTHH:MM:SS(+TZ)"
    const m = s.match(
      /^(\d{4}-\d{2}-\d{2})(?:[T\s]+)(\d{2}:\d{2}(?::\d{2})?)?/
    );
    // 【最終更新日時】であることが一目で分かるよう見出し付きで表示
    const lines = ["【最終更新日時】"];
    if (m) {
      lines.push(`📅${m[1]}`);
      if (m[2]) lines.push(`⏰${m[2]}`);
    } else {
      lines.push(s);
    }
    lines.push(`開催日 ${scheduleDate || "-"}`);
    return lines.join("\n");
  }

  function isDayClosedSnapshot(data) {
    if (!data || typeof data !== "object") return false;
    if (data.cleared === true) return true;
    const venues = Array.isArray(data.venues) ? data.venues : [];
    const n = Number(data.race_count || 0);
    return n === 0 && venues.length === 0;
  }

  function setDayClosedOverlay(on) {
    const overlay = $("dayClosedOverlay");
    document.body.classList.toggle("is-day-closed", !!on);
    if (!overlay) return;
    overlay.hidden = !on;
    overlay.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function renderUpdateTiming(data) {
    const el = $("updateTiming") || document.querySelector(".update-timing");
    if (!el) return;
    // 優先: config.js の PRE_RACE_TRIGGER_MODE（現行運用帯）→ スナップショット → 既定15
    const cfgMode = String(cfg.PRE_RACE_TRIGGER_MODE || "").trim().toLowerCase();
    const snapMode = data && data.pre_race_trigger_mode != null
      ? String(data.pre_race_trigger_mode).trim().toLowerCase()
      : "";
    const mode = cfgMode || snapMode || "15";
    const is15 = mode === "15" || mode === "early" || mode === "15m" || mode === "15min";
    const preLine = is15
      ? "・発走15分前前後（全レース）"
      : "・発走6〜8分前（全レース）";
    // スナップショット全文は、config 未指定かつ mode 一致時のみ採用（古い6_8文面の上書きを防ぐ）
    const full = data && data.update_timing_text;
    if (
      !cfgMode &&
      typeof full === "string" &&
      full.trim() &&
      snapMode &&
      ((is15 && /15/.test(full)) || (!is15 && /6/.test(full)))
    ) {
      el.textContent = full.trim();
      return;
    }
    el.textContent =
      "【主な更新タイミング】\n" +
      "・開催日早朝6時頃（全レース一斉）\n" +
      "・発走1時間前頃（重賞のみ）\n" +
      preLine +
      "\n※更新されない場合は通信障害など運用上のトラブルが発生しております。ご容赦ください";
  }

  function applyData(data, { flash = false } = {}) {
    const prevUpdated = state.data && state.data.updated_at;
    state.data = data;
    const el = $("updatedAt");
    const closed = isDayClosedSnapshot(data);
    setDayClosedOverlay(closed);
    const stamped = formatUpdatedAtLabel(data.updated_at, data.schedule_date);
    const text = closed
      ? `本日の予想公開は終了しました\n開催日 ${data.schedule_date || "-"}`
      : stamped || "更新時刻不明";
    el.textContent = text;
    if (flash && prevUpdated && data.updated_at && prevUpdated !== data.updated_at) {
      el.classList.add("just-updated");
      window.setTimeout(() => el.classList.remove("just-updated"), 2500);
    }
    renderUpdateTiming(data);
    renderTop5();
    renderTabs();
    renderMatrix();
    renderJumps();
    if (state.raceId) {
      renderDetail();
      renderShutuba();
    }
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

  function isMobileOnlyAcc(section) {
    return !!(section && section.classList.contains("acc-mobile-only"));
  }

  function canToggleAcc(section) {
    if (isMobileOnlyAcc(section)) return isMobileAcc();
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
    const btn = section.querySelector(":scope > .acc-toggle");
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
      const btn = section.querySelector(":scope > .acc-toggle");
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
  applyCastIconMode();
  initAccordion();
  initShutubaSortControls();
  initJumpLayoutControls();
  loadSnapshot();
  const poll = Number(cfg.POLL_INTERVAL_MS) || 30000;
  if (poll > 0) {
    window.setInterval(() => loadSnapshot({ silent: true }), poll);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadSnapshot({ silent: true });
  });
})();
