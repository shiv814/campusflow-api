from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a request violates a domain rule."""


class CoursePlanner:
    def __init__(self, database: str | Path = "campusflow.db") -> None:
        self.database = str(database)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    code TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    credits REAL NOT NULL CHECK(credits > 0),
                    term TEXT NOT NULL,
                    prerequisites TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    target_credits REAL NOT NULL CHECK(target_credits > 0)
                );
                CREATE TABLE IF NOT EXISTS plan_courses (
                    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
                    course_code TEXT NOT NULL REFERENCES courses(code) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (plan_id, course_code)
                );
                """
            )

    @staticmethod
    def _clean_code(value: str) -> str:
        code = value.strip().upper()
        if len(code) < 4 or not any(char.isdigit() for char in code):
            raise ValidationError("course code must include letters and a number")
        return code

    def add_course(
        self,
        code: str,
        title: str,
        credits: float,
        term: str,
        prerequisites: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_code = self._clean_code(code)
        clean_title = title.strip()
        clean_term = term.strip().title()
        if not clean_title:
            raise ValidationError("title is required")
        if credits <= 0 or credits > 2.0:
            raise ValidationError("credits must be between 0 and 2")
        prereq_codes = [self._clean_code(item) for item in (prerequisites or [])]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO courses(code, title, credits, term, prerequisites) VALUES (?, ?, ?, ?, ?)",
                (clean_code, clean_title, float(credits), clean_term, ",".join(prereq_codes)),
            )
        return self.get_course(clean_code)

    def get_course(self, code: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT code, title, credits, term, prerequisites FROM courses WHERE code = ?",
                (self._clean_code(code),),
            ).fetchone()
        if row is None:
            raise KeyError(code)
        result = dict(row)
        result["prerequisites"] = [item for item in result["prerequisites"].split(",") if item]
        return result

    def list_courses(self, term: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT code, title, credits, term, prerequisites FROM courses"
        parameters: tuple[Any, ...] = ()
        if term:
            query += " WHERE lower(term) = lower(?)"
            parameters = (term.strip(),)
        query += " ORDER BY code"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        courses = []
        for row in rows:
            item = dict(row)
            item["prerequisites"] = [value for value in item["prerequisites"].split(",") if value]
            courses.append(item)
        return courses

    def create_plan(self, name: str, target_credits: float = 5.0) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("plan name is required")
        if target_credits <= 0:
            raise ValidationError("target credits must be positive")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO plans(name, target_credits) VALUES (?, ?)",
                (name.strip(), float(target_credits)),
            )
            plan_id = int(cursor.lastrowid)
        return self.get_plan(plan_id)

    def add_course_to_plan(self, plan_id: int, course_code: str) -> dict[str, Any]:
        code = self._clean_code(course_code)
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM plans WHERE id = ?", (plan_id,)).fetchone() is None:
                raise KeyError(plan_id)
            if connection.execute("SELECT 1 FROM courses WHERE code = ?", (code,)).fetchone() is None:
                raise KeyError(code)
            position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM plan_courses WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO plan_courses(plan_id, course_code, position) VALUES (?, ?, ?)",
                (plan_id, code, position),
            )
        return self.get_plan(plan_id)

    def get_plan(self, plan_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            plan = connection.execute(
                "SELECT id, name, target_credits FROM plans WHERE id = ?", (plan_id,)
            ).fetchone()
            if plan is None:
                raise KeyError(plan_id)
            rows = connection.execute(
                """
                SELECT c.code, c.title, c.credits, c.term, c.prerequisites
                FROM plan_courses pc JOIN courses c ON c.code = pc.course_code
                WHERE pc.plan_id = ? ORDER BY pc.position
                """,
                (plan_id,),
            ).fetchall()
        courses = []
        for row in rows:
            item = dict(row)
            item["prerequisites"] = [value for value in item["prerequisites"].split(",") if value]
            courses.append(item)
        total = round(sum(float(course["credits"]) for course in courses), 2)
        return {
            "id": int(plan["id"]),
            "name": str(plan["name"]),
            "target_credits": float(plan["target_credits"]),
            "total_credits": total,
            "remaining_credits": max(round(float(plan["target_credits"]) - total, 2), 0.0),
            "courses": courses,
        }
