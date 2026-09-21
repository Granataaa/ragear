/**
 * RAGEAR - UNINETTUNO Course Recommender Frontend Application
 */

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

// App State
const state = {
    filters: {
        facolta: "",
        cfu: null,
        tipologia_corso: "",
        settore: "",
        top_k: 50
    },
    ragServerStatus: {
        online: false,
        url: ""
    }
};

async function initApp() {
    setupEventListeners();
    await checkRAGStatus();
    await loadFilterOptions();
    await loadSampleQueries();
}

function setupEventListeners() {
    const searchInput = document.getElementById("searchInput");
    const searchBtn = document.getElementById("searchBtn");
    const clearBtn = document.getElementById("clearSearchBtn");
    const toggleFiltersBtn = document.getElementById("toggleFiltersBtn");
    const filtersDrawer = document.getElementById("filtersDrawer");
    const resetFiltersBtn = document.getElementById("resetFiltersBtn");
    const topKSlider = document.getElementById("topKSlider");
    const topKVal = document.getElementById("topKVal");

    // Search on Enter
    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            performSearch();
        }
    });

    // Input changes (show/hide clear button)
    searchInput.addEventListener("input", () => {
        if (searchInput.value.trim().length > 0) {
            clearBtn.style.display = "block";
        } else {
            clearBtn.style.display = "none";
        }
    });

    // Clear search
    clearBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearBtn.style.display = "none";
        searchInput.focus();
    });

    // Search button
    searchBtn.addEventListener("click", () => {
        performSearch();
    });

    // Toggle filters drawer
    toggleFiltersBtn.addEventListener("click", () => {
        const isOpen = filtersDrawer.classList.toggle("open");
        toggleFiltersBtn.classList.toggle("active", isOpen);
    });

    // Top K slider
    topKSlider.addEventListener("input", () => {
        state.filters.top_k = parseInt(topKSlider.value, 10);
        topKVal.textContent = topKSlider.value;
    });

    // Filter selectors
    document.getElementById("filterFaculty").addEventListener("change", (e) => {
        state.filters.facolta = e.target.value;
        updateActiveFilterBadge();
    });

    document.getElementById("filterCfu").addEventListener("change", (e) => {
        state.filters.cfu = e.target.value ? parseInt(e.target.value, 10) : null;
        updateActiveFilterBadge();
    });

    document.getElementById("filterDegreeType").addEventListener("change", (e) => {
        state.filters.tipologia_corso = e.target.value;
        updateActiveFilterBadge();
    });

    document.getElementById("filterSettore").addEventListener("change", (e) => {
        state.filters.settore = e.target.value;
        updateActiveFilterBadge();
    });

    // Reset filters
    resetFiltersBtn.addEventListener("click", () => {
        state.filters.facolta = "";
        state.filters.cfu = null;
        state.filters.tipologia_corso = "";
        state.filters.settore = "";
        state.filters.top_k = 50;

        document.getElementById("filterFaculty").value = "";
        document.getElementById("filterCfu").value = "";
        document.getElementById("filterDegreeType").value = "";
        document.getElementById("filterSettore").value = "";
        topKSlider.value = 50;
        topKVal.textContent = "50";

        updateActiveFilterBadge();
    });
}

function updateActiveFilterBadge() {
    let count = 0;
    if (state.filters.facolta) count++;
    if (state.filters.cfu !== null) count++;
    if (state.filters.tipologia_corso) count++;
    if (state.filters.settore) count++;

    const badge = document.getElementById("filterBadgeCount");
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = "inline-block";
    } else {
        badge.style.display = "none";
    }
}

async function checkRAGStatus() {
    const pill = document.getElementById("ragStatusPill");
    const text = document.getElementById("ragStatusText");

    try {
        const res = await fetch("/api/v1/status");
        if (!res.ok) throw new Error("Status check failed");
        const data = await res.json();

        state.ragServerStatus.online = data.is_online;
        state.ragServerStatus.url = data.rag_server_url;

        if (data.is_online) {
            pill.className = "status-pill online";
            text.textContent = `Server RAG Online (${data.rag_server_url})`;
        } else {
            pill.className = "status-pill offline";
            text.textContent = `Server RAG Offline (${data.rag_server_url})`;
        }
    } catch (e) {
        pill.className = "status-pill offline";
        text.textContent = "Server RAG Non Raggiungibile";
    }
}

async function loadFilterOptions() {
    try {
        const res = await fetch("/api/v1/filters");
        if (!res.ok) return;
        const data = await res.json();

        // Populate Faculty dropdown
        const facSelect = document.getElementById("filterFaculty");
        data.faculties.forEach(fac => {
            const opt = document.createElement("option");
            opt.value = fac;
            opt.textContent = fac;
            facSelect.appendChild(opt);
        });

        // Populate CFU dropdown
        const cfuSelect = document.getElementById("filterCfu");
        data.cfu_list.forEach(cfu => {
            const opt = document.createElement("option");
            opt.value = cfu;
            opt.textContent = `${cfu} CFU`;
            cfuSelect.appendChild(opt);
        });

        // Populate Settori dropdown
        const setSelect = document.getElementById("filterSettore");
        data.settori.forEach(settore => {
            const opt = document.createElement("option");
            opt.value = settore;
            opt.textContent = settore;
            setSelect.appendChild(opt);
        });
    } catch (e) {
        console.warn("Could not load filter options", e);
    }
}

async function loadSampleQueries() {
    const chipsContainer = document.getElementById("sampleChips");
    try {
        const res = await fetch("/api/v1/sample-queries");
        if (!res.ok) return;
        const data = await res.json();

        chipsContainer.innerHTML = "";
        data.queries.forEach(query => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "chip";
            chip.textContent = query;
            chip.addEventListener("click", () => {
                const searchInput = document.getElementById("searchInput");
                searchInput.value = query;
                document.getElementById("clearSearchBtn").style.display = "block";
                performSearch();
            });
            chipsContainer.appendChild(chip);
        });
    } catch (e) {
        console.warn("Could not load sample queries", e);
    }
}

async function performSearch() {
    const searchInput = document.getElementById("searchInput");
    const query = searchInput.value.trim();
    if (!query) {
        searchInput.focus();
        return;
    }

    const searchBtn = document.getElementById("searchBtn");
    const resultsContainer = document.getElementById("resultsContainer");

    // UI Loading state
    searchBtn.disabled = true;
    renderSkeletons(resultsContainer);

    // Build payload
    const payload = {
        question: query,
        top_k_chunks: state.filters.top_k,
        score_key: "final_score",
        filters: {}
    };

    if (state.filters.facolta) payload.filters.facolta = state.filters.facolta;
    if (state.filters.cfu !== null) payload.filters.cfu = state.filters.cfu;
    if (state.filters.tipologia_corso) payload.filters.tipologia_corso = state.filters.tipologia_corso;
    if (state.filters.settore) payload.filters.settore = state.filters.settore;

    try {
        const response = await fetch("/api/v1/recommend", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json().catch(() => ({ detail: "Errore sconosciuto" }));
            throw new Error(errData.detail || `Errore HTTP ${response.status}`);
        }

        const data = await response.json();
        renderResults(data);
    } catch (err) {
        renderError(resultsContainer, err.message);
    } finally {
        searchBtn.disabled = false;
    }
}

function renderSkeletons(container) {
    container.innerHTML = `
        <div class="results-header">
            <span class="results-count">Ricerca semantica e calcolo RAGER in corso...</span>
        </div>
        <div class="skeleton-card">
            <div class="skeleton-line title"></div>
            <div class="skeleton-line short"></div>
            <div class="skeleton-line long"></div>
        </div>
        <div class="skeleton-card">
            <div class="skeleton-line title"></div>
            <div class="skeleton-line short"></div>
            <div class="skeleton-line medium"></div>
        </div>
        <div class="skeleton-card">
            <div class="skeleton-line title"></div>
            <div class="skeleton-line short"></div>
            <div class="skeleton-line long"></div>
        </div>
    `;
}

function renderError(container, message) {
    container.innerHTML = `
        <div class="state-box">
            <div class="state-icon">⚠️</div>
            <div class="state-title">Errore durante la raccomandazione</div>
            <div class="state-desc">${escapeHtml(message)}</div>
            <div style="margin-top: 1.5rem;">
                <button class="btn-search" onclick="performSearch()">Riprova</button>
            </div>
        </div>
    `;
}

function renderResults(data) {
    const container = document.getElementById("resultsContainer");
    const recs = data.recommendations || [];

    if (recs.length === 0) {
        container.innerHTML = `
            <div class="state-box">
                <div class="state-icon">🔍</div>
                <div class="state-title">Nessun corso corrispondente trovato</div>
                <div class="state-desc">Nessun corso soddisfa i criteri di ricerca e i filtri impostati. Prova a rimuovere i filtri o a riformulare la domanda.</div>
            </div>
        `;
        return;
    }

    let html = `
        <div class="results-header">
            <span class="results-count">${recs.length} Corsi Consigliati</span>
            <span class="results-meta">Valutati ${data.total_candidates_evaluated} chunk semantici in <strong>${data.elapsed_seconds}s</strong></span>
        </div>
    `;

    recs.forEach(course => {
        let rankClass = "";
        if (course.rank === 1) rankClass = "gold";
        else if (course.rank === 2) rankClass = "silver";
        else if (course.rank === 3) rankClass = "bronze";

        const cfuBadge = course.cfu ? `<span class="badge badge-cfu">🎓 ${course.cfu} CFU</span>` : "";
        const facoltaBadge = course.facolta ? `<span class="badge badge-faculty">🏛️ ${escapeHtml(course.facolta)}</span>` : "";
        const degreeBadge = course.corso_laurea ? `<span class="badge badge-degree">📚 ${escapeHtml(course.corso_laurea)}</span>` : "";
        const settoreBadge = course.settore ? `<span class="badge badge-settore">🔬 ${escapeHtml(course.settore)}</span>` : "";

        const breakdown = course.score_breakdown;

        // Lessons list HTML
        let lessonsHtml = "";
        if (course.matched_lessons && course.matched_lessons.length > 0) {
            const items = course.matched_lessons.map(l => {
                const videoBtn = l.video_url
                    ? `<a href="${escapeHtml(l.video_url)}" target="_blank" rel="noreferrer" class="btn-video">▶️ Guarda Video</a>`
                    : "";
                const lezLinkBtn = l.link_lezione
                    ? `<a href="${escapeHtml(l.link_lezione)}" target="_blank" rel="noreferrer" class="btn-uninettuno-link">🔗 Scheda Lezione</a>`
                    : "";

                return `
                    <div class="lesson-item">
                        <div class="lesson-item-header">
                            <span class="lesson-item-title">${escapeHtml(l.lesson_title)}</span>
                            <span class="lesson-time">⏱️ ${l.formatted_time}</span>
                        </div>
                        ${l.snippet ? `<div class="lesson-snippet">"${escapeHtml(l.snippet)}"</div>` : ""}
                        <div class="lesson-actions">
                            ${videoBtn}
                            ${lezLinkBtn}
                        </div>
                    </div>
                `;
            }).join("");

            lessonsHtml = `
                <div class="lessons-accordion" id="accordion-${course.rank}">
                    <button type="button" class="accordion-toggle" onclick="toggleAccordion('accordion-${course.rank}')">
                        <span>🎯 Perché questo corso? Mostra ${course.matched_lessons.length} lezioni pertinenti</span>
                        <span class="accordion-icon">▼</span>
                    </button>
                    <div class="lessons-content">
                        ${items}
                    </div>
                </div>
            `;
        }

        const syllabusLink = course.link_corso
            ? `<div class="card-footer"><a href="${escapeHtml(course.link_corso)}" target="_blank" rel="noreferrer" class="link-syllabus">📖 Apri Programma Ufficiale del Corso →</a></div>`
            : "";

        html += `
            <div class="course-card">
                <div class="card-top">
                    <div class="rank-badge ${rankClass}">#${course.rank}</div>
                    <div class="course-info">
                        <h3 class="course-title">${escapeHtml(course.course_title)}</h3>
                        <div class="badge-row">
                            ${facoltaBadge}
                            ${degreeBadge}
                            ${cfuBadge}
                            ${settoreBadge}
                        </div>
                    </div>
                </div>

                <div class="score-section">
                    <div class="confidence-box">
                        <span class="confidence-label">Affinità Contenuti</span>
                        <span class="confidence-val">${course.confidence_percent}%</span>
                    </div>
                    <div class="confidence-bar-wrapper">
                        <div class="confidence-bar-bg">
                            <div class="confidence-bar-fill" style="width: ${course.confidence_percent}%;"></div>
                        </div>
                    </div>
                    <div class="metrics-row">
                        <span class="metric-item">Chunk pertinenti: <strong>${breakdown.matched_chunks_count}</strong></span>
                        <span class="metric-item">Copertura: <strong>${breakdown.unique_lessons_count}/${breakdown.total_course_lessons} lezioni</strong></span>
                        <span class="metric-item">Score RAGER: <strong>${course.recommendation_score >= 0.001 ? course.recommendation_score.toFixed(4) : course.recommendation_score.toExponential(2)}</strong></span>
                    </div>
                </div>

                ${lessonsHtml}
                ${syllabusLink}
            </div>
        `;
    });

    container.innerHTML = html;
}

function toggleAccordion(id) {
    const acc = document.getElementById(id);
    if (acc) {
        acc.classList.toggle("open");
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
