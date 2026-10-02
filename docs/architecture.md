# Architecture

The alpha is a Python package with a thin FastAPI boundary and a static browser client. Domain contracts sit below adapters, so importers, the optional GSAS-II vendor-import boundary, and the POW_COD sidecar can be swapped without changing report semantics. POW_COD preparation is an offline job; the runtime opens only verified read-only assets. The matcher queries indexed d-spacing ranges before loading candidate structures, consumes d-spacing reference lines, and applies the selected radiation in one auditable place.

The API returns an envelope with `success` and `data`. The report itself is immutable after construction.
