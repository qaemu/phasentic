# Security and privacy

The service binds to `127.0.0.1` by default. Uploads are bounded to 10 MiB, extension-checked, written to generated temporary names, deleted after analysis, and never interpolated into a shell command. Response headers include a restrictive content security policy and clickjacking protection.

Requests whose `Host` is not `127.0.0.1`, `localhost`, `::1` or the address given to `phasentic serve --host` are refused, which defeats DNS rebinding. A request that carries an `Origin` header (every browser POST does) must come from the page's own origin, so another website cannot submit work. Scripts and the CLI send no `Origin` and are unaffected.

Each analysis and calibration runs in its own worker process, one at a time (a second request gets `429`). The worker is killed when the client disconnects and after `PHASENTIC_ANALYSIS_TIMEOUT_SECONDS` (default 300; validated analyses take under a minute), and it exits by itself if the server dies.

A calibration result returned by `/api/v1/calibrate` carries an HMAC signature made with a key that lives only in the running server. `/api/v1/analyze` refuses calibrations it did not sign, so a hand-made `passed` result cannot unlock a `supported` decision. The frontend renders returned values with `textContent`.

No API key or credential is stored in the repository. Do not expose the service beyond localhost without adding authentication, CSRF controls, rate limits, and an explicit data-retention policy.
