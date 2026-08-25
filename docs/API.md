# CampusFlow API Conventions

The API is intentionally dependency-free. JSON endpoints use `application/json`; plan export uses CSV.

## Errors

Domain validation failures map to 400-class responses. Resource conflicts are distinct from missing resources. Error bodies are structured JSON rather than raw tracebacks.

## Request IDs

Every request receives an identifier so a client-visible failure can be correlated with server-side logs. Clients should preserve that identifier when reporting issues.

## Filtering

`GET /courses` supports term, department, text search, active state, credit bounds, limit and offset. Invalid query values should fail visibly rather than silently changing meaning.

## Validation and recommendations

`GET /plans/{id}/validate` reports prerequisite-order issues, timetable conflicts and overload conditions. `GET /plans/{id}/recommendations` returns deterministic eligible next courses for the current database state.

## Export

`GET /plans/{id}/export.csv` emits a portable plan representation. The v3 Python layer additionally supports iCalendar and responsive HTML exports.
