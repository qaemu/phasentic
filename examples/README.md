# Examples

`patterns/silicon-cu-ka.xy` is a synthetic sample-pattern smoke fixture.
`patterns/srm-640g-cu-ka.xy` is a synthetic validation scan generated from the
certified NIST SRM 640g manifest with a known offset; it is **not** a certified
measurement and must not be used to estimate instrument uncertainty. The
physical standard certificate and a laboratory scan remain part of the user's
calibration record.

`patterns/silicon-cu-ka.xy` is a synthetic, noise-free smoke fixture for the alpha; `silicon-cu-ka.raw` (two-column ASCII) and `silicon-cu-ka.xrdml` hold the same scan, so all three give the same result. It is suitable for checking the CLI, GUI, and candidate ranking; it is not an instrument calibration standard.
