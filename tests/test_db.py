from campusflow.db import CoursePlanner, ValidationError


def test_course_and_plan_workflow(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    planner.add_course("ENGG2410", "Digital Systems", 0.5, "Fall")
    planner.add_course("CIS2520", "Data Structures", 0.5, "Winter", ["CIS1500"])
    plan = planner.create_plan("Third Year", 1.0)
    planner.add_course_to_plan(plan["id"], "ENGG2410")
    completed = planner.add_course_to_plan(plan["id"], "CIS2520")
    assert completed["total_credits"] == 1.0
    assert completed["remaining_credits"] == 0.0
    assert [course["code"] for course in completed["courses"]] == ["ENGG2410", "CIS2520"]


def test_validation(tmp_path):
    planner = CoursePlanner(tmp_path / "test.db")
    try:
        planner.add_course("BAD", "Invalid", 0.5, "Fall")
    except ValidationError as error:
        assert "course code" in str(error)
    else:
        raise AssertionError("invalid course code should fail")
