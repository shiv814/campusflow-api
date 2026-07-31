from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class ValidationError(ValueError):
    """Raised when a request violates a CampusFlow domain rule."""


class ConflictError(RuntimeError):
    """Raised when a resource cannot be changed because it is in use."""


class CoursePlanner:
    """SQLite-backed course catalogue and academic-plan service.

    The class intentionally keeps all domain rules outside the HTTP layer so it can
    be reused by scripts, tests, desktop applications, or a different web stack.
    """

    VALID_TERMS = {"Fall", "Winter", "Summer", "Any"}
    VALID_DELIVERY = {"In Person", "Online", "Hybrid"}
    VALID_PLAN_STATUS = {"Draft", "Active", "Completed", "Archived"}

    def __init__(self, database: str | Path = "campusflow.db") -> None:
        self.database = str(database)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, definition: str) -> None:
        name = definition.split()[0]
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    code TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    credits REAL NOT NULL CHECK(credits > 0),
                    term TEXT NOT NULL,
                    prerequisites TEXT NOT NULL DEFAULT '',
                    department TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    capacity INTEGER NOT NULL DEFAULT 0 CHECK(capacity >= 0),
                    delivery TEXT NOT NULL DEFAULT 'In Person',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS course_prerequisites (
                    course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
                    prerequisite_code TEXT NOT NULL,
                    PRIMARY KEY (course_code, prerequisite_code),
                    CHECK(course_code <> prerequisite_code)
                );
                CREATE TABLE IF NOT EXISTS course_meetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
                    day TEXT NOT NULL,
                    start_minute INTEGER NOT NULL CHECK(start_minute >= 0 AND start_minute < 1440),
                    end_minute INTEGER NOT NULL CHECK(end_minute > start_minute AND end_minute <= 1440),
                    location TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    target_credits REAL NOT NULL CHECK(target_credits > 0),
                    student_id TEXT NOT NULL DEFAULT '',
                    start_term TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Draft',
                    created_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS plan_courses (
                    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                    course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    grade REAL,
                    notes TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (plan_id, course_code)
                );
                CREATE INDEX IF NOT EXISTS idx_courses_term ON courses(term);
                CREATE INDEX IF NOT EXISTS idx_courses_department ON courses(department);
                CREATE INDEX IF NOT EXISTS idx_plan_courses_position ON plan_courses(plan_id, position);
                """
            )
            # Upgrade databases created by the original portfolio version.
            self._ensure_column(connection, "courses", "department TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "courses", "description TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "courses", "capacity INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "courses", "delivery TEXT NOT NULL DEFAULT 'In Person'")
            self._ensure_column(connection, "courses", "active INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, "courses", "created_at TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "plans", "student_id TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "plans", "start_term TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "plans", "status TEXT NOT NULL DEFAULT 'Draft'")
            self._ensure_column(connection, "plans", "created_at TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "plan_courses", "completed INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "plan_courses", "grade REAL")
            self._ensure_column(connection, "plan_courses", "notes TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _clean_code(value: str) -> str:
        code = value.strip().upper().replace(" ", "")
        if len(code) < 4 or len(code) > 12 or not any(char.isalpha() for char in code) or not any(char.isdigit() for char in code):
            raise ValidationError("course code must contain letters and numbers and be 4-12 characters")
        if not code.isalnum():
            raise ValidationError("course code may contain only letters and numbers")
        return code

    @staticmethod
    def _clean_text(value: str, field: str, *, required: bool = True, maximum: int = 500) -> str:
        cleaned = " ".join(value.strip().split())
        if required and not cleaned:
            raise ValidationError(f"{field} is required")
        if len(cleaned) > maximum:
            raise ValidationError(f"{field} must be at most {maximum} characters")
        return cleaned

    @classmethod
    def _clean_term(cls, value: str, *, allow_blank: bool = False) -> str:
        cleaned = value.strip().title()
        if allow_blank and not cleaned:
            return ""
        if cleaned not in cls.VALID_TERMS:
            raise ValidationError(f"term must be one of: {', '.join(sorted(cls.VALID_TERMS))}")
        return cleaned

    @classmethod
    def _clean_delivery(cls, value: str) -> str:
        aliases = {"in-person": "In Person", "in person": "In Person", "online": "Online", "hybrid": "Hybrid"}
        cleaned = aliases.get(value.strip().lower(), value.strip().title())
        if cleaned not in cls.VALID_DELIVERY:
            raise ValidationError(f"delivery must be one of: {', '.join(sorted(cls.VALID_DELIVERY))}")
        return cleaned

    @staticmethod
    def _parse_meetings(meetings: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
        for meeting in meetings or []:
            day = str(meeting.get("day", "")).strip().title()[:3]
            start = int(meeting.get("start_minute", -1))
            end = int(meeting.get("end_minute", -1))
            location = " ".join(str(meeting.get("location", "")).strip().split())
            if day not in valid_days:
                raise ValidationError("meeting day must be Mon-Sun")
            if not 0 <= start < end <= 1440:
                raise ValidationError("meeting times must satisfy 0 <= start < end <= 1440")
            parsed.append({"day": day, "start_minute": start, "end_minute": end, "location": location})
        return parsed

    def add_course(
        self,
        code: str,
        title: str,
        credits: float,
        term: str,
        prerequisites: list[str] | None = None,
        *,
        department: str = "",
        description: str = "",
        capacity: int = 0,
        delivery: str = "In Person",
        meetings: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        clean_code = self._clean_code(code)
        clean_title = self._clean_text(title, "title", maximum=120)
        clean_term = self._clean_term(term)
        clean_department = self._clean_text(department, "department", required=False, maximum=80)
        clean_description = self._clean_text(description, "description", required=False, maximum=1000)
        clean_delivery = self._clean_delivery(delivery)
        if not 0 < float(credits) <= 3.0:
            raise ValidationError("credits must be greater than 0 and at most 3")
        if int(capacity) < 0:
            raise ValidationError("capacity cannot be negative")
        prereq_codes = list(dict.fromkeys(self._clean_code(item) for item in (prerequisites or [])))
        if clean_code in prereq_codes:
            raise ValidationError("a course cannot be its own prerequisite")
        parsed_meetings = self._parse_meetings(meetings)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO courses(
                       code, title, credits, term, prerequisites, department, description,
                       capacity, delivery, active, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    clean_code,
                    clean_title,
                    float(credits),
                    clean_term,
                    ",".join(prereq_codes),
                    clean_department,
                    clean_description,
                    int(capacity),
                    clean_delivery,
                    self._utc_now(),
                ),
            )
            connection.executemany(
                "INSERT INTO course_prerequisites(course_code, prerequisite_code) VALUES (?, ?)",
                [(clean_code, prerequisite) for prerequisite in prereq_codes],
            )
            connection.executemany(
                """INSERT INTO course_meetings(course_code, day, start_minute, end_minute, location)
                   VALUES (?, ?, ?, ?, ?)""",
                [(clean_code, m["day"], m["start_minute"], m["end_minute"], m["location"]) for m in parsed_meetings],
            )
        return self.get_course(clean_code)

    def update_course(self, code: str, **changes: Any) -> dict[str, Any]:
        current = self.get_course(code)
        allowed = {"title", "credits", "term", "department", "description", "capacity", "delivery", "active", "prerequisites", "meetings"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"unsupported course fields: {', '.join(sorted(unknown))}")
        payload = {**current, **changes}
        title = self._clean_text(str(payload["title"]), "title", maximum=120)
        credits = float(payload["credits"])
        if not 0 < credits <= 3.0:
            raise ValidationError("credits must be greater than 0 and at most 3")
        term = self._clean_term(str(payload["term"]))
        department = self._clean_text(str(payload.get("department", "")), "department", required=False, maximum=80)
        description = self._clean_text(str(payload.get("description", "")), "description", required=False, maximum=1000)
        capacity = int(payload.get("capacity", 0))
        if capacity < 0:
            raise ValidationError("capacity cannot be negative")
        delivery = self._clean_delivery(str(payload.get("delivery", "In Person")))
        active = 1 if bool(payload.get("active", True)) else 0
        prerequisites = list(dict.fromkeys(self._clean_code(item) for item in payload.get("prerequisites", [])))
        clean_code = self._clean_code(code)
        if clean_code in prerequisites:
            raise ValidationError("a course cannot be its own prerequisite")
        meetings = self._parse_meetings(payload.get("meetings", []))
        with self._connect() as connection:
            connection.execute(
                """UPDATE courses SET title=?, credits=?, term=?, prerequisites=?, department=?,
                   description=?, capacity=?, delivery=?, active=? WHERE code=?""",
                (title, credits, term, ",".join(prerequisites), department, description, capacity, delivery, active, clean_code),
            )
            connection.execute("DELETE FROM course_prerequisites WHERE course_code=?", (clean_code,))
            connection.executemany(
                "INSERT INTO course_prerequisites(course_code, prerequisite_code) VALUES (?, ?)",
                [(clean_code, prerequisite) for prerequisite in prerequisites],
            )
            connection.execute("DELETE FROM course_meetings WHERE course_code=?", (clean_code,))
            connection.executemany(
                "INSERT INTO course_meetings(course_code, day, start_minute, end_minute, location) VALUES (?, ?, ?, ?, ?)",
                [(clean_code, m["day"], m["start_minute"], m["end_minute"], m["location"]) for m in meetings],
            )
        return self.get_course(clean_code)

    def delete_course(self, code: str) -> None:
        clean_code = self._clean_code(code)
        with self._connect() as connection:
            used = connection.execute("SELECT COUNT(*) FROM plan_courses WHERE course_code=?", (clean_code,)).fetchone()[0]
            if used:
                raise ConflictError("course is used by one or more plans")
            cursor = connection.execute("DELETE FROM courses WHERE code=?", (clean_code,))
            if cursor.rowcount == 0:
                raise KeyError(code)

    def get_course(self, code: str) -> dict[str, Any]:
        clean_code = self._clean_code(code)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM courses WHERE code = ?", (clean_code,)).fetchone()
            if row is None:
                raise KeyError(code)
            prereq_rows = connection.execute(
                "SELECT prerequisite_code FROM course_prerequisites WHERE course_code=? ORDER BY prerequisite_code",
                (clean_code,),
            ).fetchall()
            meeting_rows = connection.execute(
                "SELECT day, start_minute, end_minute, location FROM course_meetings WHERE course_code=? ORDER BY id",
                (clean_code,),
            ).fetchall()
        result = dict(row)
        result["active"] = bool(result["active"])
        normalized = [item[0] for item in prereq_rows]
        if not normalized and result.get("prerequisites"):
            normalized = [item for item in str(result["prerequisites"]).split(",") if item]
        result["prerequisites"] = normalized
        result["meetings"] = [dict(item) for item in meeting_rows]
        return result

    def list_courses(
        self,
        term: str | None = None,
        *,
        department: str | None = None,
        query: str | None = None,
        active: bool | None = True,
        min_credits: float | None = None,
        max_credits: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        parameters: list[Any] = []
        if term:
            where.append("lower(term) = lower(?)")
            parameters.append(term.strip())
        if department:
            where.append("lower(department) = lower(?)")
            parameters.append(department.strip())
        if query:
            where.append("(lower(code) LIKE ? OR lower(title) LIKE ? OR lower(description) LIKE ?)")
            needle = f"%{query.strip().lower()}%"
            parameters.extend([needle, needle, needle])
        if active is not None:
            where.append("active = ?")
            parameters.append(1 if active else 0)
        if min_credits is not None:
            where.append("credits >= ?")
            parameters.append(float(min_credits))
        if max_credits is not None:
            where.append("credits <= ?")
            parameters.append(float(max_credits))
        safe_limit = min(max(int(limit), 1), 500)
        safe_offset = max(int(offset), 0)
        sql = "SELECT code FROM courses"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY code LIMIT ? OFFSET ?"
        parameters.extend([safe_limit, safe_offset])
        with self._connect() as connection:
            codes = [row[0] for row in connection.execute(sql, parameters).fetchall()]
        return [self.get_course(code) for code in codes]

    def create_plan(
        self,
        name: str,
        target_credits: float = 5.0,
        *,
        student_id: str = "",
        start_term: str = "",
        status: str = "Draft",
    ) -> dict[str, Any]:
        clean_name = self._clean_text(name, "plan name", maximum=120)
        if float(target_credits) <= 0:
            raise ValidationError("target credits must be positive")
        clean_student = self._clean_text(student_id, "student id", required=False, maximum=80)
        clean_start = self._clean_term(start_term, allow_blank=True)
        clean_status = status.strip().title()
        if clean_status not in self.VALID_PLAN_STATUS:
            raise ValidationError(f"status must be one of: {', '.join(sorted(self.VALID_PLAN_STATUS))}")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO plans(name, target_credits, student_id, start_term, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (clean_name, float(target_credits), clean_student, clean_start, clean_status, self._utc_now()),
            )
            plan_id = int(cursor.lastrowid)
        return self.get_plan(plan_id)

    def list_plans(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id FROM plans"
        params: list[Any] = []
        if status:
            sql += " WHERE lower(status)=lower(?)"
            params.append(status.strip())
        sql += " ORDER BY id DESC"
        with self._connect() as connection:
            ids = [int(row[0]) for row in connection.execute(sql, params).fetchall()]
        return [self.get_plan(plan_id) for plan_id in ids]

    def update_plan(self, plan_id: int, **changes: Any) -> dict[str, Any]:
        current = self.get_plan(plan_id)
        allowed = {"name", "target_credits", "student_id", "start_term", "status"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"unsupported plan fields: {', '.join(sorted(unknown))}")
        payload = {**current, **changes}
        name = self._clean_text(str(payload["name"]), "plan name", maximum=120)
        target = float(payload["target_credits"])
        if target <= 0:
            raise ValidationError("target credits must be positive")
        student = self._clean_text(str(payload.get("student_id", "")), "student id", required=False, maximum=80)
        start = self._clean_term(str(payload.get("start_term", "")), allow_blank=True)
        status = str(payload.get("status", "Draft")).strip().title()
        if status not in self.VALID_PLAN_STATUS:
            raise ValidationError(f"status must be one of: {', '.join(sorted(self.VALID_PLAN_STATUS))}")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE plans SET name=?, target_credits=?, student_id=?, start_term=?, status=? WHERE id=?",
                (name, target, student, start, status, int(plan_id)),
            )
            if cursor.rowcount == 0:
                raise KeyError(plan_id)
        return self.get_plan(plan_id)

    def delete_plan(self, plan_id: int) -> None:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM plans WHERE id=?", (int(plan_id),))
            if cursor.rowcount == 0:
                raise KeyError(plan_id)

    def add_course_to_plan(self, plan_id: int, course_code: str, *, completed: bool = False, grade: float | None = None, notes: str = "") -> dict[str, Any]:
        code = self._clean_code(course_code)
        if grade is not None and not 0 <= float(grade) <= 100:
            raise ValidationError("grade must be between 0 and 100")
        clean_notes = self._clean_text(notes, "notes", required=False, maximum=500)
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM plans WHERE id=?", (int(plan_id),)).fetchone() is None:
                raise KeyError(plan_id)
            if connection.execute("SELECT 1 FROM courses WHERE code=? AND active=1", (code,)).fetchone() is None:
                raise KeyError(code)
            position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM plan_courses WHERE plan_id=?",
                (int(plan_id),),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO plan_courses(plan_id, course_code, position, completed, grade, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (int(plan_id), code, position, 1 if completed else 0, grade, clean_notes),
            )
        return self.get_plan(plan_id)

    def update_plan_course(self, plan_id: int, course_code: str, **changes: Any) -> dict[str, Any]:
        allowed = {"completed", "grade", "notes", "position"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"unsupported plan-course fields: {', '.join(sorted(unknown))}")
        code = self._clean_code(course_code)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT completed, grade, notes, position FROM plan_courses WHERE plan_id=? AND course_code=?",
                (int(plan_id), code),
            ).fetchone()
            if row is None:
                raise KeyError(course_code)
            completed = 1 if bool(changes.get("completed", row["completed"])) else 0
            grade = changes.get("grade", row["grade"])
            if grade is not None and not 0 <= float(grade) <= 100:
                raise ValidationError("grade must be between 0 and 100")
            notes = self._clean_text(str(changes.get("notes", row["notes"])), "notes", required=False, maximum=500)
            position = int(changes.get("position", row["position"]))
            if position <= 0:
                raise ValidationError("position must be positive")
            connection.execute(
                """UPDATE plan_courses SET completed=?, grade=?, notes=?, position=?
                   WHERE plan_id=? AND course_code=?""",
                (completed, grade, notes, position, int(plan_id), code),
            )
            self._normalize_positions(connection, int(plan_id))
        return self.get_plan(plan_id)

    @staticmethod
    def _normalize_positions(connection: sqlite3.Connection, plan_id: int) -> None:
        rows = connection.execute(
            "SELECT course_code FROM plan_courses WHERE plan_id=? ORDER BY position, course_code",
            (plan_id,),
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE plan_courses SET position=? WHERE plan_id=? AND course_code=?",
                (index, plan_id, row[0]),
            )

    def remove_course_from_plan(self, plan_id: int, course_code: str) -> dict[str, Any]:
        code = self._clean_code(course_code)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM plan_courses WHERE plan_id=? AND course_code=?",
                (int(plan_id), code),
            )
            if cursor.rowcount == 0:
                raise KeyError(course_code)
            self._normalize_positions(connection, int(plan_id))
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            plan = connection.execute("SELECT * FROM plans WHERE id=?", (int(plan_id),)).fetchone()
            if plan is None:
                raise KeyError(plan_id)
            rows = connection.execute(
                """SELECT pc.position, pc.completed, pc.grade, pc.notes, c.code
                   FROM plan_courses pc JOIN courses c ON c.code=pc.course_code
                   WHERE pc.plan_id=? ORDER BY pc.position, c.code""",
                (int(plan_id),),
            ).fetchall()
        courses: list[dict[str, Any]] = []
        for row in rows:
            item = self.get_course(row["code"])
            item.update(
                position=int(row["position"]),
                completed=bool(row["completed"]),
                grade=row["grade"],
                notes=row["notes"],
            )
            courses.append(item)
        total = round(sum(float(course["credits"]) for course in courses), 2)
        completed_credits = round(sum(float(course["credits"]) for course in courses if course["completed"]), 2)
        result = dict(plan)
        result.update(
            id=int(plan["id"]),
            target_credits=float(plan["target_credits"]),
            total_credits=total,
            completed_credits=completed_credits,
            remaining_credits=max(round(float(plan["target_credits"]) - total, 2), 0.0),
            progress_percent=min(round(completed_credits / float(plan["target_credits"]) * 100, 1), 100.0),
            courses=courses,
        )
        return result

    @staticmethod
    def _meetings_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
        return first["day"] == second["day"] and first["start_minute"] < second["end_minute"] and second["start_minute"] < first["end_minute"]

    def validate_plan(self, plan_id: int) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        issues: list[dict[str, Any]] = []
        completed_before: set[str] = set()
        for course in plan["courses"]:
            missing = [code for code in course["prerequisites"] if code not in completed_before]
            if missing:
                issues.append({"type": "prerequisite", "course": course["code"], "missing": missing})
            if course["completed"]:
                completed_before.add(course["code"])
        for index, first in enumerate(plan["courses"]):
            for second in plan["courses"][index + 1 :]:
                overlaps = [
                    {"day": left["day"], "start_minute": max(left["start_minute"], right["start_minute"]), "end_minute": min(left["end_minute"], right["end_minute"])}
                    for left in first["meetings"]
                    for right in second["meetings"]
                    if self._meetings_overlap(left, right)
                ]
                if overlaps:
                    issues.append({"type": "schedule_conflict", "courses": [first["code"], second["code"]], "overlaps": overlaps})
        if plan["total_credits"] > plan["target_credits"]:
            issues.append({"type": "credit_overload", "excess_credits": round(plan["total_credits"] - plan["target_credits"], 2)})
        return {
            "plan_id": int(plan_id),
            "valid": not issues,
            "issue_count": len(issues),
            "issues": issues,
            "summary": "Plan passes all checks" if not issues else f"Plan has {len(issues)} issue(s)",
        }

    def recommend_courses(self, plan_id: int, *, term: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        plan = self.get_plan(plan_id)
        selected = {course["code"] for course in plan["courses"]}
        completed = {course["code"] for course in plan["courses"] if course["completed"]}
        candidates = self.list_courses(term, active=True, limit=500)
        recommendations: list[dict[str, Any]] = []
        for course in candidates:
            if course["code"] in selected:
                continue
            missing = [code for code in course["prerequisites"] if code not in completed]
            if missing:
                continue
            remaining = plan["remaining_credits"]
            fit = 2 if course["credits"] <= remaining else 0
            score = fit + (1 if course["term"] in {term, "Any"} else 0) + (1 if course["prerequisites"] else 0)
            recommendations.append({**course, "recommendation_score": score, "reason": "prerequisites satisfied"})
        recommendations.sort(key=lambda item: (-item["recommendation_score"], item["code"]))
        return recommendations[: min(max(int(limit), 1), 50)]

    def analytics(self) -> dict[str, Any]:
        with self._connect() as connection:
            summary = connection.execute(
                """SELECT COUNT(*) AS course_count, COALESCE(SUM(credits), 0) AS catalog_credits,
                   COUNT(DISTINCT department) AS departments FROM courses WHERE active=1"""
            ).fetchone()
            plan_summary = connection.execute(
                "SELECT COUNT(*) AS plan_count, COALESCE(AVG(target_credits), 0) AS average_target FROM plans"
            ).fetchone()
            popular = connection.execute(
                """SELECT c.code, c.title, COUNT(pc.plan_id) AS plan_count
                   FROM courses c LEFT JOIN plan_courses pc ON pc.course_code=c.code
                   GROUP BY c.code, c.title ORDER BY plan_count DESC, c.code LIMIT 10"""
            ).fetchall()
            by_term = connection.execute(
                "SELECT term, COUNT(*) AS count FROM courses WHERE active=1 GROUP BY term ORDER BY term"
            ).fetchall()
        return {
            "course_count": int(summary["course_count"]),
            "catalog_credits": round(float(summary["catalog_credits"]), 2),
            "department_count": int(summary["departments"]),
            "plan_count": int(plan_summary["plan_count"]),
            "average_target_credits": round(float(plan_summary["average_target"]), 2),
            "courses_by_term": [dict(row) for row in by_term],
            "most_planned_courses": [dict(row) for row in popular],
        }

    def export_plan_csv(self, plan_id: int) -> str:
        plan = self.get_plan(plan_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["position", "code", "title", "credits", "term", "completed", "grade", "notes"])
        for course in plan["courses"]:
            writer.writerow([
                course["position"], course["code"], course["title"], course["credits"], course["term"],
                course["completed"], "" if course["grade"] is None else course["grade"], course["notes"],
            ])
        return output.getvalue()
