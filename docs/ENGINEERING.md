# Engineering Notes

## Standard-library HTTP

`http.server` is not recommended as a public internet server. Here it is deliberate: the repository demonstrates routing, parsing, status semantics and dependency boundaries without delegating them to a framework. A production deployment would put the domain layer behind a hardened ASGI stack and reverse proxy.

## SQLite

SQLite provides transactions, constraints, indexes and real SQL semantics while keeping the demo reproducible. It is a strong fit for a local/single-node planner and a useful migration boundary for PostgreSQL later.

## Deterministic optimization

The scheduler's stable ranking makes failures reproducible and interview discussion concrete. Random or opaque optimization would complicate tests without automatically improving the plan.

## Failure modes considered

Cyclic prerequisites, unknown references, unavailable terms, constraints too tight to make progress, duplicate courses, invalid workload/credits, malformed meetings, unsafe HTML interpolation and reserved iCalendar characters are handled explicitly.

## Testing philosophy

Small algorithmic tests target invariants; existing HTTP tests target end-to-end behaviour. Both styles deliberately overlap at public boundaries.
