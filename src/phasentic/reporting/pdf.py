"""Plain PDF report: only values Phasentic measured, read or calculated. No prose, no blank fields."""

from __future__ import annotations

import io
import math
import re
from datetime import date

from phasentic import __version__

A4 = (8.27, 11.69)  # inches
LEFT, RIGHT, TOP, BOTTOM = 0.07, 0.93, 0.95, 0.05
COLORS = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00"]
LINE = 0.0135  # text line height, figure fraction


def _formula(text: str | None) -> str:
    """'La2 O3' -> 'La$_2$O$_3$' (mathtext subscripts)."""
    raw = re.sub(r"\s+", "", str(text or "—"))
    return re.sub(r"(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)", r"$_{\1}$", raw)


def _ref(reference_id: str | None) -> str:
    return str(reference_id or "—").replace("powcod:", "COD ")


def _num(value, digits: int = 2, unit: str = "") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:.{digits}f}{unit}" if math.isfinite(number) else "—"


class _Pages:
    """Top-down layout on A4 pages; starts a new page when the next block does not fit."""

    def __init__(self, pdf, title: str) -> None:
        self.pdf, self.title, self.fig, self.y, self.page = pdf, title, None, 0.0, 0
        self._new()

    def _new(self) -> None:
        import matplotlib.pyplot as plt

        if self.fig is not None:
            self._close()
        self.fig = plt.figure(figsize=A4)
        self.page += 1
        self.y = TOP

    def _close(self) -> None:
        import matplotlib.pyplot as plt

        self.fig.text(LEFT, 0.025, self.title, fontsize=6.5, color="#5d6673")
        self.fig.text(RIGHT, 0.025, f"page {self.page}", fontsize=6.5, color="#5d6673", ha="right")
        self.pdf.savefig(self.fig)
        plt.close(self.fig)

    def need(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self._new()

    def heading(self, text: str) -> None:
        self.need(LINE * 3)
        self.y -= LINE * 0.6
        self.fig.text(LEFT, self.y, text, fontsize=9.5, weight="bold", va="top")
        self.y -= LINE * 1.3
        self.fig.add_artist(_rule(self.y + LINE * 0.25))

    def text(self, text: str, size: float = 8.0, **kwargs) -> None:
        self.need(LINE)
        self.fig.text(LEFT, self.y, text, fontsize=size, va="top", **kwargs)
        self.y -= LINE * size / 8.0

    def table(self, header: list[str], rows: list[list[str]], widths: list[float], align: list[str] | None = None) -> None:
        """Rows of text; widths are fractions of the text column; align 'l' or 'r' per column."""
        align = align or ["l"] * len(header)
        span = RIGHT - LEFT

        def line(cells: list[str], bold: bool = False, color: str = "#1d2430") -> None:
            self.need(LINE)
            x = LEFT
            for cell, width, side in zip(cells, widths, align):
                self.fig.text(
                    x + (width * span - 0.006 if side == "r" else 0), self.y, cell, fontsize=7.5, va="top",
                    ha="right" if side == "r" else "left", weight="bold" if bold else "normal", color=color,
                )
                x += width * span
            self.y -= LINE

        line(header, bold=True)
        for row in rows:
            line(row)
        self.y -= LINE * 0.4

    def pairs(self, items: list[tuple[str, str]]) -> None:
        """Label/value pairs in two columns; items with an empty value are skipped."""
        items = [(k, v) for k, v in items if v not in (None, "", "—")]
        half = (len(items) + 1) // 2
        left, right = items[:half], items[half:]
        for index in range(half):
            self.need(LINE)
            for column, source in ((0, left), (1, right)):
                if index < len(source):
                    x = LEFT + column * (RIGHT - LEFT) / 2
                    self.fig.text(x, self.y, source[index][0], fontsize=7.5, va="top", color="#5d6673")
                    self.fig.text(x + 0.17, self.y, source[index][1], fontsize=7.5, va="top")
            self.y -= LINE
        self.y -= LINE * 0.4

    def axes(self, height: float):
        labels = 0.04  # room below the axes for tick labels and the axis title
        self.need(height + labels)
        ax = self.fig.add_axes((LEFT + 0.05, self.y - height, RIGHT - LEFT - 0.05, height))
        self.y -= height + labels
        return ax

    def finish(self) -> None:
        self._close()


def _rule(y: float):
    from matplotlib.lines import Line2D

    return Line2D([LEFT, RIGHT], [y, y], linewidth=0.6, color="#1d2430")


def _database(provenance: dict) -> str:
    release = str(provenance.get("powcod_release") or "")
    if not release:
        return str(provenance.get("reference_source") or "—")
    return release if "COD" in release else f"POW_COD {release}"


def _selected(report: dict) -> dict | None:
    mixture = report.get("mixture") or {}
    return next(
        (h for h in mixture.get("hypotheses") or [] if h.get("hypothesis_id") == mixture.get("selected_hypothesis_id")),
        None,
    )


def report_pdf(report: dict) -> bytes:
    """Render the analysis report dictionary as a plain A4 PDF."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    provenance = report.get("provenance") or {}
    settings = provenance.get("settings") or {}
    meta = (provenance.get("input_source") or {}).get("metadata") or {}
    radiation, acquisition = meta.get("source_radiation") or {}, meta.get("acquisition") or {}
    source = report.get("input") or {}
    mixture = report.get("mixture") or {}
    query = mixture.get("query") or {}
    selected = _selected(report)
    components = (selected or {}).get("components") or []
    alternatives = mixture.get("phase_alternatives") or {}
    pinned = set(settings.get("pinned_reference_ids") or [])
    peaks = report.get("peaks") or []
    wavelength = radiation.get("ka1_angstrom")
    width = ((provenance.get("reference_query") or {}).get("candidate_query_stats") or {}).get("profile_width") or {}
    title = f"Phasentic {__version__} · {source.get('file_name', '')} · analysis {report.get('analysis_id', '')}"

    buffer = io.BytesIO()
    with PdfPages(buffer, metadata={"Title": f"Phase identification {source.get('file_name', '')}", "Creator": f"Phasentic {__version__}"}) as pdf:
        out = _Pages(pdf, title)
        out.text(f"Phase identification · {source.get('file_name', '—')}", size=13, weight="bold")
        out.y -= LINE * 0.6
        out.pairs([
            ("Decision", str(report.get("decision", "—"))),
            ("Analysis ID", str(report.get("analysis_id", "—"))),
            ("Report date", date.today().isoformat()),
            ("Database", _database(provenance)),
        ])

        out.heading("Identified phases")
        if components:
            rows = []
            for index, component in enumerate(components, 1):
                entry = alternatives.get(component.get("reference_id")) or {}
                rows.append([
                    f"{index}", _formula(component.get("formula")), str(component.get("space_group") or "—"),
                    _ref(component.get("reference_id")) + (" (fixed)" if component.get("reference_id") in pinned else ""),
                    _num(entry.get("fit_percent"), 1, " %") if entry else "—",
                    str(len(component.get("matched_peak_indices") or [])),
                    str(len(component.get("independent_evidence_peak_indices") or [])),
                ])
            out.table(["No.", "Formula", "Space group", "Reference", "Fit", "Peaks", "Unique"], rows,
                      [0.06, 0.2, 0.17, 0.25, 0.1, 0.11, 0.11], ["l", "l", "l", "l", "r", "r", "r"])
        else:
            out.text("No phase set selected.")

        trace = mixture.get("residual_trace") or {}
        x = trace.get("angles_deg") or []
        if x:
            background = trace.get("background_intensities") or [0.0] * len(x)
            model = [c + b for c, b in zip(trace.get("calculated_intensities") or [], background)]
            observed = trace.get("observed_intensities") or []
            ax = out.axes(0.22)
            ax.plot(x, observed, color="#9aa1ab", linewidth=0.9, label="observed")
            ax.plot(x, model, color="#1d2430", linewidth=0.6, label="calculated")
            ax.plot(x, background, color="#b9bec6", linewidth=0.6, linestyle="--", label="background")
            low = min(observed) if observed else 0.0
            span = (max(observed) - low) if observed else 1.0
            for index, component in enumerate(components):
                y = low - span * (0.06 + 0.05 * index)
                for peak_index in component.get("matched_peak_indices") or []:
                    if 0 <= peak_index < len(peaks):
                        ax.plot([peaks[peak_index]["position_deg"]] * 2, [y - span * 0.015, y + span * 0.015],
                                color=COLORS[index % len(COLORS)], linewidth=1.0)
            for position in (selected or {}).get("unexplained_peak_positions") or []:
                ax.plot(position, low - span * 0.02, marker="v", color="#1d2430", markersize=3, linestyle="none")
            residual = trace.get("residual_intensities") or []
            offset = low - span * (0.12 + 0.05 * len(components))
            ax.plot(x, [offset + value for value in residual], color="#5d6673", linewidth=0.5, label="observed − calculated")
            ax.set_xlim(x[0], x[-1])
            ax.set_xlabel("2θ / °", fontsize=7.5)
            ax.set_ylabel("Intensity / counts", fontsize=7.5)
            ax.tick_params(labelsize=6.5)
            ax.legend(fontsize=6.5, frameon=False, ncol=4, loc="upper right")
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            out.text("Ticks: peaks assigned to each phase (rows in table order); ▼ unexplained peaks.", size=6.5, color="#5d6673")

        listed = [(component, alternatives.get(component.get("reference_id"))) for component in components]
        listed = [(component, entry) for component, entry in listed if entry and entry.get("alternatives")]
        if listed:
            out.heading("Alternatives (fit: 100 % = perfect)")
            rows = []
            for index, (component, entry) in enumerate(listed, 1):
                options = [dict(component, fit_percent=entry.get("fit_percent"), own=True), *entry["alternatives"]]
                for option in sorted(options, key=lambda item: -float(item.get("fit_percent") or 0)):
                    rows.append([
                        str(components.index(component) + 1), _formula(option.get("formula")), str(option.get("space_group") or "—"),
                        _ref(option.get("reference_id")) + (" (selected)" if option.get("own") else ""), _num(option.get("fit_percent"), 1, " %"),
                    ])
            out.table(["Phase", "Formula", "Space group", "Reference", "Fit"], rows, [0.08, 0.25, 0.2, 0.32, 0.15], ["l", "l", "l", "l", "r"])

        hypotheses = [h for h in mixture.get("hypotheses") or [] if isinstance(h.get("selection_score"), (int, float))][:5]
        if len(hypotheses) > 1:
            out.heading("Competing phase sets (selection score, lower is better)")
            out.table(
                ["Phase set", "Score", "Unexplained peaks"],
                [[" + ".join(_formula(c.get("formula")) for c in h.get("components") or []) + ("  (selected)" if h is selected else ""),
                  _num(h.get("selection_score"), 4), str(len(h.get("unexplained_peak_positions") or []))] for h in hypotheses],
                [0.6, 0.2, 0.2], ["l", "r", "r"],
            )

        out.heading("Measurement")
        out.pairs([
            ("Radiation", str((report.get("radiation") or {}).get("label") or "")),
            ("λ Kα1 / Å", _num(wavelength, 6) if wavelength else ""),
            ("λ Kα2 / Å", _num(radiation.get("ka2_angstrom"), 6) if radiation.get("ka2_angstrom") else ""),
            ("2θ range / °", f"{_num(source.get('angle_min_deg'), 3)} – {_num(source.get('angle_max_deg'), 3)}"),
            ("Points", str(source.get("point_count") or "")),
            ("Step / °", _num((float(source.get("angle_max_deg", 0)) - float(source.get("angle_min_deg", 0))) / (int(source.get("point_count") or 2) - 1), 4)),
            ("Measured", str(acquisition.get("measured_start", "")).replace("T", " ")),
            ("Instrument", str(acquisition.get("instrument_id", ""))),
            ("Tube", ", ".join(v for v in (acquisition.get("tube_voltage"), acquisition.get("tube_current")) if v)),
            ("Counting time", str(acquisition.get("counting_time", ""))),
            ("Geometry", ", ".join(v for v in (acquisition.get("sample_mode"), acquisition.get("goniometer_radius")) if v)),
            ("Sample ID", str(acquisition.get("sample_id", ""))[:28]),
        ])

        quality = report.get("quality") or {}
        correction = provenance.get("coordinate_correction") or {}
        out.heading("Processing")
        out.pairs([
            ("Peaks detected", str(len(peaks))),
            ("Signal/noise", _num(quality.get("signal_to_noise"), 0)),
            ("Peak S/N threshold", _num(settings.get("peak_min_snr"), 0)),
            ("Background window / °", _num(settings.get("background_window_deg"), 1)),
            ("Displacement / °", _num(correction.get("sample_displacement_deg"), 3)),
            ("Calibration", str(quality.get("calibration_status") or "")),
            ("FWHM a / °", _num(width.get("a_deg"), 4) if width.get("status") == "estimated" else _num(settings.get("profile_width_deg"), 3)),
            ("FWHM b / °", _num(width.get("b_deg"), 4) if width.get("status") == "estimated" else ""),
            ("Pseudo-Voigt η", _num(settings.get("profile_eta"), 2)),
            ("Tolerance / °", _num(settings.get("peak_tolerance_deg"), 2)),
            ("Elements", ", ".join(settings.get("allowed_elements") or [])),
            ("Max. phases", str(settings.get("max_phases", ""))),
            ("Fits tried", str(query.get("fit_attempts", ""))),
            ("Candidates fitted", str(query.get("candidate_pool_size", ""))),
            ("Unexplained peaks", str(len((selected or {}).get("unexplained_peak_positions") or []))),
            ("Missing lines", str(len((selected or {}).get("missing_expected_lines") or []))),
        ])

        if peaks:
            out.heading("Detected peaks")
            owner = {}
            for index, component in enumerate(components, 1):
                for peak_index in component.get("matched_peak_indices") or []:
                    owner.setdefault(peak_index, []).append(str(index))
            rows = []
            for index, peak in sorted(enumerate(peaks), key=lambda item: float(item[1]["position_deg"])):
                angle = float(peak["position_deg"])
                d = wavelength / (2 * math.sin(math.radians(angle / 2))) if wavelength else None
                rows.append([str(len(rows) + 1), _num(angle, 3), _num(d, 4) if d else "—", _num(peak.get("intensity"), 0),
                             _num(peak.get("width_deg"), 3), ", ".join(owner.get(index, [])) or "—"])
            out.table(["No.", "2θ / °", "d / Å", "Intensity / counts", "Width / °", "Phase"], rows,
                      [0.08, 0.16, 0.16, 0.22, 0.16, 0.22], ["l", "r", "r", "r", "r", "l"])

        out.heading("Traceability")
        out.text(f"Input SHA-256  {source.get('sha256', '—')}", size=7, family="monospace")
        out.text(f"Database SHA-256  {provenance.get('powcod_database_sha256') or '—'}", size=7, family="monospace")
        out.text(f"Engine  {provenance.get('algorithm_version', '—')}", size=7, family="monospace")
        out.text(f"Mixture search  {mixture.get('algorithm_version', '—')}", size=7, family="monospace")
        out.finish()
    return buffer.getvalue()


if __name__ == "__main__":  # self-check: python -m phasentic.reporting.pdf
    sample = {
        "analysis_id": "x", "decision": "tentative", "input": {"file_name": "s.xy", "point_count": 3, "angle_min_deg": 10, "angle_max_deg": 12},
        "radiation": {"label": "Cu Kα"}, "peaks": [{"position_deg": 11.0, "intensity": 50, "width_deg": 0.1}],
        "provenance": {"settings": {}, "input_source": {"metadata": {"source_radiation": {"ka1_angstrom": 1.5406}}}},
        "mixture": {"selected_hypothesis_id": "h", "hypotheses": [{"hypothesis_id": "h", "selection_score": 0.1, "components": [
            {"reference_id": "powcod:1", "formula": "La2 O3", "space_group": "P-3m1", "matched_peak_indices": [0]}]}],
            "residual_trace": {"angles_deg": [10, 11, 12], "observed_intensities": [1, 50, 1], "calculated_intensities": [0, 45, 0],
                               "background_intensities": [1, 1, 1], "residual_intensities": [0, 4, 0]}},
    }
    data = report_pdf(sample)
    assert data.startswith(b"%PDF") and len(data) > 1000
    print("ok")
