# File formats

`.xy` accepts UTF-8 two-column angle/intensity text with blank lines and `#`, `!`, `;`, or `//` comments. Commas are accepted as separators.

`.xrdml` reads a namespaced XML scan with `<positions>` plus `<startPosition>/<endPosition>` or explicit positions, and an `<intensities>` series.

`.raw` accepts two-column ASCII exports directly. Binary Bruker RAW v2/v3/v4 files are detected by the GSAS-II adapter mapping and rejected with a named reason when GSAS-II is absent. They are never parsed by byte guessing in the built-in importer.

The optional GSAS-II mapping registry covers Bruker RAW v2/v3/v4, PANalytical XRDML, and Rigaku RAS/RASX according to the GSAS-II importer documentation. The alpha includes real Bruker RAW4 and PANalytical XRDML fixtures in `tests/fixtures/vendor/`, with hashes and upstream commit recorded in `tests/fixtures/vendor/manifest.json`.

All inputs must contain at least three finite, non-negative intensity pairs with strictly increasing angles and are limited to 10 MiB by the HTTP boundary.
