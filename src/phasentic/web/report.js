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
    return t.map((s) => esc(s).replace(/-(\d)/g, "$1&#773;").replace(/^(\d)(\d)/, "$1<sub>$2</sub>").replace(/(\d)_(\d)/g, "$1<sub>$2</sub>")).join("").replace(/([A-Za-z])(?![^<]*>)/g, "<i>$1</i>");
  }

  // HTML subscripts -> Unicode, for SVG text.
  const plain = (html) => String(html).replace(/<sub>(.*?)<\/sub>/g, (_, d) => d.replace(/\d/g, (n) => "₀₁₂₃₄₅₆₇₈₉"[n])).replace(/<[^>]+>/g, "");

  function codLink(referenceId) {
    const id = String(referenceId || "").replace(/^powcod:/, "");
    if (/^\d+$/.test(id)) return `<a href="https://www.crystallography.net/cod/${id}.html">COD ${id}</a>`;
    // Materials Project entries (experimental structures, DFT-relaxed) added to the COD-derived database.
    if (/^mp-\d+$/.test(id)) return `<a href="https://next-gen.materialsproject.org/materials/${id}">MP ${id.slice(3)}</a>`;
    return esc(referenceId);
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
    g += `<text x="${(L + W - R) / 2}" y="${H - 1}" class="label" text-anchor="middle">2θ / °  (${esc(report.radiation?.label || "")})</text>`;
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Measured pattern and detected peaks">${g}</svg><figcaption>${num1(1)}Measured pattern. Ticks mark the ${(report.peaks || []).length} detected peaks; no mixture fit was selected.</figcaption></figure>`;
  }

  // A database name worth printing (not just the entry ID or the formula again).
  const realName = (c) => Boolean(c.name) && c.name !== c.formula && !/^(cod|powcod)[: ]/i.test(c.name);

  function selectedHypothesis(report) {
    const m = report.mixture || {};
    return (m.hypotheses || []).find((h) => h.hypothesis_id === m.selected_hypothesis_id) || null;
  }

  // Figure 1: observed vs model with difference curve and assigned-peak ticks per phase.
  // view = {x0, x1, y0?, y1?} zooms the figure (web interface); omitted for the full range.
  function fitFigure(report, phases, view) {
    const t = report.mixture && report.mixture.residual_trace;
    if (!t || !t.angles_deg) return "";
    const all = t.angles_deg;
    // Keep the points inside the x range plus one neighbour each side; clip paths trim the rest.
    let i0 = 0, i1 = all.length - 1;
    if (view) {
      while (i0 < all.length - 1 && all[i0 + 1] < view.x0) i0++;
      while (i1 > 0 && all[i1 - 1] > view.x1) i1--;
    }
    const cut = (a) => a.slice(i0, i1 + 1);
    const x = cut(all), obs = cut(t.observed_intensities), bg = cut(t.background_intensities);
    const model = cut(t.calculated_intensities).map((v, i) => v + bg[i]);
    const res = cut(t.residual_intensities);
    const W = 680, L = 52, R = 12, top = 8, mainH = 148, gap = 7, tickRow = 11, diffH = 38;
    const tickTop = top + mainH + gap, diffTop = tickTop + phases.length * tickRow + 8, H = diffTop + diffH + 30;
    const xmin = view ? view.x0 : x[0], xmax = view ? view.x1 : x[x.length - 1];
    const inside = x.map((v) => v >= xmin && v <= xmax);
    const seen = (a) => a.filter((_, i) => inside[i]);
    const zoomY = view && Number.isFinite(view.y0) && Number.isFinite(view.y1);
    const ymax = zoomY ? view.y1 : Math.max(...seen(obs), ...seen(model)) * 1.04, ymin = zoomY ? view.y0 : Math.min(0, ...seen(obs));
    const rmax = Math.max(...seen(res).map(Math.abs)) || 1;
    const sx = (v) => L + ((v - xmin) / (xmax - xmin)) * (W - L - R);
    const sy = (v) => top + mainH - ((v - ymin) / (ymax - ymin)) * mainH;
    const sd = (v) => diffTop + diffH / 2 - (v / rmax) * (diffH / 2);
    const xt = ticks(xmin, xmax, view ? niceStep(xmax - xmin, 8) : 10), yt = ticks(Math.max(0, ymin), ymax, niceStep(ymax - Math.max(0, ymin), 4));
    const inX = (v) => v >= xmin && v <= xmax;
    let g = `<defs><clipPath id="fit-main"><rect x="${L}" y="${top}" width="${W - L - R}" height="${mainH}"/></clipPath><clipPath id="fit-diff"><rect x="${L}" y="${diffTop}" width="${W - L - R}" height="${diffH}"/></clipPath></defs>`;
    yt.forEach((v) => { g += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/><text x="${L - 6}" y="${sy(v) + 3}" class="tick" text-anchor="end">${fmtCount(v)}</text>`; });
    xt.forEach((v) => { g += `<line x1="${sx(v)}" x2="${sx(v)}" y1="${diffTop + diffH}" y2="${diffTop + diffH + 4}" class="axis"/><text x="${sx(v)}" y="${diffTop + diffH + 15}" class="tick" text-anchor="middle">${+v.toFixed(2)}</text>`; });
    g += `<g clip-path="url(#fit-main)"><path d="${path(x, bg, sx, sy)}" class="bg"/>`;
    g += `<path d="${path(x, obs, sx, sy)}" fill="none" stroke="${OBS}" stroke-width="1.6"/>`;
    g += `<path d="${path(x, model, sx, sy)}" fill="none" stroke="${MODEL}" stroke-width="1"/></g>`;
    const peaks = report.peaks || [];
    phases.forEach((p, k) => {
      const y = tickTop + k * tickRow + tickRow / 2;
      (p.component.matched_peak_indices || []).forEach((idx) => { const pk = peaks[idx]; if (pk && inX(pk.position_deg)) g += `<line x1="${sx(pk.position_deg)}" x2="${sx(pk.position_deg)}" y1="${y - 4}" y2="${y + 4}" stroke="${p.color}" stroke-width="1.6"/>`; });
      g += `<text x="${L - 6}" y="${y + 3}" class="tick" text-anchor="end">${k + 1}</text>`;
    });
    (selectedHypothesis(report)?.unexplained_peak_positions || []).filter(inX).forEach((pos) => { g += `<path d="M${sx(pos)},${tickTop - 6} l-3,-5 h6z" fill="${INK}"/>`; });
    g += `<line x1="${L}" x2="${W - R}" y1="${sd(0)}" y2="${sd(0)}" class="grid"/>`;
    g += `<path d="${path(x, res, sx, sd)}" fill="none" stroke="${MUTED}" stroke-width="0.8" clip-path="url(#fit-diff)"/>`;
    g += `<text x="${L - 6}" y="${diffTop + 8}" class="tick" text-anchor="end">Δ</text>`;
    g += `<line x1="${L}" x2="${W - R}" y1="${diffTop + diffH}" y2="${diffTop + diffH}" class="axis"/>`;
    g += `<text x="${(L + W - R) / 2}" y="${H - 2}" class="label" text-anchor="middle">2θ / °  (${esc(report.radiation?.label || "")}, corrected for specimen displacement)</text>`;
    g += `<text x="12" y="${top + mainH / 2}" class="label" text-anchor="middle" transform="rotate(-90 12 ${top + mainH / 2})">Intensity / counts</text>`;
    const legend = `<div class="legend"><span><i style="background:${OBS};height:2px"></i>Measured</span><span><i style="background:${MODEL};height:1px"></i>Model (background + phases)</span><span><i class="dash"></i>Background</span>${phases.map((p, k) => `<span><i class="tickkey" style="background:${p.color}"></i>${k + 1} ${formula(p.component.formula)}</span>`).join("")}<span><i style="background:${MUTED};height:1px"></i>Δ measured − model</span></div>`;
    const zoom = `data-zoom="${[L, W - R, top, mainH, diffTop + diffH, xmin, xmax, ymin, ymax].join(",")}"`;
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Measured pattern, fitted model and difference curve" ${zoom}>${g}</svg>${legend}<figcaption>${num1(1)} Observed (grey), calculated (black, background plus phases) and difference (lower panel, observed − calculated) profiles. Tick rows mark the detected peaks assigned to each phase; ▼ marks detected peaks no selected phase explains.</figcaption></figure>`;
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
    return `<figure><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Contribution of each phase">${g}</svg><figcaption>${num1(2)} Evidence for each phase (abscissa 2θ / °). Filled: the phase’s fitted contribution. Grey: the measurement minus background and all other selected phases, i.e. what this phase must explain. Own scale per panel; heights are not weight fractions.</figcaption></figure>`;
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

  // Printable report. Structure: ISO/IEC 17025:2017 §7.8 (report content, opinions marked, decision
  // rule, authorisation), ANSI/NISO Z39.18 (summary, scope, methods, results, conclusions, references,
  // symbols), IUCr powder-diffraction reporting (measurement conditions, data processing, observed /
  // calculated / difference plot, numeric data as pdCIF) and ISO 80000 quantity/unit notation.
  function build(report, opts = {}) {
    const r = report && report.result ? report.result : report;
    const p = r.provenance || {}, s = p.settings || {}, q = r.quality || {}, input = r.input || {};
    const meta = (p.input_source && p.input_source.metadata) || {};
    const rad = meta.source_radiation || {}, acq = meta.acquisition || {};
    const sel = selectedHypothesis(r);
    const phases = phasesOf(r);
    const generated = opts.date || new Date();
    const dateText = generated.toISOString().slice(0, 10);
    const reportId = `PHX-${r.analysis_id || "unknown"}`;
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
    const preset = isPowcod && opts.preset === "validated";
    const elements = (s.allowed_elements || []).join(", ");
    const release = String(p.powcod_release || "");
    const isPowcodRelease = isPowcod && !release.includes("COD");
    const dbShort = release.includes("COD") ? esc(release) : `POW_COD ${esc(release)}`;
    const dbName = !isPowcod ? "the built-in demo subset (three phases; not for real samples)"
      : release.includes("COD") ? `${dbShort}, powder patterns calculated from the Crystallography Open Database [2]` : `${dbShort} (CNR) [3], from the Crystallography Open Database [2]`;
    const pct = (v, d = 1) => (Number.isFinite(Number(v)) ? `${Number(v).toFixed(d)}&#8201;%` : "—");  // ISO 80000: space before %
    const pinned = Array.isArray(s.pinned_reference_ids) ? s.pinned_reference_ids : [];
    const mq = (r.mixture && r.mixture.query) || {};
    const lab = String(opts.laboratory || "").trim();

    const lambda = `${rad.ka1_angstrom ? `<i>λ</i>(K<i>α</i><sub>1</sub>) = ${num(rad.ka1_angstrom, 6)} Å` : ""}${rad.ka2_angstrom ? `, <i>λ</i>(K<i>α</i><sub>2</sub>) = ${num(rad.ka2_angstrom, 6)} Å` : ""}${rad.ka2_to_ka1_intensity_ratio != null ? `, <i>I</i>(K<i>α</i><sub>2</sub>)/<i>I</i>(K<i>α</i><sub>1</sub>) = ${num(rad.ka2_to_ka1_intensity_ratio, 3)}` : ""}`;
    const part = (v) => esc(String(v).replace(/\.+$/, ""));
    const slits = [acq.divergence_slit, acq.mask, acq.incident_soller, acq.antiscatter_slit, acq.diffracted_soller].filter(Boolean).map(part).join("; ");
    const filters = [acq.incident_filter, acq.diffracted_filter, acq.monochromator].filter(Boolean).map(part).join("; ");
    const eta = Number(s.profile_eta);
    const widthModel = p.reference_query?.candidate_query_stats?.profile_width;

    // Table 1: identified phases (journal style: horizontal rules only).
    const fallback = (r.candidates || []).filter((c) => Number(c.matched_peaks) > 0).slice(0, 5);
    const phaseName = (c) => (realName(c) ? esc(c.name) : "—");
    const refCell = (c) => `${codLink(c.reference_id)}${pinned.includes(c.reference_id) ? "<sup>‡</sup>" : ""}`;
    const phaseRows = phases.map((ph, k) => {
      const c = ph.component;
      return `<tr><td>${k + 1}</td><td>${formula(c.formula)}</td><td>${phaseName(c)}</td><td>${spaceGroup(c.space_group)}</td><td>${refCell(c)}</td><td class="n">${(c.matched_peak_indices || []).length}</td><td class="n">${(c.independent_evidence_peak_indices || []).length}</td></tr>`;
    }).join("");
    const fallbackRows = fallback.map((c, k) => `<tr><td>${k + 1}</td><td>${formula(c.formula)}</td><td>${phaseName(c)}</td><td>${spaceGroup(c.space_group)}</td><td>${codLink(c.reference_id)}</td><td class="n">${esc(c.matched_peaks ?? "—")}</td><td class="n">—</td></tr>`).join("");

    // Table 2: alternatives per phase.
    const alts = r.mixture && r.mixture.phase_alternatives && typeof r.mixture.phase_alternatives === "object" ? r.mixture.phase_alternatives : {};
    const altRows = phases.filter((ph) => alts[ph.component.reference_id]).map((ph) => {
      const entry = alts[ph.component.reference_id];
      const rows = [{ ...ph.component, fit_percent: entry.fit_percent, own: true }, ...(entry.alternatives || [])]
        .sort((a, b) => Number(b.fit_percent) - Number(a.fit_percent));
      return rows.map((a, k) => `<tr${k === 0 ? ' class="group"' : ""}><td>${k === 0 ? phases.indexOf(ph) + 1 : ""}</td><td>${formula(a.formula)}${a.own ? "*" : ""}</td><td>${spaceGroup(a.space_group)}</td><td>${codLink(a.reference_id)}</td><td class="n">${pct(a.fit_percent)}</td></tr>`).join("");
    }).join("");

    // Discussion (opinion), as prose.
    const discussion = [];
    if (pinned.length) discussion.push(`The entr${pinned.length > 1 ? "ies" : "y"} ${pinned.map(codLink).join(", ")} ${pinned.length > 1 ? "were" : "was"} fixed by the operator from the alternatives in Table 2 rather than selected automatically; the remaining phases were searched around ${pinned.length > 1 ? "them" : "it"} (marked ‡ in Table 1).`);
    if (phases.length) discussion.push(`The pattern is best explained by ${phases.length === 1 ? "a single phase" : `${phases.length} phases`}, ${phases.map((ph) => formula(ph.component.formula)).join(" and ")} (Table 1, Fig. 1).`);
    if (sel) discussion.push(unexplained ? `${unexplained} detected peak${unexplained > 1 ? "s remain" : " remains"} unexplained (▼ in Fig. 1), which points to a further, unidentified phase.` : "Every detected peak is assigned to a selected phase; the assignment is by position and does not by itself prove that a phase is present.");
    if (altClose !== null && altClose < 0.1) discussion.push(`The runner-up phase set scores within ${pct(altClose * 100)} of the selected one (Fig. 3), so the data separate them only weakly.`);
    if (missing) discussion.push(`${missing} reference reflections expected in the measured range were not detected; weak lines are often lost in noise, whereas missing strong lines would argue against a phase.`);

    const phaseList = phases.map((ph) => `${formula(ph.component.formula)} (${spaceGroup(ph.component.space_group)})`).join(", ");
    const itemName = esc(input.file_name || "the item");
    const dbPhrase = isPowcod ? "reference patterns calculated from the Crystallography Open Database" : "a demonstration reference set";
    const abstract = phases.length
      ? `The powder X-ray diffraction pattern of ${itemName} was compared with ${dbPhrase}${elements ? `, restricted to the elements ${esc(elements)}` : ""}. The best-supported phase set is ${phaseList} (decision: ${decisionText.toLowerCase()}${pinned.length ? "; one phase fixed by the operator" : ""}).${unexplained ? ` ${unexplained} detected peak${unexplained > 1 ? "s are" : " is"} not explained by these phases.` : ""} The identification is qualitative: no phase quantities, lattice parameters or Rietveld refinement are reported.`
      : `The powder X-ray diffraction pattern of ${itemName} was compared with ${dbPhrase}. No phase set explained the pattern well enough to be reported (decision: ${decisionText.toLowerCase()}).`;
    const conclusion = phases.length
      ? `${phaseList} ${phases.length > 1 ? "are" : "is"} identified as ${r.decision === "supported" ? "present (supported)" : "the most plausible phase set; the identification is tentative and must be confirmed by an analyst"}. No further conclusion should be drawn from this report without review.`
      : "No phase is identified. The scan quality, the stated chemistry and the presence of the expected phases in the reference database should be checked.";

    // Experimental section, written from the measurement file where it records the conditions.
    const unit = (v) => esc(String(v || "").replace(/ seconds$/, " s").replace(/ deg$/, "°"));
    const sentence = (parts) => parts.filter(Boolean).join(" ");
    const measured = acq.measured_start ? (() => {
      const [d0, t0] = String(acq.measured_start).split("T"), t1 = acq.measured_end ? String(acq.measured_end).split("T")[1] : "";
      const zone = (t0 || "").match(/[+-]\d\d:\d\d$|Z$/);
      const clock = (t) => (t || "").slice(0, 5);
      return `on ${esc(d0)} between ${clock(t0)} and ${clock(t1)}${zone ? ` (UTC${zone[0] === "Z" ? "" : zone[0].replace("-", "−")})` : ""}`;
    })() : "";
    const experimental1 = sentence([
      `The pattern (file ${itemName}) was recorded${acq.sample_mode ? ` in ${esc(acq.sample_mode.toLowerCase())} geometry` : ""}${acq.instrument_id || acq.instrument_software ? ` on a diffractometer (${[acq.instrument_id && `instrument ${esc(acq.instrument_id)}`, acq.instrument_software && `control software ${esc(acq.instrument_software)}`].filter(Boolean).join(", ")})` : ""}${acq.goniometer_radius ? ` with a goniometer radius of ${unit(acq.goniometer_radius)}` : ""}, using ${esc(r.radiation?.label || "the stated")} radiation${lambda ? ` (${lambda})` : ""}${acq.tube ? ` from a ${esc(acq.tube)} tube${acq.tube_voltage && acq.tube_current ? ` operated at ${unit(acq.tube_voltage)} and ${unit(acq.tube_current)}` : ""}` : ""}.`,
      filters ? `K<i>β</i> radiation was suppressed with: ${filters}.` : "",
      slits ? `Beam optics: ${slits}.` : "",
      acq.detector ? `Intensities were recorded with a ${esc(acq.detector)}${acq.detector_mode ? ` in ${esc(acq.detector_mode.toLowerCase())} mode` : ""}.` : "",
      `Data were collected${acq.scan_mode ? ` in ${esc(acq.scan_mode.toLowerCase())} mode` : ""} from 2<i>θ</i> = ${num(input.angle_min_deg, 3)}° to ${num(input.angle_max_deg, 3)}° in steps of ${num(step, 4)}° (${points} points)${acq.counting_time ? `, ${unit(acq.counting_time)} per step` : ""}${acq.sample_spinning ? `, with the specimen rotating once every ${unit(acq.sample_spinning)}` : ""}${measured ? `, ${measured}` : ""}.`,
      "Specimen preparation, temperature and atmosphere were not recorded in the measurement file; ambient conditions are assumed.",
    ]);
    const background = s.background_window_deg != null ? ` (window ${num(s.background_window_deg, 1)}°)` : "";
    const experimental2 = sentence([
      `The background was estimated with a smoothed rolling 20th-percentile filter${background} and subtracted before fitting.`,
      `${(r.peaks || []).length} peaks were located by a noise-aware search (signal-to-noise ratio ≥ ${num(s.peak_min_snr, 0)}).`,
      Number.isFinite(disp.sample_displacement_deg) && Math.abs(disp.sample_displacement_deg) > 0 ? `A specimen displacement of ${num(disp.sample_displacement_deg, 3)}° (Δ2<i>θ</i> = <i>D</i> cos <i>θ</i>) was corrected.` : "No specimen-displacement correction was needed.",
      `Reference powder patterns were calculated from entries of ${dbName}${elements ? ` containing only ${esc(elements)}` : ""} and broadened with a pseudo-Voigt profile${Number.isFinite(eta) ? ` (Lorentzian fraction <i>η</i> = ${num(eta, 2)})` : ""}${widthModel && widthModel.status === "estimated" ? ` whose width followed FWHM = <i>a</i> + <i>b</i> tan <i>θ</i>, with <i>a</i> = ${num(widthModel.a_deg, 4)}° and <i>b</i> = ${num(widthModel.b_deg, 4)}° estimated from ${esc(widthModel.peaks_used ?? "")} peaks of the scan` : ` of fixed width ${num(s.profile_width_deg, 2)}°`}.`,
      `Sets of up to ${esc(s.max_phases ?? "—")} phases were evaluated by a bounded beam search (${esc(mq.fit_attempts ?? "—")} fits), scaling the calculated profiles to the background-subtracted pattern by non-negative least squares with weights from the 2<i>θ</i> grid spacing; peaks were matched within ±${num(s.peak_tolerance_deg, 2)}°.`,
      "No structural (Rietveld) refinement was performed.",
      `Line positions were ${q.calibration_status === "passed" ? "calibrated against a certified standard" : `not verified against a certified standard (calibration status: ${esc(q.calibration_status || "unverified")})`}.`,
      `The analysis used Phasentic ${esc(opts.version || "")} [1]${preset ? " with its validated settings" : " with custom settings that have not been validated"}.`,
    ]);

    const references = [
      `Phasentic ${esc(opts.version || "")} (2026). <i>Powder X-ray diffraction phase identification software</i>. https://github.com/qaemu/phasentic.`,
      `Gražulis, S., Daškevič, A., Merkys, A., Chateigner, D., Lutterotti, L., Quirós, M., Serebryanaya, N. R., Moeck, P., Downs, R. T. &amp; Le Bail, A. (2012). <i>Nucleic Acids Res.</i> <b>40</b>, D420–D427. https://doi.org/10.1093/nar/gkr900.`,
      `Altomare, A., Corriero, N., Cuocci, C., Falcicchio, A., Moliterni, A. &amp; Rizzi, R. (2015). <i>J. Appl. Cryst.</i> <b>48</b>, 598–603. https://doi.org/10.1107/S1600576715002319.`,
      `ISO/IEC 17025:2017. <i>General requirements for the competence of testing and calibration laboratories</i>. Geneva: International Organization for Standardization.`,
      `EN 13925-1:2003. <i>Non-destructive testing — X-ray diffraction from polycrystalline and amorphous material — Part 1: General principles</i>. Brussels: European Committee for Standardization.`,
    ];
    const dataFiles = opts.files || {};
    const warnings = (q.warnings || []).map(esc).join(" ");
    const row = (k, v) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`;
    const blank = "";
    const labLines = lab ? esc(lab).split("\n") : [];
    const title = `Qualitative phase analysis of ${esc(String(input.file_name || "the item").replace(/\.[^.]+$/, ""))} by powder X-ray diffraction`;

    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(reportId)}: ${esc(input.file_name || "phase identification")}</title>
<style>
@page { size: A4; margin: 20mm;
  @bottom-center { content: "${esc(reportId)}  —  page " counter(page) " of " counter(pages); font: 9pt "Times New Roman", "Liberation Serif", Times, serif; } }
body { margin: 0; color: #000; background: #fff; font: 11pt/1.4 "Times New Roman", "Liberation Serif", "Nimbus Roman", Times, serif; }
.page { max-width: 170mm; margin: 0 auto; padding: 20mm 0; }
@media print { .page { padding: 0; max-width: none; } .hint { display: none; } }
.hint { font: 9pt sans-serif; color: #555; text-align: center; margin: 8px 0 0; }
a { color: inherit; text-decoration: none; }
.kicker { font-size: 10pt; margin: 0 0 12pt; }
.kicker span + span::before { content: " — "; }
h1 { font-size: 15pt; font-weight: 700; margin: 0 0 6pt; }
.authors, .affil, .dates { margin: 0; font-size: 11pt; }
.dates { margin-bottom: 12pt; }
.abstract, .keywords, .notice { margin: 0 0 8pt; }
h2 { font-size: 12pt; font-weight: 700; margin: 14pt 0 4pt; break-after: avoid; }
h3 { font-size: 11pt; font-weight: 700; margin: 10pt 0 3pt; break-after: avoid; }
p { margin: 0 0 6pt; }
.span { margin: 8pt 0; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; font-size: 10pt; }
caption { caption-side: top; text-align: left; padding-bottom: 3pt; }
th, td { border: .5pt solid #000; padding: 2pt 5pt; text-align: left; vertical-align: top; }
thead th { font-weight: 700; }
td.n, th.n { text-align: right; }
.tnote { font-size: 10pt; margin: 3pt 0 0; }
figure { margin: 0; }
svg { width: 100%; height: auto; display: block; font-family: "Times New Roman", "Liberation Serif", Times, serif; }
svg .grid { stroke: #ddd; stroke-width: .6; } svg .axis { stroke: #000; stroke-width: .7; }
svg .bg { fill: none; stroke: #888; stroke-width: .8; stroke-dasharray: 3 3; }
svg .tick { font-size: 9px; fill: #000; } svg .label { font-size: 10px; fill: #000; } svg .panel { font-size: 10px; fill: #000; font-weight: 700; }
figcaption { font-size: 10pt; margin-top: 4pt; }
.legend { font-size: 9pt; margin-top: 3pt; }
.legend span { margin-right: 12pt; }
.legend i { display: inline-block; width: 14pt; vertical-align: middle; margin-right: 4pt; }
.legend i.dash { border-top: 1px dashed #888; } .legend i.tickkey { width: 2pt; height: 8pt; }
.refs { margin: 0; padding-left: 1.6em; } .refs li { margin-bottom: 3pt; overflow-wrap: anywhere; }
.mono { font-family: "Courier New", "Liberation Mono", monospace; font-size: 9pt; overflow-wrap: anywhere; }
.appendix th[scope=row] { font-weight: 400; width: 40%; }
.appendix td { height: 16pt; }
.sign { margin-top: 24pt; break-inside: avoid; }
.sign div { margin-top: 22pt; border-top: .5pt solid #000; width: 80mm; padding-top: 2pt; font-size: 10pt; }
.statement { margin-top: 10pt; }
.end { text-align: center; margin-top: 14pt; }
</style></head>
<body><p class="hint">To save as PDF: File → Print → Save as PDF (A4). This line does not print.</p><main class="page">
<div class="kicker"><span>Phase identification report · powder X-ray diffraction</span><span>Report no. ${esc(reportId)}</span></div>
<h1>${title}</h1>
<p class="authors">${labLines.length ? labLines[0] : "Automated analysis with Phasentic"}</p>
${labLines.length > 1 ? `<p class="affil">${labLines.slice(1).join(", ")}</p>` : ""}
<p class="dates">${acq.measured_start ? `Measured ${esc(String(acq.measured_start).slice(0, 10))} · ` : ""}Issued ${esc(dateText)}</p>

<p class="abstract"><b>Abstract.</b> ${abstract}</p>
<p class="keywords"><b>Keywords:</b> powder X-ray diffraction; qualitative phase analysis; ${isPowcod ? "Crystallography Open Database; " : ""}${phases.map((ph) => formula(ph.component.formula)).join("; ") || "phase identification"}.</p>
<p class="notice">This report was produced automatically by the Phasentic software [1] directly from the measurement file, using a fixed, reproducible algorithm (no AI model). No analyst has reviewed it and no Rietveld refinement was performed. It is a screening result until a qualified analyst confirms it and signs Appendix A.</p>

<div class="body">
<h2>1. Introduction</h2>
<p>This report gives a qualitative identification of the crystalline phases in ${itemName} by comparing its powder diffraction pattern with reference patterns [2${isPowcodRelease ? ", 3" : ""}], following the general principles of EN 13925-1 [5]. Phase quantities, lattice parameters, crystallite size, amorphous content and structural refinement are outside its scope.</p>

<h2>2. Experimental</h2>
<h3>2.1. Measurement</h3>
<p>${experimental1}</p>
<h3>2.2. Data processing and phase identification</h3>
<p>${experimental2}</p>
${warnings ? `<p>Quality warnings: ${warnings}</p>` : ""}
<h3>2.3. Decision rule</h3>
<p>The result is classed as <i>supported</i> when the selected phase set explains the pattern and the line positions passed calibration against a certified standard; as <i>tentative</i> when it is the most plausible set without passed calibration or with weak separation from alternatives; and as <i>unresolved</i> when no set explains the pattern well enough (ISO/IEC 17025, §7.8.6 [4]). The rule does not weigh the consequences of a wrong identification; that judgement rests with the authorising analyst.</p>

<h2>3. Results and discussion</h2>
<p>The decision is <i>${decisionText.toLowerCase()}</i>. ${esc(decisionNote)} ${sel ? "The selected phases are listed in Table 1; Fig. 1 compares the observed and calculated patterns." : fallbackRows ? "No phase set was selected; Table 1 lists the best-ranked single-phase candidates." : "No candidate matched a detected peak."}</p>

<div class="span"><table>
  <caption><b>Table 1.</b> ${sel ? "Identified phases" : "Best-ranked single-phase candidates"}. <i>Matched</i>: detected peaks assigned to the phase; <i>unique</i>: peaks no other selected phase explains.</caption>
  <thead><tr><th>No.</th><th>Formula</th><th>Name</th><th>Space group</th><th>Reference entry</th><th class="n">Matched</th><th class="n">Unique</th></tr></thead>
  <tbody>${phaseRows || fallbackRows || `<tr><td colspan="7">No candidate phases.</td></tr>`}</tbody>
</table>
<p class="tnote">Phases are ranked hypotheses, not certainties; no phase fractions are given.${pinned.length ? " ‡ Fixed by the operator." : ""}</p></div>

<div class="span">${phases.length ? fitFigure(r, phases) : measuredFigure(r)}</div>

${discussion.length ? `<p>The following interpretation is an opinion derived from the results, not a measured result (ISO/IEC 17025, §7.8.7 [4]). ${discussion.join(" ")}</p>` : ""}

${phases.length ? `<div class="span">${phaseFigure(r, phases)}</div>` : ""}
${altRows ? `<p>Table 2 lists, for each selected phase, the other materials that fit nearly as well in its place. The fit is the share of the signal left by the other phases that an entry explains when refitted in that phase's place (100&#8201;% would be a perfect fit); materials within 80&#8201;% of the best entry are listed, and further entries of the same material are omitted.</p>
<div class="span"><table>
  <caption><b>Table 2.</b> Alternative entries per phase, best fit first. * Selected entry.</caption>
  <thead><tr><th>No.</th><th>Formula</th><th>Space group</th><th>Reference entry</th><th class="n">Fit</th></tr></thead>
  <tbody>${altRows}</tbody>
</table></div>` : ""}
${alternativesFigure(r) ? `<div class="span">${alternativesFigure(r)}</div>` : ""}

<h3>3.1. Limitations and uncertainty</h3>
<p>The result is qualitative, so no numerical measurement uncertainty is stated. Only phases present in the reference database and allowed by the stated chemistry can be found; minor phases (below a few mass percent) and weakly scattering phases next to strongly scattering ones are often missed. On a sealed test of 200 synthesis products the validated method found the exact phases in 42.5&#8201;% of samples and the right compounds in 52&#8201;%, with accuracy falling sharply for three or more phases.</p>

<h2>4. Conclusions</h2>
<p>${conclusion}</p>

<h2>Data availability</h2>
<p class="first data">${dataFiles.scan ? `The measurement file is archived unchanged as ${esc(dataFiles.scan)}. ` : `The measurement file is ${itemName}. `}${dataFiles.cif ? `The observed, background and calculated profiles of Fig. 1 are given in ${esc(dataFiles.cif)} (powder CIF), and all settings and intermediate results in ${esc(dataFiles.json || "")}.` : "All settings, intermediate results and the profiles of Fig. 1 are in the JSON analysis report with the same analysis identifier."} Checksums and software versions are listed in Appendix A.</p>

<h2>References</h2>
<ol class="refs">${references.map((ref) => `<li>${ref}</li>`).join("")}</ol>
</div>

<div class="appendix">
<h2>Appendix A. Report details and authorisation</h2>
<table>
  <caption>Items required by ISO/IEC 17025, §7.8.2 [4]; blank fields are completed by the laboratory.</caption>
  <tbody>
    ${row("Laboratory (name, address)", lab ? esc(lab).replace(/\n/g, ", ") : blank)}
    ${row("Location of measurement, if different", blank)}
    ${row("Customer (name, contact)", blank)}
    ${row("Item description and condition", blank)}
    ${row("Item identification", acq.sample_id || acq.sample_name ? esc(acq.sample_id || acq.sample_name) : blank)}
    ${row("Date of receipt", blank)}
    ${row("Date of measurement", acq.measured_start ? esc(String(acq.measured_start).slice(0, 10)) : blank)}
    ${row("Sampling", "Not performed by the laboratory; results apply to the item as received.")}
    ${row("External provider", blank)}
    ${row("Method", `Phasentic ${esc(opts.version || "")}${preset ? ", validated settings" : ", custom settings"}`)}
    ${row("Operator choices", pinned.length ? `Phases fixed by the operator: ${pinned.map(codLink).join(", ")}` : "None (fully automatic selection)")}
    ${row("Date of issue", esc(dateText))}
    ${row("Analysis identifier", `<span class="mono">${esc(r.analysis_id)}</span>`)}
    ${row("Measurement file SHA-256", `<span class="mono">${esc(input.sha256)}</span>`)}
    ${row("Software", `<span class="mono">${esc(p.algorithm_version)}; ${esc(r.mixture?.algorithm_version || "")}</span>`)}
    ${row("Reference database SHA-256", `<span class="mono">${esc(p.powcod_database_sha256 || "—")}</span>`)}
  </tbody>
</table>
<div class="sign"><div>Analysed by (name, signature, date)</div><div>Reviewed by (name, signature, date)</div><div>Authorised by (name, function, signature, date)</div></div>
<p class="statement">Results relate only to the item tested, as received. This report shall not be reproduced except in full without the written approval of the issuing laboratory. Until the signature fields are completed it is an unreviewed screening result, not a laboratory finding.</p>
<p class="end">— End of report ${esc(reportId)} —</p>
</div>
</main></body></html>`;
  }

  // Powder CIF (IUCr pdCIF 1.0) with the observed, background and calculated profiles of the
  // selected phase set, for archiving the numeric data behind Figure 1.
  function cif(report, opts = {}) {
    const r = report && report.result ? report.result : report;
    const t = (r.mixture && r.mixture.residual_trace) || {};
    const p = r.provenance || {}, meta = (p.input_source && p.input_source.metadata) || {};
    const rad = meta.source_radiation || {}, input = r.input || {};
    // CIF 1.1 text is ASCII: Greek letters as CIF markup (\\a = alpha), anything else dropped.
    const q = (v) => `'${String(v ?? "?").replace(/'/g, "").replace(/[\r\n]+/g, " ").replace(/[^\x20-\x7e]/g, (c) => ({ "α": "\\a", "β": "\\b", "θ": "\\q", "λ": "\\l" }[c] || ""))}'`;
    const n = (v, d) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "?");
    const phases = phasesOf(r).map((ph) => ph.component);
    const block = String(r.analysis_id || "phasentic").replace(/[^A-Za-z0-9_]/g, "_");
    const x = t.angles_deg || [];
    const lines = [
      `# Powder CIF written by Phasentic ${opts.version || ""}; qualitative screening fit, not a Rietveld refinement.`,
      `# Profiles on the fit grid: ${x.length} of ${input.point_count ?? "?"} measured points. The complete measurement is the original`,
      `# file ${String(input.file_name || "").replace(/[^\x20-\x7e]/g, "?")} (SHA-256 ${input.sha256 || "?"}).`,
      `data_${block}`,
      `_audit_creation_date ${(opts.date || new Date()).toISOString().slice(0, 10)}`,
      `_audit_creation_method ${q(`Phasentic ${opts.version || ""}, analysis ${r.analysis_id}`)}`,
      `_pd_spec_description ${q(input.file_name)}`,
      `_diffrn_radiation_type ${q(r.radiation?.label)}`,
      ...(rad.ka1_angstrom ? [`_diffrn_radiation_wavelength ${n(rad.ka1_angstrom, 6)}`] : []),
      `_pd_meas_2theta_range_min ${n(input.angle_min_deg, 4)}`,
      `_pd_meas_2theta_range_max ${n(input.angle_max_deg, 4)}`,
      `_pd_proc_ls_profile_function ${q("pseudo-Voigt profiles of calculated reference patterns, non-negative least-squares scale factors")}`,
      `_pd_proc_ls_background_function ${q("rolling 20th percentile, smoothed; subtracted before fitting")}`,
      `_refine_ls_weighting_scheme calc`,
      `_refine_ls_weighting_details ${q("trapezoidal 2theta-grid weights")}`,
      "",
      "loop_",
      "_pd_phase_id",
      "_pd_phase_name",
      ...phases.map((c, i) => `${i + 1} ${q(`${c.formula}, ${c.space_group}, ${String(c.reference_id).replace(/^powcod:(\d+)$/, "COD $1").replace(/^powcod:mp-/, "MP mp-")}${realName(c) ? `, ${c.name}` : ""}`)}`),
      "",
      "loop_",
      "_pd_proc_2theta_corrected",
      "_pd_meas_intensity_total",
      "_pd_proc_intensity_bkg_calc",
      "_pd_calc_intensity_total",
      ...x.map((v, i) => `${n(v, 4)} ${n(t.observed_intensities[i], 2)} ${n(t.background_intensities[i], 2)} ${n(t.calculated_intensities[i] + (t.background_intensities[i] || 0), 2)}`),
      "",
    ];
    return lines.join("\n");
  }

  // Figures without "Figure N." numbering, for the web interface.
  const unnumbered = (fn) => (...args) => { numbered = false; try { return fn(...args); } finally { numbered = true; } };
  const api = {
    build,
    cif,
    formula,
    spaceGroup,
    codLink,
    PHASE_COLORS,
    figures: {
      fit: unnumbered((r, view) => (phasesOf(r).length ? fitFigure(r, phasesOf(r), view) : measuredFigure(r))),
      phases: unnumbered((r) => phaseFigure(r, phasesOf(r))),
      alternatives: unnumbered(alternativesFigure),
    },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PhasenticReport = api;
})(typeof window !== "undefined" ? window : globalThis);
