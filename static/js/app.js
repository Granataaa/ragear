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
                const hasTime = (l.start_time > 0 || l.end_time > 0);
                const startTimeFmt = formatTimeCompact(l.start_time);
                const deepLinkUrl = l.video_url
                    ? (l.start_time > 0 ? `${l.video_url}#t=${Math.floor(l.start_time)}` : l.video_url)
                    : "";

                // Timeline visualization (if timestamps available)
                let timelineBarHtml = "";
                if (hasTime) {
                    const estDuration = l.estimated_duration || 2700; // ~45 min default
                    const effectiveTotal = Math.max(estDuration, (l.end_time || l.start_time) + 300);
                    const leftPct = Math.min(95, Math.max(0, (l.start_time / effectiveTotal) * 100));
                    const widthPct = Math.min(100 - leftPct, Math.max(3.0, (((l.end_time || (l.start_time + 60)) - l.start_time) / effectiveTotal) * 100));

                    timelineBarHtml = `
                        <div class="lesson-timeline-container" title="Spezzone dal min ${startTimeFmt}">
                            <div class="lesson-timeline-header">
                                <span>⏱️ Segmento nel video: <strong>${escapeHtml(l.formatted_time)}</strong></span>
                                <span class="timeline-duration-label">Lezione: ~45 min</span>
                            </div>
                            <div class="lesson-timeline-track" onclick="openVideoModal('${escapeAttr(l.video_url)}', ${l.start_time}, ${l.end_time}, '${escapeAttr(l.lesson_title)}', '${escapeAttr(course.course_title)}', '${escapeAttr(l.snippet)}')">
                                <div class="lesson-timeline-segment" style="left: ${leftPct.toFixed(1)}%; width: ${widthPct.toFixed(1)}%;"></div>
                                <div class="lesson-timeline-marker" style="left: ${leftPct.toFixed(1)}%;"></div>
                            </div>
                        </div>
                    `;
                }

                // Action buttons
                let modalBtn = "";
                let directTabBtn = "";
                if (l.video_url) {
                    const modalLabel = hasTime ? `🎬 Guarda Spezzone (min ${startTimeFmt})` : `🎬 Guarda Video`;
                    modalBtn = `
                        <button type="button" class="btn-video-modal" onclick="openVideoModal('${escapeAttr(l.video_url)}', ${l.start_time}, ${l.end_time}, '${escapeAttr(l.lesson_title)}', '${escapeAttr(course.course_title)}', '${escapeAttr(l.snippet)}', '${escapeAttr(l.link_lezione || '')}')">
                            ${modalLabel}
                        </button>
                    `;
                    directTabBtn = `
                        <a href="${escapeHtml(deepLinkUrl)}" target="_blank" rel="noreferrer" class="btn-video-tab" title="Apri video in nuova scheda dal min ${startTimeFmt}">
                            ↗️ Nuova Scheda
                        </a>
                    `;
                }

                const lezLinkBtn = l.link_lezione
                    ? `<a href="${escapeHtml(l.link_lezione)}" target="_blank" rel="noreferrer" class="btn-uninettuno-link">🔗 Scheda Lezione</a>`
                    : "";

                const timeBadge = hasTime
                    ? `<span class="lesson-time">⏱️ ${escapeHtml(l.formatted_time)}</span>`
                    : "";

                return `
                    <div class="lesson-item">
                        <div class="lesson-item-header">
                            <span class="lesson-item-title">${escapeHtml(l.lesson_title)}</span>
                            ${timeBadge}
                        </div>
                        ${timelineBarHtml}
                        ${l.snippet ? `<div class="lesson-snippet">"${escapeHtml(l.snippet)}"</div>` : ""}
                        <div class="lesson-actions">
                            ${modalBtn}
                            ${directTabBtn}
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

/* ==========================================================================
   Video Player Modal & Time Helpers
   ========================================================================== */

let currentHls = null;

function formatTimeCompact(seconds) {
    if (!seconds || seconds <= 0) return "00:00";
    const total = Math.floor(seconds);
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hrs > 0) {
        return `${hrs}:${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    return `${mins < 10 ? '0' : ''}${mins}:${secs < 10 ? '0' : ''}${secs}`;
}

function openVideoModal(videoUrl, startTime, endTime, lessonTitle, courseTitle, snippet, lessonLink) {
    if (!videoUrl) return;

    const modal = document.getElementById("videoModal");
    const video = document.getElementById("modalVideoPlayer");
    const titleEl = document.getElementById("modalLessonTitle");
    const courseEl = document.getElementById("modalCourseTitle");
    const timeBadge = document.getElementById("modalTimeBadge");
    const snippetEl = document.getElementById("modalSnippetText");
    const directLink = document.getElementById("modalDirectLinkBtn");
    const statusEl = document.getElementById("modalVideoStatus");
    const statusCyberspazioBtn = document.getElementById("modalStatusCyberspazioBtn");
    const statusDirectBtn = document.getElementById("modalStatusDirectBtn");
    const footerCyberspazioBtn = document.getElementById("modalCyberspazioFooterBtn");

    titleEl.textContent = lessonTitle || "Video Lezione";
    courseEl.textContent = courseTitle || "UNINETTUNO";
    snippetEl.textContent = snippet ? `"${snippet}"` : "Trascrizione del punto saliente spiegato dal docente nel video.";

    const startFmt = formatTimeCompact(startTime);
    const endFmt = formatTimeCompact(endTime);
    if (startTime > 0 || endTime > 0) {
        timeBadge.textContent = `⏱️ Minutaggio: ${startFmt} - ${endFmt}`;
    } else {
        timeBadge.textContent = "⏱️ Inizio Lezione";
    }

    // Direct link with media fragment deep-link #t=
    const deepLink = startTime > 0 ? `${videoUrl}#t=${Math.floor(startTime)}` : videoUrl;
    if (directLink) directLink.href = deepLink;
    if (statusDirectBtn) statusDirectBtn.href = deepLink;

    if (lessonLink) {
        if (statusCyberspazioBtn) {
            statusCyberspazioBtn.href = lessonLink;
            statusCyberspazioBtn.style.display = "inline-flex";
        }
        if (footerCyberspazioBtn) {
            footerCyberspazioBtn.href = lessonLink;
            footerCyberspazioBtn.style.display = "inline-flex";
        }
    } else {
        if (statusCyberspazioBtn) statusCyberspazioBtn.style.display = "none";
        if (footerCyberspazioBtn) footerCyberspazioBtn.style.display = "none";
    }

    // Reset previous HLS instance if any
    if (currentHls) {
        currentHls.destroy();
        currentHls = null;
    }
    video.pause();
    video.removeAttribute("src");
    video.style.display = "block";
    statusEl.style.display = "none";

    const isHls = videoUrl.includes(".m3u8");

    if (isHls && window.Hls && Hls.isSupported()) {
        currentHls = new Hls({ startPosition: startTime > 0 ? startTime : 0 });
        currentHls.loadSource(videoUrl);
        currentHls.attachMedia(video);
        currentHls.on(Hls.Events.MANIFEST_PARSED, function () {
            if (startTime > 0) {
                video.currentTime = startTime;
            }
            video.play().catch(() => {});
        });
        currentHls.on(Hls.Events.ERROR, function (event, data) {
            if (data.fatal) {
                statusEl.style.display = "flex";
                video.style.display = "none";
            }
        });
    } else {
        // Native MP4 (or Safari native HLS)
        video.src = deepLink;
        video.load();

        const seekAndPlay = () => {
            if (startTime > 0) {
                try {
                    video.currentTime = startTime;
                } catch (e) {}
            }
            video.play().catch(() => {});
        };

        video.onloadedmetadata = seekAndPlay;
        video.onerror = () => {
            statusEl.style.display = "flex";
            video.style.display = "none";
        };
    }

    modal.style.display = "flex";
    document.body.style.overflow = "hidden";
}

function closeVideoModal() {
    const modal = document.getElementById("videoModal");
    const video = document.getElementById("modalVideoPlayer");
    const statusEl = document.getElementById("modalVideoStatus");
    if (currentHls) {
        currentHls.destroy();
        currentHls = null;
    }
    if (video) {
        video.pause();
        video.src = "";
        video.style.display = "block";
    }
    if (statusEl) {
        statusEl.style.display = "none";
    }
    if (modal) {
        modal.style.display = "none";
    }
    document.body.style.overflow = "";
}

function handleModalBackdropClick(event) {
    if (event.target.id === "videoModal") {
        closeVideoModal();
    }
}

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        const modal = document.getElementById("videoModal");
        if (modal && modal.style.display !== "none") {
            closeVideoModal();
        }
    }
});

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeAttr(str) {
    if (!str) return "";
    return str
        .replace(/\\/g, "\\\\")
        .replace(/'/g, "\\'")
        .replace(/"/g, "&quot;")
        .replace(/\r?\n/g, " ");
}
