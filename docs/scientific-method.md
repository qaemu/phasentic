# Scientific method and IUCr alignment

The alpha follows the practical order used in powder diffraction work: preserve primary data, record scan metadata, verify the coordinate and radiation, inspect background and peaks, compare against crystallographic references, and separate screening from refinement.

The report schema is designed to grow toward powder CIF-compatible provenance: measurement range and increment, selected radiation, observed peaks, background diagnostics, candidate references, and calculated evidence. The current JSON report is not a CIF and should not be presented as one.

Position matching uses Bragg’s law and d spacings. Intensity matching is deliberately relative and diagnostic because absorption, texture, multiplicity, profile shape, and instrument geometry affect measured intensities. A complete identification workflow must therefore include whole-pattern residuals and uncertainty, not only peak lists.

Before a publication claim, validate line position and profile using a certified standard; record instrument configuration and sample preparation; inspect preferred orientation, peak overlap, amorphous content, and impurity candidates; and run a constrained refinement with an auditable engine such as GSAS-II.

## Mixture screening boundary

The explicit `joint_no_requery` and `full_mixture` modes are deterministic
development screens layered on
the single-phase matcher. It renders each shortlisted reference on the full
measured grid with a fixed area-normalized Gaussian profile, fits all selected
profiles jointly with nonnegative least squares after the existing fixed
background correction, and keeps the signed residual. Candidate additions
must contribute independent observed-line evidence and pass a relative
objective-improvement gate. Duplicate groups are counted once, while retained
alternatives remain visible as competing hypotheses.

The fitted values are arbitrary profile amplitudes. They are not mass,
volume, mole, or weight fractions and are not converted into composition
claims. A residual improvement alone cannot promote a result to scientific
support; calibration and quality gates still apply, and overlapping or
missing-library cases remain tentative or unresolved.
