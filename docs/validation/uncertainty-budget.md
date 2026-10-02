# Instrument-specific uncertainty budget

The budget belongs to a named instrument configuration. It is not a universal
constant and it does not convert a candidate score into a probability.

## Measurands

Start with 2θ peak position, d-spacing, calibration zero shift, and wavelength
scale. Add profile width only when a line-shape standard and a validated profile
model are available.

## Components

Estimate Type A components from repeated standard scans: peak-fit variation,
same-mount repeatability, remounting, day-to-day drift, and operator variation.
Record Type B components from the instrument and reference material: certified
lattice parameter, wavelength, specimen displacement, goniometer geometry,
encoder resolution, temperature, Kα treatment, background model, and parser
rounding.

Document correlations instead of adding every component as if it were
independent. Combine the components under the GUM model; use Monte Carlo
propagation when the angle-to-d-spacing transform or the fit model is strongly
nonlinear. Record the coverage factor, coverage probability, valid angle range,
and the data used to estimate every component.

## Decision use

The phase gate should compare observed and reference positions against the
configuration-specific combined uncertainty and the validated false-support
policy. A missing or incomplete budget keeps the result at `tentative` or
`unresolved`; it must not silently widen the tolerance.
