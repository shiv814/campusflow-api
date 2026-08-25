# Contributing

1. Create a feature branch from `main`.
2. Keep domain logic out of the HTTP transport when possible.
3. Add deterministic tests for every new planning rule or algorithm.
4. Run `python -m compileall campusflow` and `python -m pytest -q`.
5. Update README/docs when public behaviour changes.

Code targets Python 3.10+ and avoids new runtime dependencies unless the portability trade-off is justified.
