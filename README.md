# CampusFlow API

CampusFlow is a dependency-free Python academic-planning platform built on SQLite and the standard-library HTTP server. It now covers the full workflow from maintaining a searchable course catalogue to validating a student's plan, detecting timetable conflicts, measuring progress, generating recommendations, and exporting records.

## What it demonstrates

- Layered design: HTTP transport, domain service, and persistence are separated
- Backward-compatible SQLite schema upgrades for databases created by version 1
- Resource validation, conflict handling, foreign keys, indexes, and transactions
- Search, filtering, pagination, partial updates, deletion, analytics, and CSV export
- Prerequisite-order and meeting-time conflict detection
- CORS support and request IDs for API observability
- A reusable service class that can be embedded without running the web server

## Feature tour

### Course catalogue

Courses include code, title, credits, term, department, description, capacity, delivery mode, prerequisite codes, active status, and zero or more scheduled meetings. The catalogue supports full-text-like search across code, title, and description plus term, department, credit, active-status, limit, and offset filters.

### Academic plans

Plans track a student, target credits, starting term, lifecycle status, ordered courses, completion state, grades, notes, total credits, completed credits, remaining credits, and progress percentage.

### Plan intelligence

`GET /plans/{id}/validate` identifies:

- missing prerequisites based on course order and completion state
- overlapping meeting times
- credit overload relative to the plan target

`GET /plans/{id}/recommendations` returns eligible courses that are not already selected and scores them by target-credit fit, term fit, and prerequisite progression.

## Quick start

```bash
python -m campusflow.seed --database campusflow.db
python -m campusflow.api --host 127.0.0.1 --port 8080 --database campusflow.db
```

Create a course:

```bash
curl -X POST http://127.0.0.1:8080/courses \
  -H "Content-Type: application/json" \
  -d '{
    "code":"ENGG2410",
    "title":"Digital Systems Design",
    "credits":0.5,
    "term":"Fall",
    "department":"Engineering",
    "delivery":"Hybrid",
    "meetings":[{"day":"Tue","start_minute":600,"end_minute":680,"location":"THRN 1200"}]
  }'
```

Build and validate a plan:

```bash
curl -X POST http://127.0.0.1:8080/plans \
  -H "Content-Type: application/json" \
  -d '{"name":"Fall Plan","target_credits":2.5,"student_id":"1001","start_term":"Fall"}'

curl -X POST http://127.0.0.1:8080/plans/1/courses \
  -H "Content-Type: application/json" \
  -d '{"code":"ENGG2410","notes":"Core requirement"}'

curl http://127.0.0.1:8080/plans/1/validate
curl http://127.0.0.1:8080/plans/1/recommendations?term=Fall
curl http://127.0.0.1:8080/plans/1/export.csv
```

## API reference

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Liveness and version |
| GET/POST | `/courses` | Search or create courses |
| GET/PATCH/DELETE | `/courses/{code}` | Read, update, or remove a course |
| GET/POST | `/plans` | List or create plans |
| GET/PATCH/DELETE | `/plans/{id}` | Read, update, or remove a plan |
| POST | `/plans/{id}/courses` | Append a course to a plan |
| PATCH/DELETE | `/plans/{id}/courses/{code}` | Update completion metadata or remove a course |
| GET | `/plans/{id}/validate` | Run academic and schedule checks |
| GET | `/plans/{id}/recommendations` | Find eligible next courses |
| GET | `/plans/{id}/export.csv` | Download the plan as CSV |
| GET | `/analytics` | Catalogue and plan summary metrics |

## Test

```bash
python -m pip install pytest
python -m pytest
```

The suite exercises domain validation, catalogue filtering, partial updates, progression analytics, prerequisite checks, schedule conflicts, deletion safeguards, recommendations, CSV export, structured HTTP errors, and an end-to-end API workflow.

## Architecture

```text
campusflow/
├── api.py       # HTTP routing, JSON/CSV responses, error mapping, CORS
├── db.py        # schema, migrations, domain rules, queries, analytics
└── seed.py      # repeatable sample-data loader
```

## Design choices

The service uses only the Python standard library at runtime. This keeps deployment simple and makes the implementation details visible, while tests still use `pytest` for readability. SQLite provides durable local storage and transaction semantics without requiring an external database server.
