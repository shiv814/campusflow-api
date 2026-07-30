# CampusFlow API

CampusFlow is a dependency-free Python REST service for storing courses and building term plans. It uses SQLite for persistence and the standard-library HTTP server for a lightweight deployment footprint.

## Highlights

- Course catalogue with prerequisite metadata
- Term plans with credit targets and ordered course selections
- JSON endpoints with validation and clear HTTP status codes
- SQLite foreign-key constraints and automated tests
- GitHub Actions workflow for Python 3.10-3.12

## Run

```bash
python -m campusflow.api --port 8080
```

Example:

```bash
curl -X POST http://127.0.0.1:8080/courses \
  -H "Content-Type: application/json" \
  -d '{"code":"ENGG2410","title":"Digital Systems","credits":0.5,"term":"Fall"}'
```

## Test

```bash
python -m pytest
```

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service status |
| GET | `/courses?term=Fall` | List or filter courses |
| POST | `/courses` | Add a course |
| POST | `/plans` | Create a term plan |
| GET | `/plans/{id}` | Retrieve plan totals |
| POST | `/plans/{id}/courses` | Add a course to a plan |
