# Security policy

Report suspected vulnerabilities privately through GitHub's
[security advisory form](https://github.com/qaemu/phasentic/security/advisories/new).
Do not put confidential diffraction files or instrument metadata in a public issue.

The web interface listens on 127.0.0.1 only and has no authentication. Do not
expose it to a network without adding authentication and rate limiting first.

Built-in protections, described in [docs/security-and-privacy.md](docs/security-and-privacy.md):
requests are refused unless addressed to the loopback host (DNS rebinding) and,
when a browser sends them, from the page's own origin (cross-site requests);
each analysis runs in a worker process that is stopped when the client
disconnects or after a time limit; calibration results are signed by the
server, so a hand-edited result cannot unlock a `supported` decision.
