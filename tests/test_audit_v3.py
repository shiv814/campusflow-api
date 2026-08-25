from campusflow.audit import DegreeAuditor, DegreeProgram, RequirementGroup


def test_degree_audit_and_gpa():
    program = DegreeProgram("Demo", 2.0, (RequirementGroup("Core", ("A", "B"), required_credits=1.0, min_courses=2), RequirementGroup("Design", ("C", "D"), required_credits=0.5, min_courses=1)))
    auditor = DegreeAuditor(program, {"A": 0.5, "B": 0.5, "C": 0.5, "D": 0.5})
    audit = auditor.audit(("A", "B", "C"))
    assert audit.earned_credits == 1.5
    assert audit.progress_percent == 75.0
    assert not audit.missing_groups
    assert auditor.weighted_gpa({"A": "A", "B": "B+"}) == 3.65
