from campusflow.graph import CourseGraph, CourseSpec, PlanConstraints, ScheduleOptimizer


def catalogue():
    return [CourseSpec("A", "A", terms=("FALL", "WINTER"), difficulty=2), CourseSpec("B", "B", terms=("WINTER",), prerequisites=("A",), difficulty=3), CourseSpec("C", "C", terms=("FALL",), prerequisites=("A",), difficulty=4), CourseSpec("D", "D", terms=("WINTER",), prerequisites=("B", "C"), difficulty=5)]


def test_graph_analysis_and_critical_path():
    graph = CourseGraph(catalogue())
    assert graph.topological_order()[0] == "A"
    assert set(graph.descendants("A")) == {"B", "C", "D"}
    path = graph.critical_path(("D",))
    assert path[0] == "A" and path[-1] == "D" and len(path) == 3
    assert "A -->" in graph.to_mermaid()


def test_optimizer_respects_terms_and_prerequisites():
    graph = CourseGraph(catalogue())
    result = ScheduleOptimizer(graph, PlanConstraints(max_credits=1.0, max_courses=2, max_workload_hours=20)).optimize(("A", "B", "C", "D"), start_term="FALL", max_terms=8)
    codes = result.scheduled_codes
    assert set(codes) == {"A", "B", "C", "D"}
    assert codes.index("A") < codes.index("B") < codes.index("D")
    assert codes.index("A") < codes.index("C") < codes.index("D")
    for semester in result.semesters:
        for course in semester.courses:
            assert semester.term in course.terms


def test_cycle_is_rejected():
    try:
        CourseGraph([CourseSpec("A", "A", prerequisites=("B",)), CourseSpec("B", "B", prerequisites=("A",))])
    except ValueError as exc:
        assert "cycle" in str(exc)
    else:
        raise AssertionError("expected cycle validation")
