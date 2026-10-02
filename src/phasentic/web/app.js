const translations = {
  en: { chemistry: "Sample chemistry (precursor and target formulas)", validatedPreset: "Use the validated method (POW_COD, Cu Kα, needs chemistry)", lede: "Powder X-ray diffraction phase identification with a validated, reproducible method.", noticeTitle: "Evidence boundary", noticeText: "Results are ranked hypotheses, not certainties. On held-out data the validated method identifies the exact phases 37% of the time and the right compounds (any polymorph) 49.5%. Confirm calibration and refine before publication.", settings: "Measurement settings", file: "Pattern file", radiation: "Anode / radiation", reference: "Reference source", angle: "Angle coordinate", tolerance: "Peak tolerance (° 2θ)", analysisMode: "Analysis mode", maxPhases: "Maximum phases", instrument: "Instrument metadata", vendor: "Vendor (optional)", model: "Model (optional)", radius: "Goniometer radius (mm, optional)", calibration: "Line-position calibration", standardFile: "Standard scan", standard: "Calibration standard", calibrate: "Calibrate standard", calibrationHint: "No calibration result attached.", instrumentPair: "Provide both instrument vendor and model, or leave both blank.", analyze: "Analyze pattern", pattern: "Measured trace and detected peaks", plotHint: "Upload a pattern to inspect its measured trace and detected peaks.", candidates: "Ranked phase hypotheses", empty: "No analysis yet.", mixtureHint: "Mixture diagnostics will appear when mixture mode is selected.", mixtureSelected: "Selected phase set", mixtureAlternative: "Retained alternative", mixtureHypothesis: "Mixture hypothesis", mixtureQuery: "Residual-query provenance", mixtureQueryCandidatePool: "Candidate pool", mixtureQueryRequeries: "Residual candidate re-queries", mixtureQueryMaxFitAttempts: "Max fit attempts", mixtureQueryRetainedBranches: "Retained branches", mixtureQueryFitAttempts: "Fit attempts", mixtureQueryTolerance: "Peak tolerance", mixtureQueryBackground: "Background model", mixtureQueryStop: "Stopping reason", mixtureScaleWarning: "Screening scales are arbitrary profile amplitudes, not phase fractions.", mixtureUnexplained: "Detected peaks remain unexplained", mixtureMissingLines: "Missing expected lines", diagnostics: "Quality and provenance", analysisProvenance: "Analysis provenance", referenceQuery: "Reference query", settingsProvenance: "Analysis settings", inputSha: "Input SHA-256", referenceSource: "Reference source", algorithmVersion: "Algorithm", diagnosticHint: "The report will show scan quality, warnings, and the reference source here.", download: "Download JSON report", score: "Screening score", stale: "Previous results cleared because a measurement setting changed.", measuredTrace: "Measured", mixtureTotal: "Mixture total", detectedPeaks: "Detected peaks" },
  es: { chemistry: "Química de la muestra (fórmulas de precursores y objetivo)", validatedPreset: "Usar el método validado (POW_COD, Cu Kα, requiere la química)", lede: "Identificación de fases por difracción de rayos X de polvo con un método validado y reproducible.", noticeTitle: "Límite de evidencia", noticeText: "Los resultados son hipótesis ordenadas, no certezas. En datos reservados, el método validado identifica las fases exactas el 37% de las veces y los compuestos correctos (cualquier polimorfo) el 49,5%. Confirme la calibración y refine antes de publicar.", settings: "Configuración de medición", file: "Archivo de patrón", radiation: "Ánodo / radiación", reference: "Fuente de referencias", angle: "Coordenada angular", tolerance: "Tolerancia de pico (° 2θ)", analysisMode: "Modo de análisis", maxPhases: "Máximo de fases", instrument: "Metadatos del instrumento", vendor: "Fabricante (opcional)", model: "Modelo (opcional)", radius: "Radio del goniómetro (mm, opcional)", calibration: "Calibración de posición de líneas", standardFile: "Escaneo estándar", standard: "Estándar de calibración", calibrate: "Calibrar estándar", calibrationHint: "No hay resultado de calibración adjunto.", instrumentPair: "Indique fabricante y modelo, o deje ambos vacíos.", analyze: "Analizar patrón", pattern: "Traza medida y picos detectados", plotHint: "Cargue un patrón para inspeccionar la traza medida y los picos detectados.", candidates: "Hipótesis de fases", empty: "Todavía no hay análisis.", mixtureHint: "Los diagnósticos de mezcla aparecen al seleccionar el modo de mezcla.", mixtureSelected: "Conjunto de fases seleccionado", mixtureAlternative: "Alternativa retenida", mixtureHypothesis: "Hipótesis de mezcla", mixtureQuery: "Procedencia de consultas residuales", mixtureQueryCandidatePool: "Conjunto de candidatos", mixtureQueryRequeries: "Nuevas consultas de candidatos por residual", mixtureQueryMaxFitAttempts: "Máximo de intentos de ajuste", mixtureQueryRetainedBranches: "Ramas retenidas", mixtureQueryFitAttempts: "Intentos de ajuste", mixtureQueryTolerance: "Tolerancia de pico", mixtureQueryBackground: "Modelo de fondo", mixtureQueryStop: "Razón de parada", mixtureScaleWarning: "Las escalas de cribado son amplitudes arbitrarias del perfil, no fracciones de fase.", mixtureUnexplained: "Picos detectados sin explicar", mixtureMissingLines: "Líneas esperadas ausentes", diagnostics: "Calidad y procedencia", analysisProvenance: "Procedencia del análisis", referenceQuery: "Consulta de referencias", settingsProvenance: "Configuración del análisis", inputSha: "SHA-256 de entrada", referenceSource: "Fuente de referencias", algorithmVersion: "Algoritmo", diagnosticHint: "El informe mostrará la calidad del escaneo, advertencias y la fuente de referencias aquí.", download: "Descargar informe JSON", score: "Puntuación de cribado", stale: "Se borraron los resultados anteriores porque cambió una configuración de medición.", measuredTrace: "Medida", mixtureTotal: "Total de mezcla", detectedPeaks: "Picos detectados" }
};


const $ = (id) => document.getElementById(id);
// Okabe-Ito palette (colour-blind safe) for per-phase traces.
const COMPONENT_COLORS = ["#e69f00", "#009e73", "#f0e442", "#d55e00", "#0072b2"];
const form = $("analysis-form");
let calibrationResult = null;
let calibrationRequest = 0;
let latestReport = null;
let analysisRequest = 0;
let activeAnalysisController = null;

function setLanguage(language) {
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    if (element.id === "calibration-status" && calibrationResult) return;
    element.textContent = translations[language][element.dataset.i18n];
  });
}

function setCalibrationStatus(message) {
  const element = $("calibration-status");
  element.removeAttribute("data-i18n");
  element.textContent = message;
}


function currentLanguage() {
  return translations[$("language").value] || translations.en;
}


function finiteValues(values) {
  return Array.isArray(values) ? values.filter((value) => Number.isFinite(Number(value))).map(Number) : [];
}

function traceValues(trace, ...names) {
  for (const name of names) {
    if (trace && Array.isArray(trace[name])) return trace[name].map(Number);
  }
  return [];
}

function drawSeries(context, angles, values, options, bounds) {
  if (!angles.length || !values.length) return;
  const { min, max, left, right, top, bottom, yMin, yMax } = bounds;
  const range = Math.max(max - min, 1e-9);
  const yRange = Math.max(yMax - yMin, 1e-9);
  context.strokeStyle = options.color;
  context.lineWidth = options.width || 1;
  context.setLineDash(options.dash || []);
  context.beginPath();
  let started = false;
  angles.forEach((angle, index) => {
    const value = Number(values[index]);
    if (!Number.isFinite(Number(angle)) || !Number.isFinite(value)) return;
    const x = left + ((Number(angle) - min) / range) * (right - left);
    const y = bottom - ((value - yMin) / yRange) * (bottom - top);
    if (!started) { context.moveTo(x, y); started = true; } else context.lineTo(x, y);
  });
  if (started) context.stroke();
  context.setLineDash([]);
}

function renderTraceLegend(id, items) {
  const legend = $(id);
  if (!legend) return;
  legend.replaceChildren();
  (Array.isArray(items) ? items : []).filter((item) => item && typeof item.label === "string" && item.label.trim()).forEach((item) => {
    const key = document.createElement("span"); key.className = "trace-key";
    const swatch = document.createElement("span"); swatch.className = `trace-swatch${item.dashed ? " dashed" : ""}`; swatch.style.color = item.color || "#9db0b4"; swatch.style.backgroundColor = item.dashed ? "transparent" : (item.color || "#9db0b4");
    const label = document.createElement("span"); label.textContent = item.label;
    key.append(swatch, label); legend.appendChild(key);
  });
}

function mixtureComponentLabel(report, referenceId) {
  const hypotheses = report?.mixture?.hypotheses;
  if (Array.isArray(hypotheses)) {
    for (const hypothesis of hypotheses) {
      const component = Array.isArray(hypothesis?.components)
        ? hypothesis.components.find((candidate) => candidate?.reference_id === referenceId)
        : null;
      if (component) return component.name ? `${component.name} · ${referenceId}` : String(referenceId || "component");
    }
  }
  return String(referenceId || "component");
}

function drawPlot(report) {
  const canvas = $("plot");
  const context = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#0e141a";
  context.fillRect(0, 0, width, height);
  const language = currentLanguage();
  const legendItems = [];
  renderTraceLegend("plot-legend", legendItems);
  const min = Number(report.input.angle_min_deg);
  const max = Number(report.input.angle_max_deg);
  const trace = report.provenance && report.provenance.measurement_trace ? report.provenance.measurement_trace : {};
  const traceAngles = traceValues(trace, "raw_angles_deg", "angles_deg");
  const traceIntensities = traceValues(trace, "raw_intensities", "observed_intensities", "intensities");
  const mixtureTrace = report.mixture && report.mixture.residual_trace;
  const mixtureCalculated = mixtureTrace ? traceValues(mixtureTrace, "calculated_intensities", "calculated") : [];
  const values = [...traceIntensities, ...finiteValues((report.peaks || []).map((peak) => peak.intensity)), ...mixtureCalculated];
  const maxIntensity = Math.max(...values, 1);
  const left = 48; const right = width - 18; const top = 18; const bottom = height - 34;
  const bounds = { min, max, left, right, top, bottom, yMin: 0, yMax: maxIntensity * 1.05 };
  context.strokeStyle = "#2a3a45"; context.lineWidth = 1;
  context.beginPath(); context.moveTo(left, top); context.lineTo(left, bottom); context.lineTo(right, bottom); context.stroke();
  drawSeries(context, traceAngles, traceIntensities, { color: "#56b4e9", width: 2 }, bounds);
  if (traceAngles.length && traceIntensities.length) legendItems.push({ label: language.measuredTrace, color: "#56b4e9" });
  if (mixtureTrace && mixtureCalculated.length) {
    const angles = traceValues(mixtureTrace, "angles_deg", "angles");
    drawSeries(context, angles, mixtureCalculated, { color: "#cc79a7" }, bounds);
    legendItems.push({ label: language.mixtureTotal, color: "#cc79a7" });
    (mixtureTrace.component_traces || []).forEach((component, componentIndex) => {
      drawSeries(context, angles, traceValues(component, "calculated_intensities", "intensities"), { color: COMPONENT_COLORS[componentIndex % COMPONENT_COLORS.length] }, bounds);
      legendItems.push({ label: mixtureComponentLabel(report, component?.reference_id), color: COMPONENT_COLORS[componentIndex % COMPONENT_COLORS.length] });
    });
  }
  context.strokeStyle = "#b8c4c8"; context.lineWidth = 1;
  (report.peaks || []).forEach((peak) => {
    const x = left + ((Number(peak.position_deg) - min) / Math.max(max - min, 1e-9)) * (right - left);
    const y = bottom - (Number(peak.intensity) / Math.max(maxIntensity, 1e-9)) * (bottom - top);
    context.beginPath(); context.moveTo(x, bottom); context.lineTo(x, y); context.stroke();
  });
  if ((report.peaks || []).length) legendItems.push({ label: language.detectedPeaks, color: "#b8c4c8" });
  context.fillStyle = "#9db0b4"; context.font = "12px system-ui";
  context.fillText(`${min.toFixed(1)}°`, left, height - 10); context.fillText(`${max.toFixed(1)}°`, right - 40, height - 10);
  const mixtureCaption = mixtureTrace && mixtureCalculated.length ? ` · ${language.mixtureTotal}` : "";
  $("plot-caption").textContent = `${report.input.point_count} measured points · ${(report.peaks || []).length} detected peaks · ${report.radiation.label}${mixtureCaption}`;
  renderTraceLegend("plot-legend", legendItems);
}

function appendMetric(grid, label, value) {
  const metric = document.createElement("div"); metric.className = "metric";
  const span = document.createElement("span"); span.textContent = label;
  const strong = document.createElement("strong"); strong.textContent = value == null ? "—" : String(value);
  metric.append(span, strong); grid.appendChild(metric);
}

function appendKeyValueList(parent, entries, className = "provenance-list") {
  const list = document.createElement("dl"); list.className = className;
  entries.forEach(([label, value]) => {
    if (value == null || value === "") return;
    const term = document.createElement("dt"); term.textContent = label;
    const description = document.createElement("dd");
    const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    if (text.length > 160) {
      // Long provenance blocks stay one click away instead of filling the page.
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

function renderMixtureSummary(parent, report) {
  const language = currentLanguage();
  const mixture = report && report.mixture && typeof report.mixture === "object" ? report.mixture : null;
  parent.replaceChildren();
  const hypotheses = mixture && Array.isArray(mixture.hypotheses) ? mixture.hypotheses.filter((hypothesis) => hypothesis && typeof hypothesis === "object") : [];
  if (!mixture || !hypotheses.length) {
    const hint = document.createElement("p"); hint.className = "muted"; hint.textContent = language.mixtureHint; parent.appendChild(hint); return;
  }
  const query = mixture.query && typeof mixture.query === "object" ? mixture.query : {};
  const querySection = document.createElement("section"); querySection.id = "mixture-query"; querySection.className = "mixture-query";
  const queryHeading = document.createElement("h3"); queryHeading.className = "provenance-heading"; queryHeading.textContent = language.mixtureQuery; querySection.appendChild(queryHeading);
  appendKeyValueList(querySection, [
    [language.algorithmVersion || "Algorithm", mixture.algorithm_version],
    [language.mixtureQueryCandidatePool, query.candidate_pool_size == null ? query.candidate_pool : `${query.candidate_pool_size} / ${query.candidate_pool_limit == null ? "—" : query.candidate_pool_limit}`],
    [language.mixtureQueryRequeries, query.residual_candidate_requeries],
    [language.mixtureQueryMaxFitAttempts, query.max_fit_attempts],
    [language.mixtureQueryRetainedBranches, query.retained_branches],
    [language.mixtureQueryFitAttempts, query.fit_attempts],
    [language.mixtureQueryTolerance, query.tolerance_deg == null ? null : `${query.tolerance_deg}°`],
    [language.mixtureQueryBackground, query.background_model],
    [language.mixtureQueryStop, query.stopping_reason],
  ]);
  parent.appendChild(querySection);
  const selectedId = typeof mixture.selected_hypothesis_id === "string" ? mixture.selected_hypothesis_id : null;
  hypotheses.forEach((hypothesis, index) => {
    const hypothesisId = typeof hypothesis.hypothesis_id === "string" && hypothesis.hypothesis_id ? hypothesis.hypothesis_id : `hypothesis-${index + 1}`;
    const selected = selectedId != null && hypothesisId === selectedId;
    const card = document.createElement("article"); card.className = "candidate"; card.dataset.hypothesisId = hypothesisId;
    const heading = document.createElement("h3"); heading.textContent = `${selected ? language.mixtureSelected : language.mixtureAlternative} · ${hypothesisId}`;
    const status = hypothesis.status == null ? "—" : String(hypothesis.status);
    const objective = Number(hypothesis.objective);
    const improvement = Number(hypothesis.objective_improvement);
    const summary = document.createElement("p"); summary.className = "muted";
    summary.textContent = `${language.mixtureHypothesis}: ${status} · normalized residual ${Number.isFinite(objective) ? `${(objective * 100).toFixed(2)}%` : "—"} · objective improvement ${Number.isFinite(improvement) ? `${(improvement * 100).toFixed(2)}%` : "—"} · ${language.mixtureQueryFitAttempts}: ${hypothesis.fit_attempts == null ? "—" : hypothesis.fit_attempts} · ${hypothesis.stopping_reason || "—"}`;
    const components = document.createElement("ul"); components.className = "evidence";
    const componentList = Array.isArray(hypothesis.components) ? hypothesis.components : [];
    componentList.forEach((component) => {
      const item = document.createElement("li");
      const scale = Number(component && component.screening_scale);
      const evidenceCount = Array.isArray(component && component.evidence_groups) ? component.evidence_groups.length : 0;
      const missingCount = Array.isArray(component && component.missing_expected_lines) ? component.missing_expected_lines.length : 0;
      const name = component && (component.name || component.reference_id) ? (component.name || component.reference_id) : "component";
      const formula = component && component.formula ? ` (${component.formula})` : "";
      item.textContent = `${name}${formula} · screening scale ${Number.isFinite(scale) ? scale.toFixed(3) : "—"} · ${evidenceCount} evidence lines${missingCount ? ` · ${missingCount} missing expected lines` : ""}`;
      components.appendChild(item);
    });
    const unexplained = Array.isArray(hypothesis.unexplained_peak_positions) ? hypothesis.unexplained_peak_positions : [];
    const unexplainedText = document.createElement("p"); unexplainedText.className = "muted";
    unexplainedText.textContent = `${unexplained.length} ${language.mixtureUnexplained}${unexplained.length ? ` (${unexplained.map((value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(4)}°` : String(value)).join(", ")})` : ""}.`;
    const missing = Array.isArray(hypothesis.missing_expected_lines) ? hypothesis.missing_expected_lines : [];
    const missingText = document.createElement("p"); missingText.className = "muted";
    missingText.textContent = `${language.mixtureMissingLines}: ${missing.length ? missing.join(", ") : "—"}.`;
    const scaleWarning = document.createElement("p"); scaleWarning.className = "muted"; scaleWarning.textContent = language.mixtureScaleWarning;
    card.append(heading, summary, components, unexplainedText, missingText, scaleWarning); parent.appendChild(card);
  });
}

function renderAnalysisProvenance(parent, report) {
  if (!parent || !report || typeof report !== "object") return;
  const language = currentLanguage();
  const provenance = report.provenance && typeof report.provenance === "object" ? report.provenance : {};
  const input = report.input && typeof report.input === "object" ? report.input : {};
  const heading = document.createElement("h3"); heading.className = "provenance-heading"; heading.textContent = language.analysisProvenance || "Analysis provenance"; parent.appendChild(heading);
  appendKeyValueList(parent, [
    [language.fileName || "File name", input.file_name],
    [language.inputSha || "Input SHA-256", input.sha256],
    [language.referenceSource || "Reference source", provenance.reference_source],
    ["POW_COD release", provenance.powcod_release],
    ["POW_COD database SHA-256", provenance.powcod_database_sha256],
    ["POW_COD cache SHA-256", provenance.powcod_cache_sha256],
    ["POW_COD intensity policy", provenance.reference_query?.intensity_policy],
    [language.algorithmVersion || "Algorithm", provenance.algorithm_version],
    [language.coordinateCorrection || "Coordinate correction", provenance.coordinate_correction],
    [language.referenceEntries || "Reference entries", provenance.cod_entry_ids || provenance.cod_entries],
    [language.sourceUrls || "Reference source URLs", provenance.cod_source_urls],
    [language.referenceQuery || "Reference query", provenance.reference_query],
    [language.settingsProvenance || "Analysis settings", provenance.settings],
  ]);
}

function renderReport(report) {
  latestReport = report;
  $("decision").textContent = report.decision;
  $("analysis-id").textContent = `run ${report.analysis_id}`;
  drawPlot(report);
  const list = $("candidate-list"); list.replaceChildren();
  if (!report.candidates.length) { const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = translations[$("language").value].empty; list.appendChild(empty); }
  report.candidates.forEach((candidate) => {
    const card = document.createElement("article"); card.className = "candidate";
    const title = document.createElement("div"); const heading = document.createElement("h3"); heading.textContent = candidate.name; const meta = document.createElement("small"); meta.textContent = `${candidate.formula} · ${candidate.reference_id}`; title.append(heading, meta);
    const score = document.createElement("div"); score.className = "score"; score.textContent = `${translations[$("language").value].score} ${(candidate.score * 100).toFixed(1)}% · ${candidate.status}`;
    const evidence = document.createElement("div"); evidence.className = "evidence"; evidence.textContent = `${candidate.matched_peaks}/${candidate.expected_peaks} lines matched · ${candidate.position_rmse_deg == null ? "RMSE unavailable" : `${candidate.position_rmse_deg.toFixed(3)}° RMSE`} · ${candidate.evidence.join("; ")}`;
    card.append(title, score, evidence); list.appendChild(card);
  });
  const mixtureContent = $("mixture-content"); renderMixtureSummary(mixtureContent, report);
  const diagnostics = $("diagnostic-content"); diagnostics.replaceChildren();
  const grid = document.createElement("div"); grid.className = "diagnostic-grid";
  const signal = Number(report.quality && report.quality.signal_to_noise);
  const baseline = Number(report.quality && report.quality.baseline_fraction);
  [["Points", report.input.point_count], ["S/N", Number.isFinite(signal) ? signal.toFixed(2) : "—"], ["Baseline", Number.isFinite(baseline) ? `${(baseline * 100).toFixed(1)}%` : "—"], ["Calibration", report.quality.calibration_status], ["Reference", report.provenance.reference_source]].forEach(([label, value]) => appendMetric(grid, label, value));
  diagnostics.appendChild(grid);
  if (report.quality.warnings.length) { const warnings = document.createElement("ul"); warnings.className = "warnings"; report.quality.warnings.forEach((warning) => { const item = document.createElement("li"); item.textContent = warning; warnings.appendChild(item); }); diagnostics.appendChild(warnings); }
  const analysisProvenance = document.createElement("div"); analysisProvenance.id = "analysis-provenance"; analysisProvenance.className = "analysis-provenance"; renderAnalysisProvenance(analysisProvenance, report); diagnostics.appendChild(analysisProvenance);
}

function clearRenderedReport() {
  latestReport = null;
  $("decision").textContent = "—";
  $("analysis-id").textContent = "";
  const list = $("candidate-list"); list.replaceChildren();
  const empty = document.createElement("p"); empty.className = "muted"; empty.textContent = translations[$("language").value].empty; list.appendChild(empty);
  const mixture = $("mixture-content"); mixture.replaceChildren();
  const mixtureHint = document.createElement("p"); mixtureHint.className = "muted"; mixtureHint.textContent = translations[$("language").value].mixtureHint; mixture.appendChild(mixtureHint);
  const diagnostics = $("diagnostic-content"); diagnostics.replaceChildren();
  const diagnosticHint = document.createElement("p"); diagnosticHint.className = "muted"; diagnosticHint.textContent = translations[$("language").value].diagnosticHint; diagnostics.appendChild(diagnosticHint);
  const canvas = $("plot"); const context = canvas.getContext("2d"); context.clearRect(0, 0, canvas.width, canvas.height); context.fillStyle = "#0e141a"; context.fillRect(0, 0, canvas.width, canvas.height);
  renderTraceLegend("plot-legend", []);
}

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
  $("footer-source").textContent = `Open local service · reference source: ${$("reference-source").value} · no phase fractions`;
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
  $("form-status").textContent = "Running deterministic screening…";
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
    renderReport(payload.data); $("form-status").textContent = "Analysis complete. Review the evidence boundary before reporting.";
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
    $("footer-source").textContent = `Open local service · reference source: ${selector.value} · no phase fractions`;
    $("reference-status").textContent = powCodInfo.available === true
      ? `POW_COD ${powCodInfo.release || "ready"}`
      : "POW_COD is disabled until a verified local database is configured (see README).";
  })
  .catch(() => { $("reference-status").textContent = "Reference-source status unavailable; demo subset remains active."; });

void loadCapabilities();
