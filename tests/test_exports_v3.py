from datetime import date, time
from campusflow.calendar import Meeting, export_ics
from campusflow.graph import CourseSpec, SemesterPlan, ScheduleResult
from campusflow.audit import DegreeAuditResult
from campusflow.report import build_html_report


def test_calendar_export_contains_recurrence_and_escaping():
    data = export_ics([Meeting("ENGG*1410", "Programming, Intro", "mon", time(9), time(10), "Room; 1")], term_start=date(2026, 9, 8), term_end=date(2026, 12, 4))
    assert "BEGIN:VCALENDAR" in data
    assert "BYDAY=MO" in data
    assert "Programming\\, Intro" in data
    assert "Room\\; 1" in data


def test_html_report_is_self_contained():
    course = CourseSpec("A", "Architecture")
    schedule = ScheduleResult((SemesterPlan(1, "FALL", (course,), 0.5, 6.0, 3.0),))
    audit = DegreeAuditResult("Demo", 1.0, 4.0, 25.0, (), ("Core",))
    html = build_html_report(schedule, audit, student_name="A <Student>")
    assert "<!doctype html>" in html.lower()
    assert "A &lt;Student&gt;" in html
    assert "25.0%" in html
