import sqlite3

import pytest

from campusflow.db import ConflictError, CoursePlanner, ValidationError


def add_catalog(planner):
    planner.add_course("CIS1500", "Intro Programming", 0.5, "Fall", department="Computing")
    planner.add_course("CIS2500", "Intermediate Programming", 0.5, "Winter", ["CIS1500"], department="Computing")
    planner.add_course(
        "ENGG2410", "Digital Systems", 0.5, "Fall", department="Engineering",
        meetings=[{"day": "Tue", "start_minute": 600, "end_minute": 680, "location": "THRN"}],
    )
    planner.add_course(
        "ENGG3100", "Control Systems", 0.75, "Fall", department="Engineering",
        meetings=[{"day": "Tue", "start_minute": 640, "end_minute": 720, "location": "RICH"}],
    )


def test_catalog_search_update_and_analytics(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    add_catalog(planner)
    computing = planner.list_courses(department="computing", query="program")
    assert [course["code"] for course in computing] == ["CIS1500", "CIS2500"]
    updated = planner.update_course("cis1500", description="Foundational Python programming", delivery="online")
    assert updated["delivery"] == "Online"
    assert "Python" in updated["description"]
    analytics = planner.analytics()
    assert analytics["course_count"] == 4
    assert analytics["department_count"] == 2
    assert analytics["catalog_credits"] == 2.25


def test_plan_validation_recommendations_progress_and_export(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    add_catalog(planner)
    plan = planner.create_plan("Engineering Plan", 1.5, student_id="1001", start_term="Fall")
    planner.add_course_to_plan(plan["id"], "CIS1500", completed=True, grade=89)
    planner.add_course_to_plan(plan["id"], "CIS2500")
    planner.add_course_to_plan(plan["id"], "ENGG2410")
    planner.add_course_to_plan(plan["id"], "ENGG3100")
    result = planner.get_plan(plan["id"])
    assert result["total_credits"] == 2.25
    assert result["completed_credits"] == 0.5
    assert result["progress_percent"] == 33.3
    validation = planner.validate_plan(plan["id"])
    assert validation["valid"] is False
    assert {issue["type"] for issue in validation["issues"]} == {"schedule_conflict", "credit_overload"}
    export = planner.export_plan_csv(plan["id"])
    assert "CIS1500" in export and "Control Systems" in export
    planner.remove_course_from_plan(plan["id"], "ENGG3100")
    recommendations = planner.recommend_courses(plan["id"], term="Fall")
    assert any(item["code"] == "ENGG3100" for item in recommendations)


def test_prerequisite_issue_and_course_delete_conflict(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    add_catalog(planner)
    plan = planner.create_plan("Out of order", 1.0)
    planner.add_course_to_plan(plan["id"], "CIS2500")
    validation = planner.validate_plan(plan["id"])
    assert validation["issues"][0]["missing"] == ["CIS1500"]
    with pytest.raises(ConflictError):
        planner.delete_course("CIS2500")
    planner.remove_course_from_plan(plan["id"], "CIS2500")
    planner.delete_course("CIS2500")
    with pytest.raises(KeyError):
        planner.get_course("CIS2500")


def test_validation_rules_and_duplicate_rejection(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    with pytest.raises(ValidationError):
        planner.add_course("BAD", "Invalid", 0.5, "Fall")
    with pytest.raises(ValidationError):
        planner.add_course("CIS1500", "Intro", 4.0, "Fall")
    planner.add_course("CIS1500", "Intro", 0.5, "Fall")
    with pytest.raises(sqlite3.IntegrityError):
        planner.add_course("CIS1500", "Duplicate", 0.5, "Fall")
    with pytest.raises(ValidationError):
        planner.update_course("CIS1500", meetings=[{"day": "X", "start_minute": 10, "end_minute": 20}])
