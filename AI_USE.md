# AI use

Phasentic's code and documentation were written with **Claude Code**,
Anthropic's coding agent, under the direction of the maintainer (qaemu).

The maintainer chose the problem and the scientific approach, set the
validation protocol, declared the accuracy targets before tuning, reviewed the
results, and is responsible for every claim in this repository.

## Why the results can be trusted

The claims rest on checks that would catch errors regardless of who wrote the
code:

- the accuracy target was declared in writing before any tuning
  (`validation/wp5-precursor-target-v1.json`);
- tuning used only 100 development scans; the 200 held-out scans were sealed
  and run once (`validation/outcome-v2.json`);
- settings and code were frozen by hash, and the runner refuses to evaluate a
  held-out cohort with code that differs from the frozen hash;
- every later code change had to reproduce all 100 development and 200
  held-out results exactly (`validation/equivalence-*.json`);
- the known failure modes are documented (`docs/validation.md`).

## No AI at run time

Phasentic does not call any AI model when it analyses a scan. The analysis is
deterministic: the same input and settings give the same report.
