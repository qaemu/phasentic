// Printable analysis report: turns the JSON analysis report into one
// self-contained HTML page (A4, print to PDF from the browser).
// Structure follows ISO/IEC 17025:2017 §7.8 (identification, method, results,
// interpretation kept separate, limitations, authorisation) and records the
// measurement details EN 13925 asks for. Reads only the report; no analysis.
(function (root) {
  "use strict";

  const PHASE_COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00"]; // validated, light surface
  const INK = "#1d2430", MUTED = "#5d6673", RULE = "#d6d9de", OBS = "#9aa1ab", MODEL = "#1d2430";

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 2) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "—");

  // "H3 Li O2" -> LiH₃O₂ (cations first, then C, N, H, O, halogens); digits as subscripts.
  function formula(text) {
    const raw = String(text || "").trim();
    if (!raw) return "—";
    let ordered = raw;
    if (!raw.includes("(")) {
      const tail = ["C", "N", "H", "O", "F", "Cl", "Br", "I", "S"];
      const parts = raw.split(/\s+/).map((t) => { const m = t.match(/^([A-Z][a-z]?)(.*)$/); return m ? [m[1], m[2]] : [t, ""]; });
      parts.sort((a, b) => (tail.indexOf(a[0]) - tail.indexOf(b[0])) || 0);
      ordered = parts.map(([e, n]) => e + n).join("");
    } else {
      ordered = raw.replace(/\s+(\d*\.?\d+\()/g, "·$1").replace(/\s+/g, "");
    }
    return esc(ordered).replace(/([A-Za-z)\]])(\d+(?:\.\d+)?)/g, "$1<sub>$2</sub>");
  }

  // "P 1 21/c 1" -> P2₁/c ; "F m -3 m" -> Fm3̄m
  function spaceGroup(text) {
    let t = String(text || "").trim().split(/\s+/);
    if (!t[0]) return "—";
    if (t.length === 4 && t[1] === "1" && t[3] === "1") t = [t[0], t[2]];
    return t.map((s) => esc(s).replace(/-(\d)/g, "$1&#773;").replace(/^(\d)(\d)/, "$1<sub>$2</sub>")).join("");
  }

  // HTML subscripts -> Unicode, for SVG text.
  const plain = (html) => String(html).replace(/<sub>(.*?)<\/sub>/g, (_, d) => d.replace(/\d/g, (n) => "₀₁₂₃₄₅₆₇₈₉"[n])).replace(/<[^>]+>/g, "");

  function codLink(referenceId) {
    const id = String(referenceId || "").replace(/^powcod:/, "");
    return /^\d+$/.test(id) ? `<a href="https://www.crystallography.net/cod/${id}.html">COD ${id}</a>` : esc(referenceId);
  }

  function ticks(min, max, step) { const out = []; for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v); return out; }
  function niceStep(span, target) { const raw = span / target, mag = 10 ** Math.floor(Math.log10(raw)); return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw; }
  function path(xs, ys, sx, sy) { let d = ""; for (let i = 0; i < xs.length; i++) { if (!Number.isFinite(ys[i])) continue; d += (d ? "L" : "M") + sx(xs[i]).toFixed(1) + "," + sy(ys[i]).toFixed(1); } return d; }
  const fmtCount = (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(v % 1000 === 0 ? 0 : 1) + "k" : String(Math.round(v)));

  let numbered = true;
  const num1 = (n) => (numbered ? `<b>Figure ${n}.</b> ` : "");

  function phasesOf(report) {
    const sel = selectedHypothesis(report);
    return (sel ? sel.components : []).map((c, i) => ({ component: c, color: PHASE_COLORS[i % PHASE_COLORS.length] }));
  }

  // Measured trace with detected-peak ticks, for analyses without a mixture fit.
  function measuredFigure(report) {
    const t = (report.provenance && report.provenance.measurement_trace) || {};
    const x = t.corrected_angles_deg || t.raw_angles_deg, y = t.corrected_intensities || t.raw_intensities;
    if (!x || !y || !x.length) return "";
    const W = 680, L = 52, R = 12, top = 8, mainH = 170, tickY = top + mainH + 12, H = tickY + 34;
    const xmin = x[0], xmax = x[x.length - 1], ymax = Math.max(...y) * 1.04;
    const sx = (v) => L + ((v - xmin) / (xmax - xmin)) * (W - L - R);
    const sy = (v) => top + mainH - (v / ymax) * mainH;
    let g = "";
    ticks(0, ymax, niceStep(ymax, 4)).forEach((v) => { g += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/><text x="${L - 6}" y="${sy(v) + 3}" class="tick" text-anchor="end">${fmtCount(v)}</text>`; });
    g += `<path d="${path(x, y, sx, sy)}" fill="none" stroke="${MODEL}" stroke-width="1"/>`;
    (report.peaks || []).forEach((pk) => { g += `<line x1="${sx(pk.position_deg)}" x2="${sx(pk.position_deg)}" y1="${tickY - 4}" y2="${tickY + 4}" stroke="${MUTED}" stroke-width="1.4"/>`; });
    g += `<line x1="${L}" x2="${W - R}" y1="${tickY + 9}" y2="${tickY + 9}" class="axis"/>`;
    ticks(xmin, xmax, 10).forEach((v) => { g += `<text x="${sx(v)}" y="${tickY + 21}" class="tick" text-anchor="middle">${v}</text>`; });
    g += `<text x="${(L + W - R) / 2}" y="${H - 1}" class="label" text-anchor="middle">2θ (°), ${esc(report.radiation?.label || "")}</text>`;
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Measured pattern and detected peaks">${g}</svg><figcaption>${num1(1)}Measured pattern. Ticks mark the ${(report.peaks || []).length} detected peaks; no mixture fit was selected.</figcaption></figure>`;
  }

  function selectedHypothesis(report) {
    const m = report.mixture || {};
    return (m.hypotheses || []).find((h) => h.hypothesis_id === m.selected_hypothesis_id) || null;
  }

  // Figure 1: observed vs model with difference curve and assigned-peak ticks per phase.
  function fitFigure(report, phases) {
    const t = report.mixture && report.mixture.residual_trace;
    if (!t || !t.angles_deg) return "";
    const x = t.angles_deg, obs = t.observed_intensities, bg = t.background_intensities;
    const model = t.calculated_intensities.map((v, i) => v + bg[i]);
    const res = t.residual_intensities;
    const W = 680, L = 52, R = 12, top = 8, mainH = 148, gap = 7, tickRow = 11, diffH = 38;
    const tickTop = top + mainH + gap, diffTop = tickTop + phases.length * tickRow + 8, H = diffTop + diffH + 30;
    const xmin = x[0], xmax = x[x.length - 1];
    const ymax = Math.max(...obs, ...model) * 1.04, ymin = Math.min(0, ...obs);
    const rmax = Math.max(...res.map(Math.abs)) || 1;
    const sx = (v) => L + ((v - xmin) / (xmax - xmin)) * (W - L - R);
    const sy = (v) => top + mainH - ((v - ymin) / (ymax - ymin)) * mainH;
    const sd = (v) => diffTop + diffH / 2 - (v / rmax) * (diffH / 2);
    const xt = ticks(xmin, xmax, 10), yt = ticks(0, ymax, niceStep(ymax, 4));
    let g = "";
    yt.forEach((v) => { g += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/><text x="${L - 6}" y="${sy(v) + 3}" class="tick" text-anchor="end">${fmtCount(v)}</text>`; });
    xt.forEach((v) => { g += `<line x1="${sx(v)}" x2="${sx(v)}" y1="${diffTop + diffH}" y2="${diffTop + diffH + 4}" class="axis"/><text x="${sx(v)}" y="${diffTop + diffH + 15}" class="tick" text-anchor="middle">${v}</text>`; });
    g += `<path d="${path(x, bg, sx, sy)}" class="bg"/>`;
    g += `<path d="${path(x, obs, sx, sy)}" fill="none" stroke="${OBS}" stroke-width="1.6"/>`;
    g += `<path d="${path(x, model, sx, sy)}" fill="none" stroke="${MODEL}" stroke-width="1"/>`;
    const peaks = report.peaks || [];
    phases.forEach((p, k) => {
      const y = tickTop + k * tickRow + tickRow / 2;
      (p.component.matched_peak_indices || []).forEach((idx) => { const pk = peaks[idx]; if (pk) g += `<line x1="${sx(pk.position_deg)}" x2="${sx(pk.position_deg)}" y1="${y - 4}" y2="${y + 4}" stroke="${p.color}" stroke-width="1.6"/>`; });
      g += `<text x="${L - 6}" y="${y + 3}" class="tick" text-anchor="end">${k + 1}</text>`;
    });
    (selectedHypothesis(report)?.unexplained_peak_positions || []).forEach((pos) => { g += `<path d="M${sx(pos)},${tickTop - 6} l-3,-5 h6z" fill="${INK}"/>`; });
    g += `<line x1="${L}" x2="${W - R}" y1="${sd(0)}" y2="${sd(0)}" class="grid"/>`;
    g += `<path d="${path(x, res, sx, sd)}" fill="none" stroke="${MUTED}" stroke-width="0.8"/>`;
    g += `<text x="${L - 6}" y="${diffTop + 8}" class="tick" text-anchor="end">Δ</text>`;
    g += `<line x1="${L}" x2="${W - R}" y1="${diffTop + diffH}" y2="${diffTop + diffH}" class="axis"/>`;
    g += `<text x="${(L + W - R) / 2}" y="${H - 2}" class="label" text-anchor="middle">2θ (°), ${esc(report.radiation?.label || "")}, corrected for sample displacement</text>`;
    g += `<text x="12" y="${top + mainH / 2}" class="label" text-anchor="middle" transform="rotate(-90 12 ${top + mainH / 2})">Intensity (counts)</text>`;
    const legend = `<div class="legend"><span><i style="background:${OBS};height:2px"></i>Measured</span><span><i style="background:${MODEL};height:1px"></i>Model (background + phases)</span><span><i class="dash"></i>Background</span>${phases.map((p, k) => `<span><i class="tickkey" style="background:${p.color}"></i>${k + 1} ${formula(p.component.formula)}</span>`).join("")}<span><i style="background:${MUTED};height:1px"></i>Δ measured − model</span></div>`;
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Measured pattern, fitted model and difference curve">${g}</svg>${legend}<figcaption>${num1(1)} Measured pattern and screening fit. Tick rows mark the detected peaks assigned to each phase; the lower panel is the difference between measurement and model.</figcaption></figure>`;
  }

  // Figure 2: one small panel per phase: background-subtracted signal vs that phase's contribution.
  function phaseFigure(report, phases) {
    const t = report.mixture && report.mixture.residual_trace;
    if (!t || !phases.length) return "";
    const x = t.angles_deg, target = t.fit_target_intensities;
    const W = 680, L = 52, R = 12, h = 42, gapY = 19;
    const H = phases.length * (h + gapY) + 18;
    const xmin = x[0], xmax = x[x.length - 1];
    const sx = (v) => L + ((v - xmin) / (xmax - xmin)) * (W - L - R);
    let g = "";
    phases.forEach((p, k) => {
      const y0 = k * (h + gapY) + 14;
      const comp = (t.component_traces || []).find((c) => c.reference_id === p.component.reference_id);
      const others = (t.component_traces || []).filter((c) => c !== comp);
      const partial = target.map((v, i) => others.reduce((acc, c) => acc - c.calculated_intensities[i], v));
      const ymax = Math.max(1, ...(comp ? comp.calculated_intensities : target)) * 1.25;
      const sy = (v) => y0 + h - (Math.min(ymax, Math.max(0, v)) / ymax) * h;
      g += `<text x="${L}" y="${y0 - 4}" class="panel">${k + 1}  ${plain(formula(p.component.formula))}  <tspan class="tick">${plain(spaceGroup(p.component.space_group))} · ${esc(String(p.component.reference_id).replace("powcod:", "COD "))}</tspan></text>`;
      g += `<text x="${L - 6}" y="${y0 + 8}" class="tick" text-anchor="end">×${fmtCount(ymax / 1.25)}</text>`;
      g += `<path d="${path(x, partial, sx, sy)}" fill="none" stroke="${OBS}" stroke-width="0.9"/>`;
      if (comp) {
        const ys = comp.calculated_intensities;
        const area = path(x, ys, sx, sy) + `L${sx(xmax)},${sy(0)}L${sx(xmin)},${sy(0)}Z`;
        g += `<path d="${area}" fill="${p.color}" fill-opacity="0.18" stroke="${p.color}" stroke-width="1"/>`;
      }
      g += `<line x1="${L}" x2="${W - R}" y1="${y0 + h}" y2="${y0 + h}" class="axis"/>`;
      const mi = (p.component.matched_peak_indices || []).length, ie = (p.component.independent_evidence_peak_indices || []).length;
      g += `<text x="${W - R}" y="${y0 - 4}" class="tick" text-anchor="end">${mi} peaks matched · ${ie} only this phase explains</text>`;
    });
    ticks(xmin, xmax, 10).forEach((v) => { g += `<text x="${sx(v)}" y="${H - 2}" class="tick" text-anchor="middle">${v}</text>`; });
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Contribution of each phase">${g}</svg><figcaption>${num1(2)} Evidence for each phase (2θ, °). Filled: the phase’s fitted contribution. Grey: the measurement minus background and all other selected phases, i.e. what this phase must explain. Own scale per panel; heights are not weight fractions.</figcaption></figure>`;
  }

  // Figure 3: competing hypotheses by selection score (lower is better).
  function alternativesFigure(report) {
    const m = report.mixture || {};
    const hyps = (m.hypotheses || []).filter((h) => Number.isFinite(h.selection_score)).slice(0, 5);
    if (hyps.length < 2) return "";
    const W = 680, L = 210, R = 70, row = 17, H = hyps.length * row + 26;
    const vmax = Math.max(...hyps.map((h) => h.selection_score)) * 1.05;
    const sx = (v) => L + (v / vmax) * (W - L - R);
    let g = "";
    ticks(0, vmax, niceStep(vmax, 4)).forEach((v) => { g += `<line x1="${sx(v)}" x2="${sx(v)}" y1="4" y2="${hyps.length * row + 4}" class="grid"/><text x="${sx(v)}" y="${hyps.length * row + 18}" class="tick" text-anchor="middle">${+v.toFixed(3)}</text>`; });
    hyps.forEach((h, i) => {
      const y = i * row + 8, sel = h.hypothesis_id === m.selected_hypothesis_id;
      const label = (h.components || []).map((c) => plain(formula(c.formula))).join(" + ");
      g += `<text x="${L - 8}" y="${y + 11}" class="${sel ? "panel" : "tick"}" text-anchor="end">${sel ? "▸ " : ""}${label}</text>`;
      g += `<rect x="${L}" y="${y + 2}" width="${Math.max(2, sx(h.selection_score) - L)}" height="12" rx="2" fill="${sel ? MODEL : "#c3c8cf"}"/>`;
      g += `<text x="${sx(h.selection_score) + 6}" y="${y + 12}" class="tick">${h.selection_score.toFixed(4)}</text>`;
    });
    return `<figure class="narrow"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Competing phase hypotheses">${g}</svg><figcaption>${num1(3)} Retained hypotheses by selection score (weighted misfit plus a penalty per added phase; lower is better). Close bars mean the data barely separate them.</figcaption></figure>`;
  }

  function build(report, opts = {}) {
    const r = report && report.result ? report.result : report;
    const p = r.provenance || {}, s = p.settings || {}, q = r.quality || {}, input = r.input || {};
    const meta = (p.input_source && p.input_source.metadata) || {};
    const rad = meta.source_radiation || {};
    const sel = selectedHypothesis(r);
    const phases = phasesOf(r);
    const generated = opts.date || new Date();
    const dateText = generated.toISOString().slice(0, 10);
    const reportId = `PHX-${r.analysis_id || "unknown"}`;
    const trace = p.measurement_trace || {};
    const points = Number(input.point_count) || 0;
    const step = points > 1 ? (Number(input.angle_max_deg) - Number(input.angle_min_deg)) / (points - 1) : NaN;
    const disp = p.coordinate_correction || {};
    const decisionText = { supported: "Supported", tentative: "Tentative", unresolved: "Unresolved", rejected: "Rejected" }[r.decision] || esc(r.decision);
    const decisionNote = {
      supported: "The selected phase set explains the pattern and passed line-position calibration.",
      tentative: "Most plausible phase set under the stated assumptions; not confirmed.",
      unresolved: "No phase set explains the pattern well enough to report.",
    }[r.decision] || "";
    const missing = sel ? (sel.missing_expected_lines || []).length : 0;
    const unexplained = sel ? (sel.unexplained_peak_positions || []).length : 0;
    const altClose = (() => { const hs = (r.mixture?.hypotheses || []).filter((h) => h !== sel && Number.isFinite(h.selection_score)); if (!sel || !hs.length) return null; const best = Math.min(...hs.map((h) => h.selection_score)); return (best - sel.selection_score) / sel.selection_score; })();
    const isPowcod = (p.reference_source || s.reference_source) === "pow_cod";
    const preset = isPowcod && (opts.preset || (s.candidate_pool === 100 && s.max_fit_attempts === 300 && s.complexity_penalty === 0.02 && s.oxidizing_synthesis === true ? "validated" : null));
    const elements = (s.allowed_elements || []).join(", ");

    const dbName = isPowcod ? `POW_COD ${esc(p.powcod_release || "")} (CNR, from COD)` : "Built-in demo subset (three phases; not for real samples)";
    const fallbackRows = (r.candidates || []).slice(0, 5).map((c, k) => `<tr><td>${k + 1}</td><td class="f">${formula(c.formula)}</td><td>${spaceGroup(c.space_group)}</td><td>${codLink(c.reference_id)}</td><td class="n">${esc(c.matched_peaks ?? "—")}</td><td class="n">score ${num(c.score, 2)}</td></tr>`).join("");
    const phaseRows = phases.map((ph, k) => {
      const c = ph.component;
      return `<tr><td><span class="sw" style="background:${ph.color}"></span>${k + 1}</td><td class="f">${formula(c.formula)}</td><td>${spaceGroup(c.space_group)}</td><td>${codLink(c.reference_id)}</td><td class="n">${(c.matched_peak_indices || []).length}</td><td class="n">${(c.independent_evidence_peak_indices || []).length}</td></tr>`;
    }).join("");

    const interpretation = [];
    if (phases.length) interpretation.push(`The pattern is best explained by ${phases.length === 1 ? "one phase" : `${phases.length} phases`}: ${phases.map((ph) => formula(ph.component.formula)).join(" and ")}.`);
    if (sel) interpretation.push(unexplained ? `${unexplained} detected peak${unexplained > 1 ? "s remain" : " remains"} unexplained (marked ▼ in Figure 1), which suggests an additional, unidentified phase.` : "Every detected peak is assigned to a selected phase (assignment by position; it does not prove the phase is present).");
    if (altClose !== null && altClose < 0.1) interpretation.push(`The runner-up hypothesis scores within ${(altClose * 100).toFixed(1)}% of the selected one (Figure 3), so the choice between them is weak and should be confirmed.`);
    if (missing) interpretation.push(`${missing} reference reflections expected in the measured range were not detected. Weak lines are often lost in noise; strong missing lines would argue against a phase.`);

    const warnings = (q.warnings || []).map(esc).join(" ");
    const kv = (k, v) => `<div class="kv"><dt>${k}</dt><dd>${v}</dd></div>`;

    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phase identification report ${esc(reportId)}</title>
<style>
@page { size: A4; margin: 14mm 17mm 15mm 17mm;
  @bottom-left { content: "${esc(reportId)} · Automated result (Phasentic ${esc(opts.version || "")}), not human-reviewed unless signed"; font: 8pt Georgia, serif; color: ${MUTED}; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt Georgia, serif; color: ${MUTED}; } }
:root { --ink: ${INK}; --muted: ${MUTED}; --rule: ${RULE}; }
* { box-sizing: border-box; }
html { background: #eceef1; }
body { margin: 0; color: var(--ink); font: 9.5pt/1.4 "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.sheet { background: #fff; max-width: 210mm; margin: 24px auto; padding: 17mm 18mm; box-shadow: 0 1px 4px rgba(0,0,0,.12); }
@media print { html { background: #fff; } .sheet { margin: 0; padding: 0; box-shadow: none; max-width: none; } a { color: inherit; text-decoration: none; } }
.auto { margin: 8pt 0 2pt; padding: 6pt 9pt; border: .8pt solid var(--ink); border-left-width: 3pt; font-size: 8.5pt; line-height: 1.4; break-inside: avoid; }
.auto b { font-variant: small-caps; letter-spacing: .05em; font-size: 9pt; }
header { text-align: center; border-bottom: 1.2pt solid var(--ink); padding-bottom: 9pt; margin-bottom: 4pt; }
.brand { font-variant: small-caps; letter-spacing: .14em; font-size: 9pt; color: var(--muted); }
h1 { font-weight: 400; font-size: 21pt; letter-spacing: .01em; margin: 2pt 0 4pt; }
.idline { font-size: 9pt; color: var(--muted); }
.idline b { color: var(--ink); font-weight: 600; }
h2 { font-variant: small-caps; letter-spacing: .1em; font-weight: 600; font-size: 10pt; border-bottom: .6pt solid var(--ink); padding-bottom: 2pt; margin: 10pt 0 4pt; break-after: avoid; }
.result { display: grid; grid-template-columns: 30mm 1fr; gap: 0 10pt; align-items: baseline; }
.verdict { font-size: 15pt; }
.verdict small { display: block; font-size: 8pt; color: var(--muted); font-variant: small-caps; letter-spacing: .08em; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; margin-top: 6pt; }
th { text-align: left; font-weight: 600; font-size: 8.5pt; color: var(--muted); border-bottom: .6pt solid var(--ink); padding: 3pt 6pt 3pt 0; }
td { border-bottom: .4pt solid var(--rule); padding: 2.5pt 6pt 2.5pt 0; vertical-align: baseline; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
td.f { font-size: 10.5pt; }
.sw { display: inline-block; width: 8pt; height: 8pt; border-radius: 2pt; margin-right: 5pt; vertical-align: -.5pt; }
.note { font-size: 8.5pt; color: var(--muted); margin: 4pt 0 0; }
p { margin: 0 0 5pt; }
ul { margin: 0; padding-left: 13pt; } li { margin-bottom: 1pt; }
.label-op { font-variant: small-caps; letter-spacing: .06em; color: var(--muted); font-size: 8.5pt; }
figure { margin: 8pt 0 2pt; break-inside: avoid; }
svg { width: 100%; height: auto; display: block; font-family: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
svg .grid { stroke: #eceef0; stroke-width: .8; } svg .axis { stroke: #8c939d; stroke-width: .8; }
svg .bg { fill: none; stroke: #b9bec6; stroke-width: .8; stroke-dasharray: 3 3; }
svg .tick { font-size: 9px; fill: ${MUTED}; } svg .label { font-size: 9.5px; fill: ${MUTED}; } svg .panel { font-size: 10.5px; fill: ${INK}; font-weight: 600; }
figcaption { font-size: 8.5pt; color: var(--muted); margin-top: 4pt; } figcaption b { color: var(--ink); font-weight: 600; }
.legend { display: flex; flex-wrap: wrap; gap: 3pt 12pt; font: 8.5pt system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: var(--muted); margin-top: 4pt; }
.legend i { display: inline-block; width: 14pt; vertical-align: middle; margin-right: 4pt; }
.legend i.dash { border-top: 1px dashed #b9bec6; } .legend i.tickkey { width: 2pt; height: 8pt; }
dl { margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 0 18pt; }
.kv { display: grid; grid-template-columns: 34mm 1fr; border-bottom: .4pt solid var(--rule); padding: 1.6pt 0; font-size: 8.5pt; break-inside: avoid; }
.kv dt { color: var(--muted); }
dl.one { grid-template-columns: 1fr; } dl.one .kv { grid-template-columns: 34mm 1fr; } .kv dd { margin: 0; overflow-wrap: anywhere; }
.mono { font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 7.5pt; }
.sign { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14pt; margin-top: 8pt; break-inside: avoid; }
.sign div { border-top: .6pt solid var(--ink); padding-top: 3pt; font-size: 8pt; color: var(--muted); margin-top: 16pt; }
.fields { display: grid; grid-template-columns: 1fr 1fr; gap: 0 18pt; }
.fields .kv dd { border-bottom: none; min-height: 12pt; }
.hint { max-width: 210mm; margin: 16px auto 0; font: 9pt system-ui, sans-serif; color: var(--muted); text-align: center; }
@media print { .hint { display: none; } }
.statement { font-size: 8pt; color: var(--muted); margin-top: 6pt; }
</style></head>
<body><p class="hint">To save as PDF: File → Print → Save as PDF (A4). This line does not print.</p><main class="sheet">
<header>
  <div class="brand">Phasentic · powder X-ray diffraction</div>
  <h1>Phase Identification Report</h1>
  <div class="idline">Report <b>${esc(reportId)}</b> · issued ${esc(dateText)} · sample file <b>${esc(input.file_name || "—")}</b></div>
</header>
<aside class="auto" role="note"><b>Automated analysis — not reviewed by a person.</b> Every result, figure and interpretation in this report was produced by the Phasentic software directly from the measurement file. It is not a human-refined result: no analyst has checked it and no Rietveld refinement was performed. No AI model is used; the analysis is a fixed, reproducible algorithm. Treat it as a screening result until a qualified analyst confirms it and signs below.</aside>

<section>
  <h2>Report details</h2>
  <div class="fields">
    ${kv("Laboratory", "&nbsp;")}${kv("Customer", "&nbsp;")}
    ${kv("Sample description", "&nbsp;")}${kv("Date received / measured", "&nbsp;")}
  </div>
</section>

<section>
  <h2>Result</h2>
  <div class="result">
    <div class="verdict">${decisionText}<small>decision</small></div>
    <p>${esc(decisionNote)} ${!sel ? "No mixture was selected; the table lists the best-ranked single candidates instead." : unexplained ? "" : "No detected peak is left unexplained."}</p>
  </div>
  <table>
    <thead><tr><th>#</th><th>Phase</th><th>Space group</th><th>Reference</th><th class="n">Peaks matched</th><th class="n">Unique evidence</th></tr></thead>
    <tbody>${phaseRows || fallbackRows || `<tr><td colspan="6">No candidate phases.</td></tr>`}</tbody>
  </table>
  <p class="note">Phases are ranked hypotheses from the ${isPowcod ? `POW_COD ${esc(p.powcod_release || "")}` : "demo"} reference database, not certainties. “Unique evidence” counts detected peaks that no other selected phase explains. No phase fractions are reported.</p>
</section>

${phases.length ? fitFigure(r, phases) : measuredFigure(r)}

<section>
  <h2>Interpretation <span class="label-op">· opinion, not a measured result</span></h2>
  <ul>${interpretation.map((t) => `<li>${t}</li>`).join("")}</ul>
</section>

${phaseFigure(r, phases)}
${alternativesFigure(r)}

<section>
  <h2>Method and measurement</h2>
  <dl>
    ${kv("Method", `Phasentic ${esc(opts.version || "")}${preset ? ", validated method" : ", custom settings (not validated)"}`)}
    ${kv("Reference database", dbName)}
    ${kv("Sample chemistry", elements ? `restricted to ${esc(elements)}` : "not restricted")}
    ${kv("Radiation", `${esc(r.radiation?.label || "")}${rad.ka1_angstrom ? `, λ(Kα₁) ${num(rad.ka1_angstrom, 6)} Å` : ""}${rad.ka2_angstrom ? `, λ(Kα₂) ${num(rad.ka2_angstrom, 6)} Å` : ""}`)}
    ${kv("Scan range", `${num(input.angle_min_deg, 2)}–${num(input.angle_max_deg, 2)}° 2θ`)}
    ${kv("Step / points", `${num(step, 4)}° / ${points}`)}
    ${kv("Data format", `${esc(input.file_extension || "")}${meta.format_owner ? ` (${esc(meta.format_owner)})` : ""}`)}
    ${kv("Instrument", s.instrument ? esc(JSON.stringify(s.instrument)) : "not provided")}
    ${kv("Displacement correction", Number.isFinite(disp.sample_displacement_deg) ? `${num(disp.sample_displacement_deg, 3)}° (Δ2θ = D·cos θ)` : "none")}
    ${kv("Line-position calibration", esc(q.calibration_status || "unverified"))}
    ${kv("Detected peaks", `${(r.peaks || []).length} (noise-aware, S/N ≥ ${num(s.peak_min_snr, 0)})`)}
    ${kv("Signal-to-noise", num(q.signal_to_noise, 0))}
    ${kv("Matching tolerance", `${num(s.peak_tolerance_deg, 2)}° 2θ`)}
    ${kv("Phases allowed", `up to ${esc(s.max_phases ?? "—")}`)}
  </dl>
  ${warnings ? `<p class="note" style="margin-top:5pt"><b>Quality warnings.</b> ${warnings}</p>` : ""}
</section>

<section>
  <h2>Limitations</h2>
  <p class="note">Identification only: no Rietveld refinement, phase fractions or lattice parameters. Only phases in the reference database and allowed by the stated chemistry can be found; minor phases (below a few weight percent) and weakly scattering phases next to heavy-element phases are often missed. The uncertainty of an individual identification is not estimated; on a sealed test of 200 synthesis products the validated method found the exact phases in 37% of samples and the right compounds in 49.5%, with accuracy falling sharply for three or more phases.</p>
</section>

<section>
  <h2>Traceability</h2>
  <dl class="one">
    ${kv("Analysis ID", `<span class="mono">${esc(r.analysis_id)}</span>`)}
    ${kv("Input SHA-256", `<span class="mono">${esc(input.sha256)}</span>`)}
    ${kv("Engine", `<span class="mono">${esc(p.algorithm_version)}</span>`)}
    ${kv("Mixture search", `<span class="mono">${esc(r.mixture?.algorithm_version)}</span>`)}
    ${kv("Database SHA-256", `<span class="mono">${esc(p.powcod_database_sha256 || "—")}</span>`)}
    ${kv("Report schema", `<span class="mono">${esc(r.schema_version)}</span>`)}
  </dl>
  <p class="note">Every setting and intermediate result is in the JSON report with the same analysis ID.</p>
</section>

<section>
  <h2>Authorisation</h2>
  <div class="sign"><div>Analysed by — name, signature, date</div><div>Reviewed by — name, signature, date</div><div>Authorised by — name, signature, date</div></div>
  <p class="statement">Results relate only to the item tested. This report shall not be reproduced except in full without the written approval of the issuing laboratory. Produced automatically by Phasentic; until the signature fields above are completed, this is an unreviewed screening result, not a laboratory finding.</p>
</section>
</main></body></html>`;
  }

  // Figures without "Figure N." numbering, for the web interface.
  const unnumbered = (fn) => (report) => { numbered = false; try { return fn(report); } finally { numbered = true; } };
  const api = {
    build,
    formula,
    spaceGroup,
    codLink,
    PHASE_COLORS,
    figures: {
      fit: unnumbered((r) => (phasesOf(r).length ? fitFigure(r, phasesOf(r)) : measuredFigure(r))),
      phases: unnumbered((r) => phaseFigure(r, phasesOf(r))),
      alternatives: unnumbered(alternativesFigure),
    },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PhasenticReport = api;
})(typeof window !== "undefined" ? window : globalThis);
