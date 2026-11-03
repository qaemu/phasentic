const translations = {
  en: {
    lede: "Powder X-ray diffraction phase identification",
    sample: "Sample", file: "Pattern file", fileHint: ".xy, .xrdml or ASCII .raw, up to 10 MB. Select several for a batch.",
    chemistry: "Precursor and target formulas", chemistryHint: "Candidates are limited to these elements plus H, C and O.",
    method: "Method", validatedPreset: "Validated method", validatedHint: "The settings tested on 200 sealed scans (with POW_COD). Needs Cu Kα and the formulas above.",
    radiation: "Anode", reference: "Reference database", customSettings: "Custom settings (not validated)",
    tolerance: "Peak tolerance (° 2θ)", maxPhases: "Maximum phases", analysisMode: "Analysis mode", angle: "Angle coordinate",
    customHint: "Ignored while the validated method is selected.",
    optional: "Instrument and calibration", vendor: "Vendor", model: "Model", radius: "Goniometer radius (mm)",
    standardFile: "Standard scan", standard: "Calibration standard", calibrate: "Calibrate",
    calibrationHint: "No calibration attached. A “supported” decision needs one.",
    instrumentPair: "Give both instrument vendor and model, or leave both blank.",
    analyze: "Analyze", running: "Analysing…", done: "Done. Read the result as a ranked hypothesis.",
    noticeTitle: "Read results as ranked hypotheses.",
    noticeText: "On 200 sealed test scans the validated method found the exact phases in 37% and the right compounds in 49.5%, falling sharply for three or more phases. Confirm before you report.",
    emptyTitle: "No analysis yet",
    emptyText: "Choose a scan, type the precursor and target formulas, keep the validated method selected and press Analyze. The fit, the competing hypotheses, the quality checks and a printable report appear here.",
    decisionLabel: "Decision", selected: "Selected phases", noMixture: "No mixture selected",
    downloadReport: "Download report", download: "JSON",
    hypotheses: "Phase hypotheses", phaseEvidence: "Evidence per phase", candidates: "Single-phase candidates", diagnostics: "Quality and provenance",
    decisions: { supported: "Supported", tentative: "Tentative", unresolved: "Unresolved", rejected: "Rejected" },
    hypSet: "Phase set", hypStatus: "Status", hypScore: "Selection score (lower is better)", hypUnexplained: "Unexplained peaks", hypMissing: "Missing lines", selectedTag: "selected",
    mixtureHint: "No mixture hypotheses: this analysis ran in single-phase mode.",
    mixtureScaleWarning: "Scores rank fits of this scan only; they are not probabilities, and fitted heights are not phase fractions.",
    mixtureQuery: "Search details",
    candPhase: "Phase", candSg: "Space group", candRef: "Reference", candScore: "Score", candLines: "Lines matched", candRmse: "Position RMSE", candStatus: "Status",
    empty: "No candidates.",
    factSn: "Signal-to-noise", factBaseline: "Background share", factCalibration: "Calibration", factReference: "Reference database", factPeaks: "Detected peaks", factDisplacement: "Displacement correction", factPoints: "Points", factRange: "Range",
    provenance: "Full provenance", analysisProvenance: "Analysis provenance", fileName: "File name", inputSha: "Input SHA-256", referenceSource: "Reference source",
    algorithmVersion: "Algorithm", coordinateCorrection: "Coordinate correction", referenceEntries: "Reference entries", sourceUrls: "Reference source URLs",
    referenceQuery: "Reference query", settingsProvenance: "Analysis settings",
    mixtureQueryCandidatePool: "Candidate pool", mixtureQueryRequeries: "Residual re-queries", mixtureQueryMaxFitAttempts: "Max fit attempts",
    mixtureQueryRetainedBranches: "Retained branches", mixtureQueryFitAttempts: "Fit attempts", mixtureQueryTolerance: "Peak tolerance",
    mixtureQueryBackground: "Background model", mixtureQueryStop: "Stopping reason",
    cancel: "Cancel", cancelled: "Cancelled.", zoomHint: "Drag over the graph to zoom; double-click to reset.",
    stages: { started: "reading the scan and finding peaks", import_and_peak_detection: "opening the reference database", store_open_and_displacement: "looking up candidates", candidate_lookup: "scoring candidates", matching_and_qualx: "grouping equivalent entries", equivalence: "fitting phase mixtures (slowest step)", mixture_search: "writing the report" },
    history: "Recent analyses", historyEmpty: "Analyses you run are kept here, on this computer.", historyPinned: "phases fixed by you", historyNoScan: "Opened from history: to refit with a chosen alternative, select the scan again.",
    batch: "Batch", csv: "CSV", batchFile: "File", batchStatus: "Status", batchWaiting: "waiting", batchRunning: "running", batchDone: "done", batchFailed: "failed", batchProgress: (i, n) => `Batch: scan ${i} of ${n}`, batchFinished: (ok, n) => `Batch finished: ${ok} of ${n} analysed. Click a row to open it.`,
    alternatives: "Alternatives per phase",
    altIntro: "How well each entry fits in a phase's place (100% = perfect fit), with the other materials within 80% of the best one; other entries of the same material are left out. Choosing one fixes it and searches the smaller phases again.",
    altFit: "Fit", altUse: "Use this", altNone: "No other material fits within 80% of the best.", altSelected: "selected",
    pinned: "Fixed by you:", unpin: "Clear and analyze again",
    stale: "A setting changed, so the previous result was cleared.",
    footer: "Runs on this computer; scans are not uploaded anywhere.", footerAi: "Open source (MIT). No AI model is used to analyse scans.",
  },
  es: {
    lede: "Identificación de fases por difracción de rayos X de polvo",
    sample: "Muestra", file: "Archivo del patrón", fileHint: ".xy, .xrdml o .raw ASCII, hasta 10 MB. Seleccione varios para un lote.",
    chemistry: "Fórmulas de precursores y objetivo", chemistryHint: "Los candidatos se limitan a estos elementos más H, C y O.",
    method: "Método", validatedPreset: "Método validado", validatedHint: "La configuración probada en 200 escaneos sellados (con POW_COD). Requiere Cu Kα y las fórmulas de arriba.",
    radiation: "Ánodo", reference: "Base de referencias", customSettings: "Configuración personalizada (no validada)",
    tolerance: "Tolerancia de pico (° 2θ)", maxPhases: "Máximo de fases", analysisMode: "Modo de análisis", angle: "Coordenada angular",
    customHint: "Se ignora mientras el método validado está seleccionado.",
    optional: "Instrumento y calibración", vendor: "Fabricante", model: "Modelo", radius: "Radio del goniómetro (mm)",
    standardFile: "Escaneo estándar", standard: "Estándar de calibración", calibrate: "Calibrar",
    calibrationHint: "Sin calibración. Una decisión “supported” la necesita.",
    instrumentPair: "Indique fabricante y modelo, o deje ambos vacíos.",
    analyze: "Analizar", running: "Analizando…", done: "Listo. Lea el resultado como una hipótesis ordenada.",
    noticeTitle: "Lea los resultados como hipótesis ordenadas.",
    noticeText: "En 200 escaneos de prueba sellados, el método validado encontró las fases exactas en el 37% y los compuestos correctos en el 49,5%, con una caída fuerte para tres o más fases. Confirme antes de informar.",
    emptyTitle: "Todavía no hay análisis",
    emptyText: "Elija un escaneo, escriba las fórmulas de precursores y objetivo, mantenga el método validado y pulse Analizar. El ajuste, las hipótesis en competencia, los controles de calidad y un informe imprimible aparecerán aquí.",
    decisionLabel: "Decisión", selected: "Fases seleccionadas", noMixture: "No se seleccionó una mezcla",
    downloadReport: "Descargar informe", download: "JSON",
    hypotheses: "Hipótesis de fases", phaseEvidence: "Evidencia por fase", candidates: "Candidatos de una sola fase", diagnostics: "Calidad y procedencia",
    decisions: { supported: "Respaldada", tentative: "Tentativa", unresolved: "Sin resolver", rejected: "Rechazada" },
    hypSet: "Conjunto de fases", hypStatus: "Estado", hypScore: "Puntuación de selección (menor es mejor)", hypUnexplained: "Picos sin explicar", hypMissing: "Líneas ausentes", selectedTag: "seleccionada",
    mixtureHint: "Sin hipótesis de mezcla: este análisis se ejecutó en modo de una sola fase.",
    mixtureScaleWarning: "Las puntuaciones ordenan ajustes de este escaneo; no son probabilidades y las alturas ajustadas no son fracciones de fase.",
    mixtureQuery: "Detalles de la búsqueda",
    candPhase: "Fase", candSg: "Grupo espacial", candRef: "Referencia", candScore: "Puntuación", candLines: "Líneas coincidentes", candRmse: "RMSE de posición", candStatus: "Estado",
    empty: "Sin candidatos.",
    factSn: "Señal/ruido", factBaseline: "Fracción de fondo", factCalibration: "Calibración", factReference: "Base de referencias", factPeaks: "Picos detectados", factDisplacement: "Corrección de desplazamiento", factPoints: "Puntos", factRange: "Rango",
    provenance: "Procedencia completa", analysisProvenance: "Procedencia del análisis", fileName: "Archivo", inputSha: "SHA-256 de entrada", referenceSource: "Fuente de referencias",
    algorithmVersion: "Algoritmo", coordinateCorrection: "Corrección de coordenadas", referenceEntries: "Entradas de referencia", sourceUrls: "URL de referencias",
    referenceQuery: "Consulta de referencias", settingsProvenance: "Configuración del análisis",
    mixtureQueryCandidatePool: "Conjunto de candidatos", mixtureQueryRequeries: "Nuevas consultas por residual", mixtureQueryMaxFitAttempts: "Máximo de intentos de ajuste",
    mixtureQueryRetainedBranches: "Ramas retenidas", mixtureQueryFitAttempts: "Intentos de ajuste", mixtureQueryTolerance: "Tolerancia de pico",
    mixtureQueryBackground: "Modelo de fondo", mixtureQueryStop: "Razón de parada",
    cancel: "Cancelar", cancelled: "Cancelado.", zoomHint: "Arrastre sobre el gráfico para ampliar; doble clic para restablecer.",
    stages: { started: "leyendo el escaneo y buscando picos", import_and_peak_detection: "abriendo la base de referencias", store_open_and_displacement: "buscando candidatos", candidate_lookup: "puntuando candidatos", matching_and_qualx: "agrupando entradas equivalentes", equivalence: "ajustando mezclas de fases (el paso más lento)", mixture_search: "escribiendo el informe" },
    history: "Análisis recientes", historyEmpty: "Los análisis que ejecute se guardan aquí, en esta computadora.", historyPinned: "fases fijadas por usted", historyNoScan: "Abierto desde el historial: para reajustar con una alternativa, seleccione el escaneo otra vez.",
    batch: "Lote", csv: "CSV", batchFile: "Archivo", batchStatus: "Estado", batchWaiting: "en espera", batchRunning: "en curso", batchDone: "listo", batchFailed: "falló", batchProgress: (i, n) => `Lote: escaneo ${i} de ${n}`, batchFinished: (ok, n) => `Lote terminado: ${ok} de ${n} analizados. Haga clic en una fila para abrirla.`,
    alternatives: "Alternativas por fase",
    altIntro: "Qué tan bien ajusta cada entrada en el lugar de una fase (100% = ajuste perfecto), con los otros materiales dentro del 80% del mejor; se omiten otras entradas del mismo material. Elegir una la fija y vuelve a buscar las fases menores.",
    altFit: "Ajuste", altUse: "Usar esta", altNone: "Ningún otro material ajusta dentro del 80% del mejor.", altSelected: "seleccionada",
    pinned: "Fijadas por usted:", unpin: "Quitar y analizar de nuevo",
    stale: "Cambió una configuración, así que se borró el resultado anterior.",
    footer: "Se ejecuta en esta computadora; los escaneos no se suben a ningún lado.", footerAi: "Código abierto (MIT). No se usa ningún modelo de IA para analizar escaneos.",
  },
};

const $ = (id) => document.getElementById(id);
const form = $("analysis-form");
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const R = () => window.PhasenticReport;
let calibrationResult = null;
let calibrationRequest = 0;
let latestReport = null;
let analysisRequest = 0;
let activeAnalysisController = null;
let pinnedIds = [];  // phases the operator fixed from the alternatives
let currentFile = null;  // scan behind the shown report (null when opened from history)
let fitView = null;  // zoomed range of the fit figure
let batchRows = [];  // {file, report, error, state}

function currentLanguage() {
  return translations[$("language").value] || translations.en;
}

function setLanguage(language) {
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    if (element.id === "calibration-status" && calibrationResult) return;
    const text = translations[language][element.dataset.i18n];
    if (typeof text === "string") element.textContent = text;
  });
}

function setCalibrationStatus(message) {
  const element = $("calibration-status");
  element.removeAttribute("data-i18n");
  element.textContent = message;
}

function appendKeyValueList(parent, entries, className = "provenance-list") {
  const list = document.createElement("dl"); list.className = className;
  entries.forEach(([label, value]) => {
    if (value == null || value === "") return;
    const term = document.createElement("dt"); term.textContent = label;
    const description = document.createElement("dd");
    const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    if (text.length > 160) {
      const details = document.createElement("details"); const summary = document.createElement("summary");
      summary.textContent = `${text.length.toLocaleString()} characters`;
      const pre = document.createElement("pre"); pre.textContent = text;
      details.append(summary, pre); description.appendChild(details);
    } else {
      description.textContent = text;
    }
    list.append(term, description);
  });
  if (list.children.length) parent.appendChild(list);
}

function fetchJsonOrThrow(response, fallback) {
  return response.json().catch(() => ({})).then((payload) => {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error(fallback);
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : fallback);
    if (payload.success === false) throw new Error(typeof payload.error === "string" ? payload.error : fallback);
    return payload;
  });
}

// The page CSP forbids inline style attributes; re-apply them through the
// CSSOM, which CSP allows. Markup comes from escaped values only.
function setHTML(element, markup) {
  element.innerHTML = String(markup).replace(/ style="/g, ' data-style="');
  element.querySelectorAll("[data-style]").forEach((node) => { node.style.cssText = node.dataset.style; });
}

// The local database is either Phasentic's COD build (release "PXRD_COD …") or POW_COD.
function databaseLabel(release) {
  if (typeof release !== "string" || !release) return "Reference database";
  return release.includes("COD") ? release : `POW_COD ${release}`;
}

function selectedHypothesis(report) {
  const m = report && report.mixture;
  return m && Array.isArray(m.hypotheses) ? m.hypotheses.find((h) => h && h.hypothesis_id === m.selected_hypothesis_id) || null : null;
}

// Hypotheses as one compact table; markup comes from escaped values and the report helpers.
function renderMixtureSummary(parent, report) {
  const L = currentLanguage();
  parent.replaceChildren();
  const mixture = report && report.mixture && typeof report.mixture === "object" ? report.mixture : null;
  const hyps = mixture && Array.isArray(mixture.hypotheses) ? mixture.hypotheses.filter((h) => h && typeof h === "object") : [];
  if (!hyps.length) { const p = document.createElement("p"); p.className = "note"; p.textContent = L.mixtureHint; parent.appendChild(p); return; }
  const max = Math.max(...hyps.map((h) => Number(h.selection_score) || 0)) || 1;
  const rows = hyps.map((h) => {
    const sel = h.hypothesis_id === mixture.selected_hypothesis_id;
    const set = (h.components || []).map((c) => R().formula(c.formula)).join(" + ") || "—";
    const score = Number(h.selection_score);
    const bar = Number.isFinite(score) ? `<span class="bar" style="width:${Math.max(2, (score / max) * 110).toFixed(0)}px"></span>${score.toFixed(4)}` : "—";
    return `<tr class="${sel ? "selected" : ""}"><td class="f">${set}${sel ? ` <span class="tag">${esc(L.selectedTag)}</span>` : ""}</td><td>${esc(h.status)}</td><td class="num">${bar}</td><td class="num">${(h.unexplained_peak_positions || []).length}</td><td class="num">${(h.missing_expected_lines || []).length}</td></tr>`;
  }).join("");
  const wrap = document.createElement("div");
  setHTML(wrap, `<table><thead><tr><th>${esc(L.hypSet)}</th><th>${esc(L.hypStatus)}</th><th class="num">${esc(L.hypScore)}</th><th class="num">${esc(L.hypUnexplained)}</th><th class="num">${esc(L.hypMissing)}</th></tr></thead><tbody>${rows}</tbody></table><p class="note">${esc(L.mixtureScaleWarning)}</p>`);
  parent.appendChild(wrap);
  const query = mixture.query && typeof mixture.query === "object" ? mixture.query : {};
  const details = document.createElement("details"); details.className = "provenance";
  const summary = document.createElement("summary"); summary.textContent = L.mixtureQuery; details.appendChild(summary);
  appendKeyValueList(details, [
    [L.algorithmVersion, mixture.algorithm_version],
    [L.mixtureQueryCandidatePool, query.candidate_pool_size == null ? query.candidate_pool : `${query.candidate_pool_size} / ${query.candidate_pool_limit == null ? "—" : query.candidate_pool_limit}`],
    [L.mixtureQueryRequeries, query.residual_candidate_requeries],
    [L.mixtureQueryMaxFitAttempts, query.max_fit_attempts],
    [L.mixtureQueryRetainedBranches, query.retained_branches],
    [L.mixtureQueryFitAttempts, query.fit_attempts],
    [L.mixtureQueryTolerance, query.tolerance_deg == null ? null : `${query.tolerance_deg}°`],
    [L.mixtureQueryBackground, query.background_model],
    [L.mixtureQueryStop, query.stopping_reason],
  ]);
  parent.appendChild(details);
}

// Per selected phase: materials that fit nearly as well in its place, best first.
// "Use this" fixes that entry plus the larger phases listed before it, then
// analyses again so the smaller phases are searched around the choice.
function renderAlternatives(parent, report) {
  const L = currentLanguage();
  const m = report.mixture || {};
  const best = selectedHypothesis(report) || (m.hypotheses || [])[0];
  const alts = m.phase_alternatives && typeof m.phase_alternatives === "object" ? m.phase_alternatives : {};
  const comps = best ? (best.components || []).filter((c) => alts[c.reference_id] && typeof alts[c.reference_id] === "object") : [];
  $("alternatives-part").hidden = !comps.length && !pinnedIds.length;
  const pinnedNote = pinnedIds.length ? `<p class="note">${esc(L.pinned)} ${pinnedIds.map((id) => R().codLink(id)).join(", ")} <button type="button" class="secondary" data-unpin="1">${esc(L.unpin)}</button></p>` : "";
  const blocks = comps.map((c, index) => {
    const entry = alts[c.reference_id];
    const list = Array.isArray(entry.alternatives) ? entry.alternatives : [];
    const row = (a, own) => `<tr${own ? ' class="selected"' : ""}><td class="f">${R().formula(a.formula)}</td><td>${R().spaceGroup(a.space_group)}</td><td>${R().codLink(a.reference_id)}</td><td class="num"><span class="bar" style="width:${Math.max(2, Number(a.fit_percent) * 1.1).toFixed(0)}px"></span>${Number(a.fit_percent).toFixed(1)}%</td><td>${own ? `<span class="tag">${esc(L.altSelected)}</span>` : currentFile ? `<button type="button" class="secondary" data-pin="${esc(a.reference_id)}" data-phase="${index}">${esc(L.altUse)}</button>` : ""}</td></tr>`;
    // Selected and alternatives in one list, best fit first.
    const body = [{ ...c, fit_percent: entry.fit_percent, own: true }, ...list]
      .sort((x, y) => Number(y.fit_percent) - Number(x.fit_percent))
      .map((a) => row(a, a.own === true)).join("");
    return `<h3>${R().formula(c.formula)}</h3><table><thead><tr><th>${esc(L.candPhase)}</th><th>${esc(L.candSg)}</th><th>${esc(L.candRef)}</th><th class="num">${esc(L.altFit)}</th><th></th></tr></thead><tbody>${body}</tbody></table>${list.length ? "" : `<p class="note">${esc(L.altNone)}</p>`}`;
  }).join("");
  setHTML(parent, `${pinnedNote}<p class="note">${esc(L.altIntro)}</p>${currentFile ? "" : `<p class="note">${esc(L.historyNoScan)}</p>`}${blocks}`);
  parent.querySelectorAll("[data-pin]").forEach((button) => button.addEventListener("click", () => {
    const index = Number(button.dataset.phase);
    pinnedIds = [...comps.slice(0, index).map((c) => c.reference_id), button.dataset.pin];
    void analyzeSingle(currentFile);
  }));
  parent.querySelectorAll("[data-unpin]").forEach((button) => button.addEventListener("click", () => { pinnedIds = []; if (currentFile) void analyzeSingle(currentFile); }));
}

function renderCandidates(parent, report) {
  const L = currentLanguage();
  const list = (report.candidates || []).slice(0, 10);
  if (!list.length) { setHTML(parent, `<p class="note">${esc(L.empty)}</p>`); return; }
  const rows = list.map((c, i) => `<tr><td class="num">${i + 1}</td><td class="f">${R().formula(c.formula)}</td><td>${R().spaceGroup(c.space_group)}</td><td>${R().codLink(c.reference_id)}</td><td class="num">${(Number(c.score) * 100).toFixed(1)}%</td><td class="num">${esc(c.matched_peaks)}/${esc(c.expected_peaks)}</td><td class="num">${c.position_rmse_deg == null ? "—" : `${Number(c.position_rmse_deg).toFixed(3)}°`}</td><td>${esc(c.status)}</td></tr>`).join("");
  setHTML(parent, `<table><thead><tr><th class="num">#</th><th>${esc(L.candPhase)}</th><th>${esc(L.candSg)}</th><th>${esc(L.candRef)}</th><th class="num">${esc(L.candScore)}</th><th class="num">${esc(L.candLines)}</th><th class="num">${esc(L.candRmse)}</th><th>${esc(L.candStatus)}</th></tr></thead><tbody>${rows}</tbody></table>`);
}

function renderAnalysisProvenance(parent, report) {
  if (!parent || !report || typeof report !== "object") return;
  const L = currentLanguage();
  const provenance = report.provenance && typeof report.provenance === "object" ? report.provenance : {};
  const input = report.input && typeof report.input === "object" ? report.input : {};
  const heading = document.createElement("h3"); heading.className = "provenance-heading"; heading.textContent = L.analysisProvenance; parent.appendChild(heading);
  appendKeyValueList(parent, [
    [L.fileName, input.file_name],
    [L.inputSha, input.sha256],
    [L.referenceSource, provenance.reference_source],
    ["POW_COD release", provenance.powcod_release],
    ["POW_COD database SHA-256", provenance.powcod_database_sha256],
    ["POW_COD cache SHA-256", provenance.powcod_cache_sha256],
    ["POW_COD intensity policy", provenance.reference_query?.intensity_policy],
    [L.algorithmVersion, provenance.algorithm_version],
    [L.coordinateCorrection, provenance.coordinate_correction],
    [L.referenceEntries, provenance.cod_entry_ids || provenance.cod_entries],
    [L.sourceUrls, provenance.cod_source_urls],
    [L.referenceQuery, provenance.reference_query],
    [L.settingsProvenance, provenance.settings],
  ]);
}

function renderDiagnostics(parent, report) {
  const L = currentLanguage();
  const q = report.quality || {}, p = report.provenance || {}, input = report.input || {};
  const sn = Number(q.signal_to_noise), base = Number(q.baseline_fraction), disp = Number(p.coordinate_correction?.sample_displacement_deg);
  const facts = [
    [L.factSn, Number.isFinite(sn) ? sn.toFixed(0) : "—"],
    [L.factBaseline, Number.isFinite(base) ? `${(base * 100).toFixed(0)}%` : "—"],
    [L.factCalibration, q.calibration_status || "—"],
    [L.factReference, p.reference_source === "pow_cod" ? databaseLabel(p.powcod_release) : "demo"],
    [L.factPeaks, (report.peaks || []).length],
    [L.factDisplacement, Number.isFinite(disp) ? `${disp.toFixed(3)}°` : "—"],
    [L.factPoints, input.point_count ?? "—"],
    [L.factRange, Number.isFinite(Number(input.angle_min_deg)) ? `${Number(input.angle_min_deg).toFixed(1)}–${Number(input.angle_max_deg).toFixed(1)}°` : "—"],
  ];
  setHTML(parent, `<dl class="facts">${facts.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>${(q.warnings || []).length ? `<ul class="warnings">${q.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}`);
  const details = document.createElement("details"); details.className = "provenance";
  const summary = document.createElement("summary"); summary.textContent = L.provenance; details.appendChild(summary);
  renderAnalysisProvenance(details, report);
  parent.appendChild(details);
}

// Fit figure with drag-to-zoom: drag a box (or a horizontal span) to zoom, double-click to reset.
function drawFit(report) {
  setHTML($("plot"), R().figures.fit(report, fitView));
  const svg = $("plot").querySelector("svg[data-zoom]");
  if (!svg) return;
  const [left, right, top, mainH, bottom, xmin, xmax, ymin, ymax] = svg.dataset.zoom.split(",").map(Number);
  const local = (event) => { const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY; return point.matrixTransform(svg.getScreenCTM().inverse()); };
  const clampX = (v) => Math.min(right, Math.max(left, v));
  const toX = (v) => xmin + ((clampX(v) - left) / (right - left)) * (xmax - xmin);
  const toY = (v) => ymin + ((top + mainH - Math.min(top + mainH, Math.max(top, v))) / mainH) * (ymax - ymin);
  let start = null, box = null;
  svg.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    const p = local(event);
    if (p.x < left || p.x > right || p.y < top || p.y > bottom) return;
    event.preventDefault();
    start = p;
    box = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    box.setAttribute("class", "zoom-box");
    svg.appendChild(box);
  });
  svg.addEventListener("mousemove", (event) => {
    if (!start) return;
    const p = local(event);
    const x0 = clampX(Math.min(start.x, p.x)), x1 = clampX(Math.max(start.x, p.x));
    const inMain = start.y <= top + mainH && Math.abs(p.y - start.y) > 6;
    const y0 = inMain ? Math.max(top, Math.min(start.y, p.y)) : top, y1 = inMain ? Math.min(top + mainH, Math.max(start.y, p.y)) : bottom;
    box.setAttribute("x", x0); box.setAttribute("width", x1 - x0); box.setAttribute("y", y0); box.setAttribute("height", y1 - y0);
  });
  const finish = (event) => {
    if (!start) return;
    const p = local(event);
    const begin = start;
    start = null; box.remove();
    if (Math.abs(p.x - begin.x) < 4) return;  // a click, not a drag
    const view = { x0: toX(Math.min(begin.x, p.x)), x1: toX(Math.max(begin.x, p.x)) };
    if (begin.y <= top + mainH && Math.abs(p.y - begin.y) > 6) { view.y0 = toY(Math.max(begin.y, p.y)); view.y1 = toY(Math.min(begin.y, p.y)); }
    fitView = view;
    drawFit(report);
  };
  svg.addEventListener("mouseup", finish);
  svg.addEventListener("mouseleave", (event) => { if (start) finish(event); });
  svg.addEventListener("dblclick", () => { fitView = null; drawFit(report); });
}

function renderReport(report) {
  latestReport = report;
  const L = currentLanguage();
  $("empty-state").hidden = true; $("result").hidden = false;
  const decision = $("decision");
  decision.dataset.state = report.decision || "";
  decision.textContent = (L.decisions && L.decisions[report.decision]) || String(report.decision || "—");
  const sel = selectedHypothesis(report);
  const colors = R().PHASE_COLORS;
  setHTML($("phase-summary"), sel && (sel.components || []).length
    ? sel.components.map((c, i) => `<span><i style="background:${colors[i % colors.length]}"></i>${R().formula(c.formula)}<em>${R().spaceGroup(c.space_group)}</em></span>`).join("")
    : `<span><em>${esc(L.noMixture)}</em></span>`);
  const input = report.input || {};
  $("analysis-id").textContent = `${report.analysis_id || ""} · ${input.file_name || ""} · ${report.radiation?.label || ""}`;
  drawFit(report);
  const evidence = sel ? R().figures.phases(report) : "";
  setHTML($("phase-evidence"), evidence);
  $("evidence-fold").hidden = !evidence;
  renderMixtureSummary($("mixture-content"), report);
  renderAlternatives($("alternatives-content"), report);
  renderCandidates($("candidate-list"), report);
  renderDiagnostics($("diagnostic-content"), report);
}

function clearRenderedReport() {
  latestReport = null;
  $("result").hidden = true; $("empty-state").hidden = false;
  ["plot", "phase-evidence", "phase-summary", "mixture-content", "alternatives-content", "candidate-list", "diagnostic-content"].forEach((id) => { $(id).replaceChildren(); });
  $("decision").textContent = "—"; $("analysis-id").textContent = "";
}

// The validated method fixes the search settings, so the custom ones are inactive.
function syncPreset() {
  const on = $("validated-preset").checked;
  ["tolerance", "analysis-mode", "max-phases"].forEach((id) => { $(id).disabled = on; });
  $("custom-settings").classList.toggle("is-off", on);
}
$("validated-preset").addEventListener("change", syncPreset);
syncPreset();

function invalidateAnalysis(message = translations[$("language").value].stale) {
  pinnedIds = []; currentFile = null; batchRows = []; $("batch").hidden = true;
  analysisRequest += 1;
  if (activeAnalysisController) activeAnalysisController.abort();
  activeAnalysisController = null;
  setRunning(false);
  clearRenderedReport();
  $("form-status").textContent = message;
}

function invalidateCalibration(message) {
  calibrationRequest += 1;
  calibrationResult = null;
  setCalibrationStatus(message);
}

// In the Phasentic app window (pywebview) files are saved through a save dialog
// and links open in the system browser, so the window never navigates away.
function saveFile(name, text, type) {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.save_file(name, text).catch((error) => { $("form-status").textContent = `Could not save ${name}: ${error.message || error}`; });
    return;
  }
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a"); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.addEventListener("click", (event) => {
  const link = event.target.closest && event.target.closest("a[href]");
  if (!link || !window.pywebview || !window.pywebview.api || link.getAttribute("href") === "/") return;
  event.preventDefault();
  window.pywebview.api.open_url(link.href);
});

let appVersion = "";
fetch("/api/v1/health").then((r) => r.json()).then((d) => { appVersion = d.version || ""; }).catch(() => {});
$("download-pdf-report").addEventListener("click", () => {
  if (!latestReport || !window.PhasenticReport) return;
  const html = window.PhasenticReport.build(latestReport, { version: appVersion, preset: $("validated-preset").checked ? "validated" : null });
  saveFile(`phasentic-report-${latestReport.analysis_id || "analysis"}.html`, html, "text/html");
});
$("download-report").addEventListener("click", () => {
  if (!latestReport) return;
  saveFile(`${latestReport.analysis_id || "xrd-report"}.json`, JSON.stringify(latestReport, null, 2), "application/json");
});


$("language").addEventListener("change", (event) => {
  setLanguage(event.target.value);
  if (latestReport) renderReport(latestReport);
  if (batchRows.length) renderBatch();
  void loadHistory();
});
$("calibrate-button").addEventListener("click", async () => {
  const file = $("standard-file").files[0];
  if (!file) { setCalibrationStatus("Select a standard scan first."); return; }
  if (file.size > 10 * 1024 * 1024) { setCalibrationStatus("File exceeds the 10 MiB limit."); return; }
  const requestId = ++calibrationRequest;
  setCalibrationStatus("Calibrating line positions…");
  const data = new FormData();
  data.append("file", file);
  data.append("standard_id", $("standard-id").value);
  data.append("radiation", $("radiation").value);
  try {
    const response = await fetch("/api/v1/calibrate", { method: "POST", body: data });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Calibration failed");
    if (requestId !== calibrationRequest) return;
    calibrationResult = payload.data;
    invalidateAnalysis("Calibration changed; analyze the sample again.");
    setCalibrationStatus(`${calibrationResult.status} · ${calibrationResult.line_count} lines · RMSE ${calibrationResult.rmse_deg == null ? "—" : `${calibrationResult.rmse_deg.toFixed(3)}°`}`);
  } catch (error) {
    if (requestId !== calibrationRequest) return;
    calibrationResult = null;
    setCalibrationStatus(error instanceof Error ? error.message : "Calibration failed.");
  }
});

$("radiation").addEventListener("change", () => {
  invalidateAnalysis();
  invalidateCalibration("Radiation changed; calibrate the standard again.");
  void loadCapabilities();
});

$("standard-id").addEventListener("change", () => {
  invalidateAnalysis();
  invalidateCalibration("Standard changed; calibrate the standard again.");
});

$("standard-file").addEventListener("change", () => {
  invalidateAnalysis();
  invalidateCalibration("Standard scan changed; calibrate the standard again.");
});

// A file dropped anywhere is selected instead of being opened, which would
// replace Phasentic (and the results) in the browser tab or app window.
document.addEventListener("dragover", (event) => event.preventDefault());
document.addEventListener("drop", (event) => {
  event.preventDefault();
  const files = event.dataTransfer && event.dataTransfer.files;
  if (!files || !files.length) return;
  const input = event.target.matches && event.target.matches("input[type=file]") ? event.target : $("file");
  input.files = files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
});
$("file").addEventListener("change", () => {
  invalidateAnalysis();
});

[
  "angle-unit",
  "tolerance",
  "analysis-mode",
  "max-phases",
  "chemistry",
  "validated-preset",
  "instrument-vendor",
  "instrument-model",
  "instrument-radius",
].forEach((id) => $(id).addEventListener("change", () => {
  invalidateAnalysis();
}));

$("reference-source").addEventListener("change", () => {
  invalidateAnalysis();
  if ($("reference-source").value === "pow_cod" && $("reference-source").selectedOptions[0].disabled) {
    $("reference-source").value = "demo";
    $("form-status").textContent = "No reference database is installed.";
  }
});

// Settings for one request, from the form; a string is a message for the user.
function formSettings() {
  const instrument = {};
  const vendor = $("instrument-vendor").value.trim();
  const model = $("instrument-model").value.trim();
  if ((vendor && !model) || (!vendor && model)) return translations[$("language").value].instrumentPair;
  if (vendor || model) {
    instrument.vendor = vendor;
    instrument.model = model;
    instrument.geometry = "reflection_bragg_brentano";
    instrument.radiation = $("radiation").value;
    instrument.k_alpha_treatment = "auto_from_source";
    const radius = Number($("instrument-radius").value);
    if (Number.isFinite(radius) && radius > 0) instrument.goniometer_radius_mm = radius;
  }
  const chemistry = $("chemistry").value.trim();
  const common = { radiation: $("radiation").value, angle_unit: $("angle-unit").value, reference_source: $("reference-source").value, ...(chemistry ? { chemistry } : {}), ...(Object.keys(instrument).length ? { instrument } : {}) };
  return $("validated-preset").checked
    ? { ...common, preset: "validated" }
    : { ...common, peak_tolerance_deg: Number($("tolerance").value), analysis_mode: $("analysis-mode").value, max_phases: Number($("max-phases").value) };
}

// Shows the running stage until the request ends.
function watchProgress(prefix) {
  const timer = setInterval(async () => {
    try {
      const stage = (await (await fetch("/api/v1/progress")).json())?.data?.stage;
      const label = stage && currentLanguage().stages[stage];
      if (label) $("form-status").textContent = `${prefix}${currentLanguage().running} ${label}…`;
    } catch (_error) { /* progress is cosmetic */ }
  }, 700);
  return () => clearInterval(timer);
}

// One scan through /analyze; resolves to the report, rejects with an Error (AbortError when cancelled).
async function requestAnalysis(file, settings, signal) {
  if (file.size > 10 * 1024 * 1024) throw new Error("File exceeds the 10 MiB limit.");
  const data = new FormData();
  data.append("file", file);
  data.append("settings_json", JSON.stringify(settings));
  data.append("calibration_json", JSON.stringify(calibrationResult || {}));
  const response = await fetch("/api/v1/analyze", { method: "POST", body: data, signal });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Analysis failed");
  return payload.data;
}

function setRunning(running) {
  $("cancel-button").hidden = !running;
  form.querySelector("button[type=submit]").disabled = running;
}

async function analyzeSingle(file) {
  const settings = formSettings();
  if (typeof settings === "string") { $("form-status").textContent = settings; return; }
  if (pinnedIds.length) settings.pinned_reference_ids = pinnedIds;
  if (activeAnalysisController) activeAnalysisController.abort();
  const requestId = ++analysisRequest;
  const controller = new AbortController();
  activeAnalysisController = controller;
  $("form-status").textContent = currentLanguage().running;
  setRunning(true);
  const stop = watchProgress("");
  try {
    const report = await requestAnalysis(file, settings, controller.signal);
    if (requestId !== analysisRequest) return;
    currentFile = file; fitView = null;
    renderReport(report); $("form-status").textContent = currentLanguage().done;
    void loadHistory();
  } catch (error) {
    if (requestId !== analysisRequest) return;
    $("form-status").textContent = error && error.name === "AbortError" ? currentLanguage().cancelled : error instanceof Error ? error.message : "Analysis failed.";
  } finally {
    stop();
    if (requestId === analysisRequest) { activeAnalysisController = null; setRunning(false); }
  }
}

// Several scans, one after another, with the same settings. Rows open their report.
async function analyzeBatch(files) {
  const settings = formSettings();
  if (typeof settings === "string") { $("form-status").textContent = settings; return; }
  pinnedIds = [];
  if (activeAnalysisController) activeAnalysisController.abort();
  const requestId = ++analysisRequest;
  const controller = new AbortController();
  activeAnalysisController = controller;
  batchRows = files.map((file) => ({ file, report: null, error: null, state: "batchWaiting" }));
  $("batch").hidden = false;
  renderBatch();
  setRunning(true);
  try {
    for (const [i, row] of batchRows.entries()) {
      if (controller.signal.aborted || requestId !== analysisRequest) break;
      row.state = "batchRunning"; renderBatch();
      const prefix = `${currentLanguage().batchProgress(i + 1, batchRows.length)} · `;
      $("form-status").textContent = prefix + currentLanguage().running;
      const stop = watchProgress(prefix);
      try {
        row.report = await requestAnalysis(row.file, settings, controller.signal);
        row.state = "batchDone";
      } catch (error) {
        if (error && error.name === "AbortError") { row.state = "batchWaiting"; break; }
        row.error = error instanceof Error ? error.message : "Analysis failed"; row.state = "batchFailed";
      } finally {
        stop();
      }
      renderBatch();
    }
  } finally {
    if (requestId === analysisRequest) {
      activeAnalysisController = null; setRunning(false);
      const ok = batchRows.filter((row) => row.report).length;
      $("form-status").textContent = controller.signal.aborted ? currentLanguage().cancelled : currentLanguage().batchFinished(ok, batchRows.length);
      renderBatch();
      void loadHistory();
    }
  }
}

function batchPhases(report) {
  const sel = report && selectedHypothesis(report);
  return sel ? (sel.components || []) : [];
}

function renderBatch() {
  const L = currentLanguage();
  const rows = batchRows.map((row, i) => {
    const phases = batchPhases(row.report).map((c) => R().formula(c.formula)).join(" + ");
    const decision = row.report ? esc((L.decisions && L.decisions[row.report.decision]) || row.report.decision) : "";
    const status = row.error ? `${esc(L.batchFailed)}: ${esc(row.error)}` : esc(L[row.state]);
    return `<tr data-batch="${i}"${row.report ? ' class="clickable"' : ""}><td>${esc(row.file.name)}</td><td class="f">${phases || "—"}</td><td>${decision}</td><td>${status}</td></tr>`;
  }).join("");
  setHTML($("batch-content"), `<table><thead><tr><th>${esc(L.batchFile)}</th><th>${esc(L.selected)}</th><th>${esc(L.decisionLabel)}</th><th>${esc(L.batchStatus)}</th></tr></thead><tbody>${rows}</tbody></table>`);
  $("batch-content").querySelectorAll("tr[data-batch]").forEach((tr) => tr.addEventListener("click", () => {
    const row = batchRows[Number(tr.dataset.batch)];
    if (!row.report) return;
    pinnedIds = []; currentFile = row.file; fitView = null;
    renderReport(row.report);
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

$("batch-csv").addEventListener("click", () => {
  const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [["file", "decision", "phases", "space_groups", "references", "error"].join(",")];
  batchRows.forEach((row) => {
    const phases = batchPhases(row.report);
    lines.push([row.file.name, row.report ? row.report.decision : "", phases.map((c) => c.formula).join("; "), phases.map((c) => c.space_group).join("; "), phases.map((c) => c.reference_id).join("; "), row.error || ""].map(cell).join(","));
  });
  saveFile("phasentic-batch.csv", lines.join("\r\n") + "\r\n", "text/csv");
});

$("cancel-button").addEventListener("click", () => {
  if (activeAnalysisController) activeAnalysisController.abort();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const files = Array.from($("file").files);
  if (!files.length) return;
  if (files.length > 1) void analyzeBatch(files);
  else { $("batch").hidden = true; batchRows = []; void analyzeSingle(files[0]); }
});

// Recent analyses, stored by the local server; opening one shows its report without the scan.
async function loadHistory() {
  const L = currentLanguage();
  try {
    const entries = (await fetchJsonOrThrow(await fetch("/api/v1/history"), "History unavailable")).data || [];
    if (!entries.length) { setHTML($("history-list"), `<p class="note">${esc(L.historyEmpty)}</p>`); return; }
    setHTML($("history-list"), `<ul class="history">${entries.map((e) => `<li><button type="button" class="history-item" data-history="${esc(e.analysis_id)}"><b>${esc(e.file_name || e.analysis_id)}</b><span class="f">${(e.phases || []).map((f) => R().formula(f)).join(" + ") || "—"}</span><small>${e.saved_at ? esc(new Date(e.saved_at * 1000).toLocaleString()) : ""} · ${esc((L.decisions && L.decisions[e.decision]) || e.decision || "")}${e.pinned ? ` · ${esc(L.historyPinned)}` : ""}</small></button></li>`).join("")}</ul>`);
    $("history-list").querySelectorAll("[data-history]").forEach((button) => button.addEventListener("click", async () => {
      try {
        const report = (await fetchJsonOrThrow(await fetch(`/api/v1/history/${encodeURIComponent(button.dataset.history)}`), "Could not open the analysis")).data;
        pinnedIds = []; currentFile = null; fitView = null;
        renderReport(report);
        $("form-status").textContent = "";
      } catch (error) { $("form-status").textContent = error.message; }
    }));
  } catch (_error) {
    setHTML($("history-list"), `<p class="note">${esc(L.historyEmpty)}</p>`);
  }
}
void loadHistory();

async function loadCapabilities() {
  try {
    const response = await fetch("/api/v1/capabilities");
    const payload = await fetchJsonOrThrow(response, "Engine capability status unavailable");
    const mixture = payload?.data?.mixture_screening;
    $("capability-status").textContent = mixture && mixture.available
      ? `Engine: ${mixture.algorithm_version}`
      : "Mixture screening is unavailable; single-phase screening remains active.";
  } catch (_error) {
    $("capability-status").textContent = "Engine capability status unavailable; deterministic screening remains active.";
  }
}

setLanguage("en");

fetch("/api/v1/reference-sources")
  .then((response) => fetchJsonOrThrow(response, "Reference-source status unavailable"))
  .then((payload) => {
    const data = payload.data && typeof payload.data === "object" && !Array.isArray(payload.data) ? payload.data : {};
    const selector = $("reference-source");
    const powCod = selector.querySelector('option[value="pow_cod"]');
    const sources = data.sources && typeof data.sources === "object" && !Array.isArray(data.sources) ? data.sources : {};
    const powCodInfo = sources.pow_cod && typeof sources.pow_cod === "object" ? sources.pow_cod : {};
    if (powCod) {
      powCod.disabled = powCodInfo.available !== true;
      powCod.textContent = powCodInfo.available === true ? databaseLabel(powCodInfo.release) : "Reference database (not installed)";
    }
    if (data.selected === "pow_cod" && powCodInfo.available === true) selector.value = "pow_cod";
    $("reference-status").textContent = powCodInfo.available === true
      ? databaseLabel(powCodInfo.release)
      : "No reference database installed; run the install command again (see README).";
  })
  .catch(() => { $("reference-status").textContent = "Reference-source status unavailable; demo subset remains active."; });

void loadCapabilities();
