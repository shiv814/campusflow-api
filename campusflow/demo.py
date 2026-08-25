"""Run the v3 planning engine without starting the HTTP server."""
from __future__ import annotations

from datetime import date, time
from pathlib import Path

from .audit import DegreeAuditor, DegreeProgram, RequirementGroup
from .calendar import Meeting, export_ics
from .graph import CourseGraph, CourseSpec, PlanConstraints, ScheduleOptimizer
from .report import build_html_report


def sample_courses() -> list[CourseSpec]:
    return [CourseSpec("ENGG*1410", "Introductory Programming", terms=("FALL", "WINTER"), difficulty=2), CourseSpec("ENGG*1420", "Object-Oriented Programming", terms=("WINTER",), prerequisites=("ENGG*1410",), difficulty=3), CourseSpec("ENGG*2410", "Digital Systems", terms=("FALL",), prerequisites=("ENGG*1410",), difficulty=4), CourseSpec("ENGG*3050", "Embedded Systems", terms=("WINTER",), prerequisites=("ENGG*2410",), difficulty=4), CourseSpec("CIS*2520", "Data Structures", terms=("FALL", "WINTER"), prerequisites=("ENGG*1420",), difficulty=4), CourseSpec("CIS*2750", "Software Systems", terms=("FALL",), prerequisites=("CIS*2520",), difficulty=4)]


def main() -> None:
    courses = sample_courses()
    graph = CourseGraph(courses)
    result = ScheduleOptimizer(graph, PlanConstraints(max_credits=1.5, max_courses=3, max_workload_hours=22)).optimize([course.code for course in courses], completed=("ENGG*1410",), start_term="WINTER")
    credit_map = {course.code: course.credits for course in courses}
    program = DegreeProgram("Computer Engineering Demo", 3.0, (RequirementGroup("Programming core", ("ENGG*1410", "ENGG*1420", "CIS*2520"), 1.5, 3), RequirementGroup("Systems core", ("ENGG*2410", "ENGG*3050", "CIS*2750"), 1.5, 3)))
    audit = DegreeAuditor(program, credit_map).audit(("ENGG*1410",))
    Path("campusflow-demo.html").write_text(build_html_report(result, audit, student_name="Demo Student"), encoding="utf-8")
    calendar = export_ics([Meeting("ENGG*1420", "Object-Oriented Programming", "MON", time(10, 30), time(11, 20), "THRN 1200")], term_start=date(2026, 1, 5), term_end=date(2026, 4, 10))
    Path("campusflow-demo.ics").write_text(calendar, encoding="utf-8")
    print("Generated campusflow-demo.html and campusflow-demo.ics")
    print("Critical prerequisite path:", " -> ".join(graph.critical_path()))
    for semester in result.semesters:
        print(f"{semester.index:>2} {semester.term:<6}", ", ".join(course.code for course in semester.courses) or "—")


if __name__ == "__main__": main()
