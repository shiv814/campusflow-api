from __future__ import annotations

import argparse
import sqlite3

from .db import CoursePlanner


SAMPLE_COURSES = [
    dict(code="CIS1500", title="Introduction to Programming", credits=0.5, term="Fall", department="Computing", delivery="Hybrid"),
    dict(code="CIS2500", title="Intermediate Programming", credits=0.5, term="Winter", department="Computing", prerequisites=["CIS1500"]),
    dict(code="CIS2520", title="Data Structures", credits=0.5, term="Fall", department="Computing", prerequisites=["CIS2500"]),
    dict(code="ENGG2410", title="Digital Systems Design", credits=0.5, term="Fall", department="Engineering", meetings=[{"day": "Tue", "start_minute": 600, "end_minute": 680, "location": "THRN 1200"}]),
    dict(code="ENGG2100", title="Engineering and Design II", credits=0.75, term="Winter", department="Engineering", delivery="In Person"),
]


def seed(planner: CoursePlanner) -> int:
    created = 0
    for item in SAMPLE_COURSES:
        try:
            planner.add_course(**item)
            created += 1
        except sqlite3.IntegrityError:
            continue
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a CampusFlow database with sample courses")
    parser.add_argument("--database", default="campusflow.db")
    args = parser.parse_args()
    count = seed(CoursePlanner(args.database))
    print(f"Seeded {count} new course(s)")


if __name__ == "__main__":
    main()
