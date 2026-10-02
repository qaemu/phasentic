# Contributing

Bug reports and suggestions are welcome as
[issues](https://github.com/qaemu/phasentic/issues). For a wrong or doubtful
result, use the *Scientific validation* template and attach the report JSON
(not the raw scan if it is confidential).

Pull requests are welcome when they are small and say clearly what they change:

- State whether analysis results can change. Changes under `src/phasentic/`
  invalidate the frozen code hash; the validated numbers only carry over if
  the development and held-out replays reproduce exactly
  (see [docs/validation.md](docs/validation.md)).
- Update `PARAMETERS.md` and the docs when an assumption or default changes.
- Never commit POW_COD/COD files, user scans, credentials or generated reports.
- If you used an AI tool, say so in the pull request.
