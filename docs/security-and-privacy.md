# Security and privacy

The service binds to `127.0.0.1` by default. Uploads are bounded to 10 MiB, extension-checked, written to generated temporary names, deleted after analysis, and never interpolated into a shell command. Response headers include a restrictive content security policy and clickjacking protection. The frontend renders returned values with `textContent`.

No API key or credential is stored in the repository. Do not expose the service beyond localhost without adding authentication, CSRF controls, rate limits, and an explicit data-retention policy.
