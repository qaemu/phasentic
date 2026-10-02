const translations = {
  en: {
    lede: "Powder X-ray diffraction phase identification",
    sample: "Sample", file: "Pattern file", fileHint: ".xy, .xrdml or ASCII .raw, up to 10 MB",
    chemistry: "Precursor and target formulas", chemistryHint: "Candidates are limited to these elements plus H, C and O.",
    method: "Method", validatedPreset: "Validated method", validatedHint: "The settings tested on 200 sealed scans. Needs POW_COD, Cu Kα and the formulas above.",
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
    stale: "A setting changed, so the previous result was cleared.",
    footer: "Runs on this computer; scans are not uploaded anywhere.", footerAi: "Open source (MIT). No AI model is used to analyse scans.",
  },
  es: {
    lede: "Identificación de fases por difracción de rayos X de polvo",
    sample: "Muestra", file: "Archivo del patrón", fileHint: ".xy, .xrdml o .raw ASCII, hasta 10 MB",
    chemistry: "Fórmulas de precursores y objetivo", chemistryHint: "Los candidatos se limitan a estos elementos más H, C y O.",
    method: "Método", validatedPreset: "Método validado", validatedHint: "La configuración probada en 200 escaneos sellados. Requiere POW_COD, Cu Kα y las fórmulas de arriba.",
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
    [L.factReference, p.reference_source === "pow_cod" ? `POW_COD ${p.powcod_release || ""}` : "demo"],
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
  setHTML($("plot"), R().figures.fit(report));
  const evidence = sel ? R().figures.phases(report) : "";
  setHTML($("phase-evidence"), evidence);
  $("evidence-fold").hidden = !evidence;
  renderMixtureSummary($("mixture-content"), report);
  renderCandidates($("candidate-list"), report);
  renderDiagnostics($("diagnostic-content"), report);
}

function clearRenderedReport() {
  latestReport = null;
  $("result").hidden = true; $("empty-state").hidden = false;
  ["plot", "phase-evidence", "phase-summary", "mixture-content", "candidate-list", "diagnostic-content"].forEach((id) => { $(id).replaceChildren(); });
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
  analysisRequest += 1;
  if (activeAnalysisController) activeAnalysisController.abort();
  activeAnalysisController = null;
  clearRenderedReport();
  $("form-status").textContent = message;
}

function invalidateCalibration(message) {
  calibrationRequest += 1;
  calibrationResult = null;
  setCalibrationStatus(message);
}

let appVersion = "";
fetch("/api/v1/health").then((r) => r.json()).then((d) => { appVersion = d.version || ""; }).catch(() => {});
$("download-pdf-report").addEventListener("click", () => {
  if (!latestReport || !window.PhasenticReport) return;
  const html = window.PhasenticReport.build(latestReport, { version: appVersion, preset: $("validated-preset").checked ? "validated" : null });
  const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
  const link = document.createElement("a"); link.href = url; link.download = `phasentic-report-${latestReport.analysis_id || "analysis"}.html`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("download-report").addEventListener("click", () => {
  if (!latestReport) return;
  const blob = new Blob([JSON.stringify(latestReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = `${latestReport.analysis_id || "xrd-report"}.json`; link.click();
  URL.revokeObjectURL(url);
});


$("language").addEventListener("change", (event) => {
  setLanguage(event.target.value);
  if (latestReport) renderReport(latestReport);
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
    $("form-status").textContent = "POW_COD is unavailable until it is configured.";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("file").files[0];
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) { $("form-status").textContent = "File exceeds the 10 MiB limit."; return; }
  if (activeAnalysisController) activeAnalysisController.abort();
  const requestId = ++analysisRequest;
  const controller = new AbortController();
  activeAnalysisController = controller;
  $("form-status").textContent = currentLanguage().running;
  const data = new FormData();
  data.append("file", file);
  const instrument = {};
  const vendor = $("instrument-vendor").value.trim();
  const model = $("instrument-model").value.trim();
  if ((vendor && !model) || (!vendor && model)) {
    $("form-status").textContent = translations[$("language").value].instrumentPair;
    activeAnalysisController = null;
    return;
  }
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
  const settings = $("validated-preset").checked
    ? { ...common, preset: "validated" }
    : { ...common, peak_tolerance_deg: Number($("tolerance").value), analysis_mode: $("analysis-mode").value, max_phases: Number($("max-phases").value) };
  data.append("settings_json", JSON.stringify(settings));
  data.append("calibration_json", JSON.stringify(calibrationResult || {}));
  try {
    const response = await fetch("/api/v1/analyze", { method: "POST", body: data, signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Analysis failed");
    if (requestId !== analysisRequest) return;
    renderReport(payload.data); $("form-status").textContent = currentLanguage().done;
  } catch (error) {
    if (requestId !== analysisRequest || error && error.name === "AbortError") return;
    $("form-status").textContent = error instanceof Error ? error.message : "Analysis failed.";
  } finally {
    if (requestId === analysisRequest) activeAnalysisController = null;
  }
});

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
      powCod.textContent = powCodInfo.available === true
        ? `POW_COD ${typeof powCodInfo.release === "string" ? powCodInfo.release : "ready"}`
        : "POW_COD (not configured)";
    }
    if (data.selected === "pow_cod" && powCodInfo.available === true) selector.value = "pow_cod";
    $("reference-status").textContent = powCodInfo.available === true
      ? `POW_COD ${powCodInfo.release || "ready"}`
      : "POW_COD is disabled until a verified local database is configured (see README).";
  })
  .catch(() => { $("reference-status").textContent = "Reference-source status unavailable; demo subset remains active."; });

void loadCapabilities();
