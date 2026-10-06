/**
 * Scheme Board - Frontend Application
 * Vanilla JS, no external dependencies, offline-ready.
 */

(function () {
  "use strict";

  // --- Constants & Config ---
  const CATEGORY_COLORS = {
    ai_automation: "#A78BFA",
    digital_product: "#38BDF8",
    service: "#34D399",
    content_media: "#F472B6",
    e_commerce: "#FBBF24",
    trading_investing: "#4ADE80",
    real_world: "#FB923C",
    community: "#E879F9",
    other: "#94A3B8",
  };

  const CATEGORY_NAMES = {
    ai_automation: "AI & Automation",
    digital_product: "Digital Product",
    service: "Service",
    content_media: "Content & Media",
    e_commerce: "E-Commerce",
    trading_investing: "Trading & Investing",
    real_world: "Real World",
    community: "Community",
    other: "Other",
  };

  const STATUS_COLORS = {
    raw: "#94A3B8",
    developed: "#60A5FA",
    testing: "#FBBF24",
    being_built: "#FF8C42",
    proven: "#34D399",
    dead: "#F87171",
  };

  const CTYPE_COLORS = {
    parallel: "#FF8C42",
    complements: "#4CC9F0",
    same_market: "#B5E48C",
    competes: "#F25C54",
    extends: "#B185DB",
  };

  const SCORE_LABELS = {
    capital: "Capital Req.",
    effort: "Effort Req.",
    time_to_revenue: "Time to Rev.",
    ceiling: "Rev. Ceiling",
    difficulty: "Difficulty",
    moat: "Moat / Defensibility",
    risk: "Downside Risk",
  };

  const ALL_SCORE_KEYS = [
    "capital",
    "effort",
    "time_to_revenue",
    "ceiling",
    "difficulty",
    "moat",
    "risk",
  ];

  // --- State ---
  let state = {
    ideas: [],
    connections: [],
    themes: [],
    stats: null,
    analysisRuns: [],
    activeTab: "map",
    selectedIdeaId: null,
    filters: {
      category: "",
      status: "",
      search: "",
      hideSeeded: false,
    },
    graph: {
      nodes: [],
      edges: [],
      panX: 0,
      panY: 0,
      zoom: 1.0,
      hoveredNode: null,
      draggedNode: null,
      isPanning: false,
      lastMouseX: 0,
      lastMouseY: 0,
      simTicksRemaining: 0,
    },
  };

  // --- DOM Elements ---
  const el = {
    errorBanner: document.getElementById("error-banner"),
    btnRetry: document.getElementById("btn-retry"),
    tabs: document.querySelectorAll(".tab-btn"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    filterCategory: document.getElementById("filter-category"),
    filterStatus: document.getElementById("filter-status"),
    filterSearch: document.getElementById("filter-search"),
    btnClearSearch: document.getElementById("btn-clear-search"),
    filterHideSeeded: document.getElementById("filter-hide-seeded"),
    btnResetFilters: document.getElementById("btn-reset-filters"),
    filteredCountBadge: document.getElementById("filtered-count-badge"),

    // Detail Panel
    detailPanel: document.getElementById("detail-panel"),
    btnClosePanel: document.getElementById("btn-close-panel"),
    panelTitle: document.getElementById("panel-title"),
    panelCategory: document.getElementById("panel-category"),
    panelOwner: document.getElementById("panel-owner"),
    panelSeeded: document.getElementById("panel-seeded"),
    panelStatusSelect: document.getElementById("panel-status-select"),
    panelSummaryField: document.getElementById("panel-summary-field"),
    panelSummary: document.getElementById("panel-summary"),
    panelRaw: document.getElementById("panel-raw"),
    panelTags: document.getElementById("panel-tags"),
    panelScores: document.getElementById("panel-scores"),
    panelOppScore: document.getElementById("panel-opp-score"),
    panelConnections: document.getElementById("panel-connections"),
    panelThemes: document.getElementById("panel-themes"),
    btnDeleteIdea: document.getElementById("btn-delete-idea"),

    // Map
    canvas: document.getElementById("graph-canvas"),
    mapTooltip: document.getElementById("map-tooltip"),
    btnRecenter: document.getElementById("btn-recenter"),
    btnZoomIn: document.getElementById("btn-zoom-in"),
    btnZoomOut: document.getElementById("btn-zoom-out"),

    // List
    ideasTableBody: document.getElementById("ideas-table-body"),
    listEmpty: document.getElementById("list-empty"),

    // Stats
    statTotalIdeas: document.getElementById("stat-total-ideas"),
    statSeededIdeas: document.getElementById("stat-seeded-ideas"),
    statConnectionsCount: document.getElementById("stat-connections-count"),
    statThemesCount: document.getElementById("stat-themes-count"),
    statusChipsContainer: document.getElementById("status-chips-container"),
    categoryChipsContainer: document.getElementById("category-chips-container"),
    rankingTableBody: document.getElementById("ranking-table-body"),
    connectionBarsContainer: document.getElementById("connection-bars-container"),
    themesTableBody: document.getElementById("themes-table-body"),
    runsTableBody: document.getElementById("runs-table-body"),

    // Modal
    btnNewIdea: document.getElementById("btn-new-idea"),
    modalNewIdea: document.getElementById("modal-new-idea"),
    btnCloseModal: document.getElementById("btn-close-modal"),
    btnCancelModal: document.getElementById("btn-cancel-modal"),
    formNewIdea: document.getElementById("form-new-idea"),
    inputTitle: document.getElementById("input-title"),
    inputRaw: document.getElementById("input-raw"),
    inputOwner: document.getElementById("input-owner"),
    inputCategory: document.getElementById("input-category"),
    inputStatus: document.getElementById("input-status"),
  };

  // --- API Functions ---
  async function apiFetch(endpoint, options = {}) {
    const res = await fetch(endpoint, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      let errText = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body.error) errText = body.error;
      } catch (e) {}
      throw new Error(errText);
    }
    if (res.status === 204) return null;
    return await res.json();
  }

  async function loadAllData() {
    try {
      const [ideasData, conns, themes, stats, runs] = await Promise.all([
        apiFetch("/api/ideas"),
        apiFetch("/api/connections"),
        apiFetch("/api/themes"),
        apiFetch("/api/stats"),
        apiFetch("/api/analysis?limit=20"),
      ]);

      state.ideas = ideasData.ideas || ideasData.items || [];
      state.connections = conns || [];
      state.themes = themes || [];
      state.stats = stats || null;
      state.analysisRuns = runs || [];

      el.errorBanner.classList.add("hidden");

      renderAll();
    } catch (err) {
      console.error("Failed to fetch data:", err);
      el.errorBanner.classList.remove("hidden");
    }
  }

  // --- Opportunity Score Calculation ---
  function computeOppScore(scores) {
    if (!scores) return null;
    const isComplete = ALL_SCORE_KEYS.every(
      (k) => scores[k] !== undefined && scores[k] !== null && typeof scores[k] === "number"
    );
    if (!isComplete) return null;
    return (
      scores.ceiling +
      scores.moat -
      scores.capital -
      scores.effort -
      scores.risk
    );
  }

  // --- Filter Logic ---
  function getFilteredIdeas() {
    const { category, status, search, hideSeeded } = state.filters;
    const query = search.toLowerCase().trim();

    return state.ideas.filter((idea) => {
      if (category && idea.category !== category) return false;
      if (status && idea.status !== status) return false;
      if (hideSeeded && idea.seeded) return false;

      if (query) {
        const title = (idea.title || "").toLowerCase();
        const raw = (idea.raw || "").toLowerCase();
        const summary = (idea.summary || "").toLowerCase();
        const owner = (idea.owner || "").toLowerCase();
        const tags = (idea.tags || []).map((t) => t.toLowerCase()).join(" ");

        if (
          !title.includes(query) &&
          !raw.includes(query) &&
          !summary.includes(query) &&
          !owner.includes(query) &&
          !tags.includes(query)
        ) {
          return false;
        }
      }
      return true;
    });
  }

  // --- Render All Views ---
  function renderAll() {
    const filtered = getFilteredIdeas();
    el.filteredCountBadge.textContent = `${filtered.length} of ${state.ideas.length} ideas`;

    renderMap(filtered);
    renderList(filtered);
    renderStats();

    if (state.selectedIdeaId) {
      const selected = state.ideas.find((i) => i.id === state.selectedIdeaId);
      if (selected) {
        showDetailPanel(selected);
      } else {
        closeDetailPanel();
      }
    }
  }

  // --- Detail Panel ---
  function showDetailPanel(idea) {
    state.selectedIdeaId = idea.id;
    el.detailPanel.classList.remove("hidden");

    el.panelTitle.textContent = idea.title;
    el.panelCategory.textContent = CATEGORY_NAMES[idea.category] || idea.category || "uncategorized";
    el.panelCategory.style.borderColor = CATEGORY_COLORS[idea.category] || "var(--border-color)";
    el.panelCategory.style.color = CATEGORY_COLORS[idea.category] || "var(--text-main)";

    el.panelOwner.textContent = `Pitched by ${idea.owner || "C6"}`;

    if (idea.seeded) {
      el.panelSeeded.classList.remove("hidden");
    } else {
      el.panelSeeded.classList.add("hidden");
    }

    el.panelStatusSelect.value = idea.status || "raw";
    el.panelStatusSelect.style.borderColor = STATUS_COLORS[idea.status] || "var(--border-color)";

    if (idea.summary) {
      el.panelSummaryField.classList.remove("hidden");
      el.panelSummary.textContent = idea.summary;
    } else {
      el.panelSummaryField.classList.add("hidden");
    }

    el.panelRaw.textContent = idea.raw;

    // Tags
    el.panelTags.innerHTML = "";
    const tags = idea.tags || [];
    if (tags.length === 0) {
      el.panelTags.innerHTML = '<span class="text-dim">No tags</span>';
    } else {
      tags.forEach((tag) => {
        const badge = document.createElement("span");
        badge.className = "tag-badge";
        badge.textContent = `#${tag}`;
        badge.onclick = (e) => {
          e.stopPropagation();
          state.filters.search = tag;
          el.filterSearch.value = tag;
          el.btnClearSearch.classList.remove("hidden");
          renderAll();
        };
        el.panelTags.appendChild(badge);
      });
    }

    // Scores
    el.panelScores.innerHTML = "";
    const scores = idea.scores || {};
    const opp = computeOppScore(scores);

    if (opp !== null) {
      const sign = opp > 0 ? `+${opp}` : `${opp}`;
      el.panelOppScore.textContent = `Opportunity Score: ${sign}`;
      el.panelOppScore.classList.remove("hidden");
    } else {
      el.panelOppScore.textContent = "Scores incomplete";
      el.panelOppScore.classList.remove("hidden");
    }

    ALL_SCORE_KEYS.forEach((key) => {
      const val = scores[key] !== undefined && scores[key] !== null ? scores[key] : null;
      const row = document.createElement("div");
      row.className = "score-row";

      const label = document.createElement("span");
      label.className = "score-name";
      label.textContent = SCORE_LABELS[key] || key;

      const track = document.createElement("div");
      track.className = "score-track";

      const fill = document.createElement("div");
      fill.className = "score-fill";
      fill.style.width = val !== null ? `${(val / 5) * 100}%` : "0%";

      track.appendChild(fill);

      const valSpan = document.createElement("span");
      valSpan.className = "score-val";
      valSpan.textContent = val !== null ? `${val}` : "—";

      row.appendChild(label);
      row.appendChild(track);
      row.appendChild(valSpan);
      el.panelScores.appendChild(row);
    });

    // Connections
    el.panelConnections.innerHTML = "";
    const relatedConns = state.connections.filter(
      (c) => c.a === idea.id || c.b === idea.id
    );

    if (relatedConns.length === 0) {
      el.panelConnections.innerHTML = '<span class="text-dim">No connections recorded</span>';
    } else {
      relatedConns.forEach((c) => {
        const otherId = c.a === idea.id ? c.b : c.a;
        const otherIdea = state.ideas.find((i) => i.id === otherId);
        const card = document.createElement("div");
        card.className = "connection-card";

        const topRow = document.createElement("div");
        topRow.className = "connection-card-top";

        const link = document.createElement("a");
        link.className = "conn-link";
        link.textContent = otherIdea ? otherIdea.title : `Idea #${otherId}`;
        link.onclick = (e) => {
          e.preventDefault();
          if (otherIdea) {
            showDetailPanel(otherIdea);
            focusNodeInGraph(otherId);
          }
        };

        const chip = document.createElement("span");
        chip.className = "chip";
        chip.style.borderColor = CTYPE_COLORS[c.ctype] || "var(--accent)";
        chip.style.color = CTYPE_COLORS[c.ctype] || "var(--accent)";
        chip.textContent = `${c.ctype} (${Math.round(c.strength * 100)}%)`;

        topRow.appendChild(link);
        topRow.appendChild(chip);
        card.appendChild(topRow);

        if (c.note) {
          const note = document.createElement("div");
          note.className = "conn-note";
          note.textContent = c.note;
          card.appendChild(note);
        }

        el.panelConnections.appendChild(card);
      });
    }

    // Themes
    el.panelThemes.innerHTML = "";
    const matchingThemes = state.themes.filter(
      (th) => th.idea_ids && th.idea_ids.includes(idea.id)
    );
    if (matchingThemes.length === 0) {
      el.panelThemes.innerHTML = '<span class="text-dim">No themes assigned</span>';
    } else {
      matchingThemes.forEach((th) => {
        const card = document.createElement("div");
        card.className = "connection-card";
        card.innerHTML = `<div class="conn-link" style="color:var(--accent);">${escapeHtml(th.name)}</div><div class="conn-note">${escapeHtml(th.description || "")}</div>`;
        el.panelThemes.appendChild(card);
      });
    }

    // Redraw graph so selected node is highlighted
    requestAnimationFrame(drawGraph);
  }

  function closeDetailPanel() {
    state.selectedIdeaId = null;
    el.detailPanel.classList.add("hidden");
    requestAnimationFrame(drawGraph);
  }

  // --- List View Rendering ---
  function renderList(filteredIdeas) {
    el.ideasTableBody.innerHTML = "";

    if (filteredIdeas.length === 0) {
      el.listEmpty.classList.remove("hidden");
      return;
    }
    el.listEmpty.classList.add("hidden");

    filteredIdeas.forEach((idea) => {
      const tr = document.createElement("tr");

      // Title & Summary
      const tdTitle = document.createElement("td");
      const titleDiv = document.createElement("div");
      titleDiv.className = "table-title";
      titleDiv.textContent = idea.title;
      if (idea.seeded) {
        const seedBadge = document.createElement("span");
        seedBadge.className = "chip chip-seeded";
        seedBadge.style.marginLeft = "6px";
        seedBadge.textContent = "seeded";
        titleDiv.appendChild(seedBadge);
      }
      tdTitle.appendChild(titleDiv);

      const summaryDiv = document.createElement("div");
      summaryDiv.className = "table-summary";
      summaryDiv.textContent = idea.summary || idea.raw;
      tdTitle.appendChild(summaryDiv);

      // Category
      const tdCat = document.createElement("td");
      const catChip = document.createElement("span");
      catChip.className = "chip chip-category";
      catChip.textContent = CATEGORY_NAMES[idea.category] || idea.category || "other";
      catChip.style.color = CATEGORY_COLORS[idea.category] || "var(--text-main)";
      catChip.style.borderColor = CATEGORY_COLORS[idea.category] || "var(--border-color)";
      tdCat.appendChild(catChip);

      // Status (Inline editable!)
      const tdStatus = document.createElement("td");
      const statusSelect = document.createElement("select");
      statusSelect.className = "form-select status-select";
      statusSelect.style.borderColor = STATUS_COLORS[idea.status] || "var(--border-color)";
      statusSelect.style.color = STATUS_COLORS[idea.status] || "var(--text-main)";

      ["raw", "developed", "testing", "being_built", "proven", "dead"].forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = s;
        if (s === idea.status) opt.selected = true;
        statusSelect.appendChild(opt);
      });

      statusSelect.onclick = (e) => e.stopPropagation();
      statusSelect.onchange = async (e) => {
        e.stopPropagation();
        const newStatus = statusSelect.value;
        try {
          await apiFetch(`/api/ideas/${idea.id}`, {
            method: "PATCH",
            body: JSON.stringify({ status: newStatus }),
          });
          idea.status = newStatus;
          loadAllData();
        } catch (err) {
          alert(`Failed to update status: ${err.message}`);
        }
      };
      tdStatus.appendChild(statusSelect);

      // Tags
      const tdTags = document.createElement("td");
      const tagsContainer = document.createElement("div");
      tagsContainer.className = "tags-container";
      (idea.tags || []).slice(0, 3).forEach((t) => {
        const badge = document.createElement("span");
        badge.className = "tag-badge";
        badge.textContent = `#${t}`;
        badge.onclick = (e) => {
          e.stopPropagation();
          state.filters.search = t;
          el.filterSearch.value = t;
          el.btnClearSearch.classList.remove("hidden");
          renderAll();
        };
        tagsContainer.appendChild(badge);
      });
      if ((idea.tags || []).length > 3) {
        const more = document.createElement("span");
        more.className = "text-dim";
        more.textContent = `+${idea.tags.length - 3}`;
        tagsContainer.appendChild(more);
      }
      tdTags.appendChild(tagsContainer);

      // Key Scores
      const tdScores = document.createElement("td");
      const scoresDiv = document.createElement("div");
      scoresDiv.className = "inline-scores";
      const scores = idea.scores || {};
      const opp = computeOppScore(scores);

      if (opp !== null) {
        const oppPill = document.createElement("span");
        oppPill.className = "score-mini-pill";
        oppPill.style.borderColor = "var(--accent)";
        oppPill.style.color = "var(--accent)";
        oppPill.style.fontWeight = "bold";
        oppPill.textContent = `Opp: ${opp > 0 ? "+" + opp : opp}`;
        scoresDiv.appendChild(oppPill);
      } else {
        const keys = Object.keys(scores).filter((k) => scores[k] !== undefined);
        keys.slice(0, 2).forEach((k) => {
          const p = document.createElement("span");
          p.className = "score-mini-pill";
          p.textContent = `${k.slice(0, 3)}: ${scores[k]}`;
          scoresDiv.appendChild(p);
        });
        if (keys.length === 0) {
          scoresDiv.innerHTML = '<span class="text-dim">—</span>';
        }
      }
      tdScores.appendChild(scoresDiv);

      // Age
      const tdAge = document.createElement("td");
      tdAge.className = "table-age";
      tdAge.textContent = formatAge(idea.created_at);

      tr.appendChild(tdTitle);
      tr.appendChild(tdCat);
      tr.appendChild(tdStatus);
      tr.appendChild(tdTags);
      tr.appendChild(tdScores);
      tr.appendChild(tdAge);

      tr.onclick = () => showDetailPanel(idea);
      el.ideasTableBody.appendChild(tr);
    });
  }

  // --- Stats View Rendering ---
  function renderStats() {
    if (!state.stats) return;
    const { counts, top_opportunities } = state.stats;

    el.statTotalIdeas.textContent = counts.total || 0;
    el.statSeededIdeas.textContent = counts.seeded_count || 0;
    el.statConnectionsCount.textContent = state.connections.length;
    el.statThemesCount.textContent = state.themes.length;

    // Status chips
    el.statusChipsContainer.innerHTML = "";
    const byStatus = counts.by_status || {};
    ["raw", "developed", "testing", "being_built", "proven", "dead"].forEach((s) => {
      const chip = document.createElement("div");
      chip.className = "stat-chip";
      chip.innerHTML = `
        <span class="legend-dot" style="background:${STATUS_COLORS[s]}"></span>
        <span style="text-transform: capitalize;">${s.replace("_", " ")}</span>
        <span class="stat-chip-count">${byStatus[s] || 0}</span>
      `;
      chip.onclick = () => {
        state.filters.status = state.filters.status === s ? "" : s;
        el.filterStatus.value = state.filters.status;
        renderAll();
      };
      el.statusChipsContainer.appendChild(chip);
    });

    // Category chips
    el.categoryChipsContainer.innerHTML = "";
    const byCategory = counts.by_category || {};
    Object.keys(CATEGORY_NAMES).forEach((cat) => {
      const count = byCategory[cat] || 0;
      const chip = document.createElement("div");
      chip.className = "stat-chip";
      chip.innerHTML = `
        <span class="legend-dot" style="background:${CATEGORY_COLORS[cat]}"></span>
        <span>${CATEGORY_NAMES[cat]}</span>
        <span class="stat-chip-count">${count}</span>
      `;
      chip.onclick = () => {
        state.filters.category = state.filters.category === cat ? "" : cat;
        el.filterCategory.value = state.filters.category;
        renderAll();
      };
      el.categoryChipsContainer.appendChild(chip);
    });

    // Top Opportunities Table
    el.rankingTableBody.innerHTML = "";
    const opps = top_opportunities || [];
    if (opps.length === 0) {
      el.rankingTableBody.innerHTML =
        '<tr><td colspan="5" class="empty-state">No ideas with complete scores yet.</td></tr>';
    } else {
      opps.forEach((oppIdea, idx) => {
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";

        // Rank
        const tdRank = document.createElement("td");
        tdRank.style.fontWeight = "bold";
        tdRank.textContent = `#${idx + 1}`;

        // Idea
        const tdTitle = document.createElement("td");
        tdTitle.innerHTML = `<div style="font-weight:600; color:#FFF;">${escapeHtml(oppIdea.title)}</div>`;

        // Category
        const tdCat = document.createElement("td");
        tdCat.innerHTML = `<span class="chip chip-category" style="color:${CATEGORY_COLORS[oppIdea.category]}; border-color:${CATEGORY_COLORS[oppIdea.category]};">${CATEGORY_NAMES[oppIdea.category] || oppIdea.category}</span>`;

        // Score
        const tdScore = document.createElement("td");
        const scoreVal = oppIdea.opportunity_score;
        tdScore.innerHTML = `<span class="opp-badge" style="font-size:0.9rem;">${scoreVal > 0 ? "+" + scoreVal : scoreVal}</span>`;

        // Score bars breakdown
        const tdBars = document.createElement("td");
        const barsDiv = document.createElement("div");
        barsDiv.style.display = "grid";
        barsDiv.style.gridTemplateColumns = "repeat(7, 1fr)";
        barsDiv.style.gap = "4px";
        barsDiv.style.fontSize = "0.7rem";

        const shortKeys = [
          ["cap", "capital"],
          ["eff", "effort"],
          ["tim", "time_to_revenue"],
          ["cei", "ceiling"],
          ["dif", "difficulty"],
          ["moa", "moat"],
          ["rsk", "risk"],
        ];

        shortKeys.forEach(([short, full]) => {
          const val = (oppIdea.scores && oppIdea.scores[full]) || 0;
          const col = document.createElement("div");
          col.style.textAlign = "center";
          col.innerHTML = `
            <div style="color:var(--text-muted); font-size:0.65rem;">${short}</div>
            <div style="height:4px; background:#242B38; border-radius:2px; margin:2px 0;">
              <div style="height:100%; width:${(val / 5) * 100}%; background:var(--accent); border-radius:2px;"></div>
            </div>
            <div style="font-family:var(--font-mono);">${val}</div>
          `;
          barsDiv.appendChild(col);
        });

        tdBars.appendChild(barsDiv);

        tr.appendChild(tdRank);
        tr.appendChild(tdTitle);
        tr.appendChild(tdCat);
        tr.appendChild(tdScore);
        tr.appendChild(tdBars);

        tr.onclick = () => {
          const fullIdea = state.ideas.find((i) => i.id === oppIdea.id) || oppIdea;
          showDetailPanel(fullIdea);
        };

        el.rankingTableBody.appendChild(tr);
      });
    }

    // Connections by type
    el.connectionBarsContainer.innerHTML = "";
    const ctypeCounts = {
      parallel: 0,
      complements: 0,
      same_market: 0,
      competes: 0,
      extends: 0,
    };
    state.connections.forEach((c) => {
      if (ctypeCounts[c.ctype] !== undefined) ctypeCounts[c.ctype]++;
    });
    const maxCtype = Math.max(...Object.values(ctypeCounts), 1);

    Object.keys(ctypeCounts).forEach((ctype) => {
      const cnt = ctypeCounts[ctype];
      const row = document.createElement("div");
      row.className = "conn-bar-row";
      row.innerHTML = `
        <div class="conn-bar-name" style="color:${CTYPE_COLORS[ctype]}">${ctype.replace("_", " ")}</div>
        <div class="conn-bar-track">
          <div class="conn-bar-fill" style="width:${(cnt / maxCtype) * 100}%; background:${CTYPE_COLORS[ctype]}"></div>
        </div>
        <div class="conn-bar-count">${cnt}</div>
      `;
      el.connectionBarsContainer.appendChild(row);
    });

    // Themes Table
    el.themesTableBody.innerHTML = "";
    if (state.themes.length === 0) {
      el.themesTableBody.innerHTML =
        '<tr><td colspan="3" class="empty-state">No themes created yet.</td></tr>';
    } else {
      state.themes.forEach((th) => {
        const tr = document.createElement("tr");
        const count = (th.idea_ids || []).length;
        tr.innerHTML = `
          <td style="font-weight:600; color:var(--accent);">${escapeHtml(th.name)}</td>
          <td style="color:var(--text-muted); font-size:0.82rem;">${escapeHtml(th.description || "—")}</td>
          <td><span class="count-badge">${count} ideas</span></td>
        `;
        el.themesTableBody.appendChild(tr);
      });
    }

    // Analysis Runs Table
    el.runsTableBody.innerHTML = "";
    if (state.analysisRuns.length === 0) {
      el.runsTableBody.innerHTML =
        '<tr><td colspan="4" class="empty-state">No analysis runs recorded.</td></tr>';
    } else {
      state.analysisRuns.forEach((run) => {
        const tr = document.createElement("tr");
        const isSuccess = run.status === "done";
        const isFailed = run.status === "failed";
        const badgeColor = isSuccess ? "var(--status-proven)" : isFailed ? "var(--status-dead)" : "var(--status-testing)";

        tr.innerHTML = `
          <td style="font-weight:600; color:#FFF;">${escapeHtml(run.title || "Idea #" + run.idea_id)}</td>
          <td><span class="chip" style="border-color:${badgeColor}; color:${badgeColor};">${run.status}</span></td>
          <td style="color:var(--text-dim); font-size:0.8rem;">${formatAge(run.ts)}</td>
          <td style="color:${isFailed ? "var(--danger)" : "var(--text-muted)"}; font-size:0.82rem;">${escapeHtml(run.error || (isSuccess ? "Analysis completed successfully" : "Pending execution"))}</td>
        `;
        el.runsTableBody.appendChild(tr);
      });
    }
  }

  // --- Force-Directed Graph Simulation (~70 lines) ---
  function initGraph(filteredIdeas) {
    const width = el.canvas.clientWidth || 800;
    const height = el.canvas.clientHeight || 600;

    // Preserve existing node positions if present
    const posMap = new Map();
    state.graph.nodes.forEach((n) => {
      posMap.set(n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy });
    });

    const ideaMap = new Map();
    filteredIdeas.forEach((i) => ideaMap.set(i.id, i));

    // Build Nodes
    state.graph.nodes = filteredIdeas.map((idea, idx) => {
      const prev = posMap.get(idea.id);
      const angle = (idx / filteredIdeas.length) * 2 * Math.PI;
      const initialRadius = Math.min(width, height) * 0.35;
      const opp = computeOppScore(idea.scores);

      let radius = 10;
      if (opp !== null) {
        radius = Math.max(6, Math.min(22, 8 + opp / 2));
      }

      return {
        id: idea.id,
        idea: idea,
        x: prev ? prev.x : width / 2 + Math.cos(angle) * initialRadius + (Math.random() - 0.5) * 40,
        y: prev ? prev.y : height / 2 + Math.sin(angle) * initialRadius + (Math.random() - 0.5) * 40,
        vx: prev ? prev.vx : 0,
        vy: prev ? prev.vy : 0,
        radius: radius,
        color: CATEGORY_COLORS[idea.category] || "#94A3B8",
      };
    });

    // Build Edges
    const nodeIds = new Set(filteredIdeas.map((i) => i.id));
    state.graph.edges = [];
    state.connections.forEach((c) => {
      if (nodeIds.has(c.a) && nodeIds.has(c.b)) {
        const sourceNode = state.graph.nodes.find((n) => n.id === c.a);
        const targetNode = state.graph.nodes.find((n) => n.id === c.b);
        if (sourceNode && targetNode) {
          state.graph.edges.push({
            source: sourceNode,
            target: targetNode,
            ctype: c.ctype,
            strength: c.strength || 0.5,
            color: CTYPE_COLORS[c.ctype] || "#FF8C42",
          });
        }
      }
    });

    state.graph.simTicksRemaining = 90;
    stepSimulation();
  }

  function stepSimulation() {
    if (state.graph.simTicksRemaining <= 0) {
      drawGraph();
      return;
    }

    const { nodes, edges } = state.graph;
    const width = el.canvas.clientWidth || 800;
    const height = el.canvas.clientHeight || 600;
    const cx = width / 2;
    const cy = height / 2;

    const kRepel = 2400;
    const kSpring = 0.04;
    const restLength = 110;

    // 1. Repulsion between all node pairs
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const n1 = nodes[i];
        const n2 = nodes[j];
        let dx = n2.x - n1.x;
        let dy = n2.y - n1.y;
        let dist = Math.hypot(dx, dy) || 1;
        let force = kRepel / (dist * dist);
        let fx = (dx / dist) * force;
        let fy = (dy / dist) * force;

        n1.vx -= fx;
        n1.vy -= fy;
        n2.vx += fx;
        n2.vy += fy;
      }
    }

    // 2. Spring attraction along edges
    for (let i = 0; i < edges.length; i++) {
      const e = edges[i];
      let dx = e.target.x - e.source.x;
      let dy = e.target.y - e.source.y;
      let dist = Math.hypot(dx, dy) || 1;
      let force = (dist - restLength) * kSpring * (0.5 + e.strength);
      let fx = (dx / dist) * force;
      let fy = (dy / dist) * force;

      e.source.vx += fx;
      e.source.vy += fy;
      e.target.vx -= fx;
      e.target.vy -= fy;
    }

    // 3. Centering force & update positions
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (n === state.graph.draggedNode) continue;

      n.vx += (cx - n.x) * 0.015;
      n.vy += (cy - n.y) * 0.015;

      n.vx *= 0.82;
      n.vy *= 0.82;

      n.x += n.vx;
      n.y += n.vy;
    }

    state.graph.simTicksRemaining--;
    drawGraph();

    if (state.graph.simTicksRemaining > 0) {
      requestAnimationFrame(stepSimulation);
    }
  }

  function drawGraph() {
    const canvas = el.canvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high DPI
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // Apply pan & zoom
    ctx.translate(w / 2 + state.graph.panX, h / 2 + state.graph.panY);
    ctx.scale(state.graph.zoom, state.graph.zoom);
    ctx.translate(-w / 2, -h / 2);

    const { nodes, edges, hoveredNode } = state.graph;
    const selectedId = state.selectedIdeaId;

    // Draw Edges
    edges.forEach((e) => {
      const isConnectedToSelected =
        selectedId && (e.source.id === selectedId || e.target.id === selectedId);

      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);

      ctx.strokeStyle = e.color;
      ctx.lineWidth = 1 + e.strength * 3.5;
      ctx.globalAlpha = selectedId ? (isConnectedToSelected ? 0.95 : 0.15) : 0.7;
      ctx.stroke();
    });

    // Draw Nodes
    nodes.forEach((n) => {
      const isSelected = selectedId === n.id;
      const isHovered = hoveredNode === n;

      ctx.globalAlpha = selectedId ? (isSelected ? 1.0 : 0.35) : 1.0;

      // Glow on selected or hovered
      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius + 6, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? "rgba(255, 140, 66, 0.35)" : "rgba(255, 255, 255, 0.2)";
        ctx.fill();
      }

      // Main Node Circle
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
      ctx.fillStyle = n.color;
      ctx.fill();

      // Border / outline
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);

      if (n.idea.seeded) {
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = "#FFFFFF";
        ctx.lineWidth = 2;
      } else {
        ctx.setLineDash([]);
        ctx.strokeStyle = isSelected ? "#FF8C42" : "rgba(0, 0, 0, 0.4)";
        ctx.lineWidth = isSelected ? 2.5 : 1.5;
      }
      ctx.stroke();
      ctx.setLineDash([]); // Reset

      // Title label below node
      ctx.fillStyle = isSelected ? "#FF8C42" : isHovered ? "#FFFFFF" : "#E8EAED";
      ctx.font = isSelected ? "bold 11px sans-serif" : "10px sans-serif";
      ctx.textAlign = "center";
      const truncatedTitle = n.idea.title.length > 20 ? n.idea.title.slice(0, 18) + "…" : n.idea.title;
      ctx.fillText(truncatedTitle, n.x, n.y + n.radius + 12);
    });

    ctx.restore();
  }

  function renderMap(filteredIdeas) {
    initGraph(filteredIdeas);
  }

  function focusNodeInGraph(nodeId) {
    const node = state.graph.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    const w = el.canvas.clientWidth;
    const h = el.canvas.clientHeight;
    state.graph.panX = w / 2 - node.x;
    state.graph.panY = h / 2 - node.y;
    drawGraph();
  }

  // --- Graph Coordinate Helpers ---
  function getMouseWorldPos(e) {
    const rect = el.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const w = el.canvas.clientWidth;
    const h = el.canvas.clientHeight;

    // Invert zoom and pan
    const cx = w / 2;
    const cy = h / 2;

    const wx = (mx - cx - state.graph.panX) / state.graph.zoom + cx;
    const wy = (my - cy - state.graph.panY) / state.graph.zoom + cy;
    return { wx, wy, mx, my };
  }

  function findNodeAt(wx, wy) {
    for (let i = state.graph.nodes.length - 1; i >= 0; i--) {
      const n = state.graph.nodes[i];
      const dist = Math.hypot(n.x - wx, n.y - wy);
      if (dist <= n.radius + 4) return n;
    }
    return null;
  }

  // --- Graph Interaction Listeners ---
  el.canvas.addEventListener("mousedown", (e) => {
    const { wx, wy, mx, my } = getMouseWorldPos(e);
    const node = findNodeAt(wx, wy);

    if (node) {
      state.graph.draggedNode = node;
      node.x = wx;
      node.y = wy;
    } else {
      state.graph.isPanning = true;
      state.graph.lastMouseX = mx;
      state.graph.lastMouseY = my;
    }
  });

  window.addEventListener("mousemove", (e) => {
    if (state.activeTab !== "map") return;
    const { wx, wy, mx, my } = getMouseWorldPos(e);

    if (state.graph.draggedNode) {
      state.graph.draggedNode.x = wx;
      state.graph.draggedNode.y = wy;
      state.graph.draggedNode.vx = 0;
      state.graph.draggedNode.vy = 0;
      requestAnimationFrame(drawGraph);
      return;
    }

    if (state.graph.isPanning) {
      state.graph.panX += mx - state.graph.lastMouseX;
      state.graph.panY += my - state.graph.lastMouseY;
      state.graph.lastMouseX = mx;
      state.graph.lastMouseY = my;
      requestAnimationFrame(drawGraph);
      return;
    }

    // Hover tooltip
    const node = findNodeAt(wx, wy);
    state.graph.hoveredNode = node;

    if (node) {
      el.canvas.style.cursor = "pointer";
      const opp = computeOppScore(node.idea.scores);
      const oppStr = opp !== null ? ` (Opp: ${opp > 0 ? "+" + opp : opp})` : "";
      el.mapTooltip.innerHTML = `<strong>${escapeHtml(node.idea.title)}</strong><br/><span style="color:${node.color}">${CATEGORY_NAMES[node.idea.category] || node.idea.category}</span>${oppStr}`;
      el.mapTooltip.style.left = `${mx + 12}px`;
      el.mapTooltip.style.top = `${my + 12}px`;
      el.mapTooltip.classList.remove("hidden");
    } else {
      el.canvas.style.cursor = "grab";
      el.mapTooltip.classList.add("hidden");
    }
    requestAnimationFrame(drawGraph);
  });

  window.addEventListener("mouseup", (e) => {
    if (state.graph.draggedNode) {
      state.graph.draggedNode = null;
      state.graph.simTicksRemaining = 25;
      stepSimulation();
    }
    state.graph.isPanning = false;
  });

  el.canvas.addEventListener("click", (e) => {
    const { wx, wy } = getMouseWorldPos(e);
    const node = findNodeAt(wx, wy);
    if (node) {
      showDetailPanel(node.idea);
    }
  });

  el.canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    state.graph.zoom = Math.max(0.3, Math.min(3.0, state.graph.zoom * zoomFactor));
    requestAnimationFrame(drawGraph);
  });

  // Canvas Control Buttons
  el.btnRecenter.onclick = () => {
    state.graph.panX = 0;
    state.graph.panY = 0;
    state.graph.zoom = 1.0;
    state.graph.simTicksRemaining = 40;
    stepSimulation();
  };

  el.btnZoomIn.onclick = () => {
    state.graph.zoom = Math.min(3.0, state.graph.zoom * 1.2);
    requestAnimationFrame(drawGraph);
  };

  el.btnZoomOut.onclick = () => {
    state.graph.zoom = Math.max(0.3, state.graph.zoom * 0.8);
    requestAnimationFrame(drawGraph);
  };

  // --- Filter Listeners ---
  el.filterCategory.onchange = () => {
    state.filters.category = el.filterCategory.value;
    renderAll();
  };

  el.filterStatus.onchange = () => {
    state.filters.status = el.filterStatus.value;
    renderAll();
  };

  el.filterSearch.oninput = () => {
    state.filters.search = el.filterSearch.value;
    if (state.filters.search) {
      el.btnClearSearch.classList.remove("hidden");
    } else {
      el.btnClearSearch.classList.add("hidden");
    }
    renderAll();
  };

  el.btnClearSearch.onclick = () => {
    state.filters.search = "";
    el.filterSearch.value = "";
    el.btnClearSearch.classList.add("hidden");
    renderAll();
  };

  el.filterHideSeeded.onchange = () => {
    state.filters.hideSeeded = el.filterHideSeeded.checked;
    renderAll();
  };

  el.btnResetFilters.onclick = () => {
    state.filters = { category: "", status: "", search: "", hideSeeded: false };
    el.filterCategory.value = "";
    el.filterStatus.value = "";
    el.filterSearch.value = "";
    el.btnClearSearch.classList.add("hidden");
    el.filterHideSeeded.checked = false;
    renderAll();
  };

  // --- Detail Panel Actions ---
  el.btnClosePanel.onclick = closeDetailPanel;

  el.panelStatusSelect.onchange = async () => {
    if (!state.selectedIdeaId) return;
    const newStatus = el.panelStatusSelect.value;
    try {
      await apiFetch(`/api/ideas/${state.selectedIdeaId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
      loadAllData();
    } catch (err) {
      alert(`Failed to update status: ${err.message}`);
    }
  };

  el.btnDeleteIdea.onclick = async () => {
    if (!state.selectedIdeaId) return;
    if (!confirm("Are you sure you want to delete this idea? This cannot be undone.")) {
      return;
    }
    try {
      await apiFetch(`/api/ideas/${state.selectedIdeaId}`, {
        method: "DELETE",
      });
      closeDetailPanel();
      loadAllData();
    } catch (err) {
      alert(`Failed to delete idea: ${err.message}`);
    }
  };

  // --- Modal Form Actions ---
  el.btnNewIdea.onclick = () => {
    el.modalNewIdea.classList.remove("hidden");
    el.inputTitle.focus();
  };

  function closeModal() {
    el.modalNewIdea.classList.add("hidden");
    el.formNewIdea.reset();
    el.inputOwner.value = "C6";
  }

  el.btnCloseModal.onclick = closeModal;
  el.btnCancelModal.onclick = closeModal;
  el.modalNewIdea.onclick = (e) => {
    if (e.target === el.modalNewIdea) closeModal();
  };

  el.formNewIdea.onsubmit = async (e) => {
    e.preventDefault();
    const title = el.inputTitle.value.trim();
    const raw = el.inputRaw.value.trim();
    const owner = el.inputOwner.value.trim() || "C6";
    const category = el.inputCategory.value || null;
    const status = el.inputStatus.value || "raw";

    if (!title || !raw) return;

    try {
      const created = await apiFetch("/api/ideas", {
        method: "POST",
        body: JSON.stringify({
          title,
          raw,
          owner,
          category,
          status,
        }),
      });

      closeModal();
      await loadAllData();
      if (created && created.id) {
        showDetailPanel(created);
      }
    } catch (err) {
      alert(`Failed to create idea: ${err.message}`);
    }
  };

  // --- Tab Navigation ---
  function setActiveTab(tabName) {
    state.activeTab = tabName;
    el.tabs.forEach((t) => {
      if (t.dataset.tab === tabName) {
        t.classList.add("active");
      } else {
        t.classList.remove("active");
      }
    });

    el.tabPanes.forEach((p) => {
      if (p.id === `tab-pane-${tabName}` || p.id === `tab-${tabName}`) {
        p.classList.add("active");
      } else {
        p.classList.remove("active");
      }
    });

    if (tabName === "map") {
      requestAnimationFrame(() => {
        state.graph.simTicksRemaining = 20;
        stepSimulation();
      });
    }
  }

  el.tabs.forEach((tab) => {
    tab.onclick = () => setActiveTab(tab.dataset.tab);
  });

  el.btnRetry.onclick = () => loadAllData();

  // --- Utilities ---
  function formatAge(dateStr) {
    if (!dateStr) return "—";
    try {
      const d = new Date(dateStr + (dateStr.endsWith("Z") ? "" : "Z"));
      const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
      if (diffSec < 60) return "just now";
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
      return `${Math.floor(diffSec / 86400)}d ago`;
    } catch (e) {
      return dateStr.split(" ")[0];
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // --- Initialization ---
  window.addEventListener("DOMContentLoaded", () => {
    // Mobile responsive: default to list tab on narrow screens
    if (window.innerWidth < 768) {
      setActiveTab("list");
    }

    loadAllData();

    // Auto-refresh every 30s
    setInterval(loadAllData, 30000);

    window.addEventListener("resize", () => {
      if (state.activeTab === "map") {
        drawGraph();
      }
    });
  });
})();
