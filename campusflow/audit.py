"""Degree requirement auditing and progress analytics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class RequirementGroup:
    name: str
    course_codes: tuple[str, ...] = ()
    required_credits: float = 0.0
    min_courses: int = 0

    def __post_init__(self) -> None:
        if self.required_credits < 0 or self.min_courses < 0:
            raise ValueError("requirement thresholds cannot be negative")
        object.__setattr__(self, "course_codes", tuple(code.upper() for code in self.course_codes))


@dataclass(frozen=True, slots=True)
class DegreeProgram:
    name: str
    total_credits: float
    groups: tuple[RequirementGroup, ...]

    def __post_init__(self) -> None:
        if self.total_credits <= 0:
            raise ValueError("total_credits must be positive")


@dataclass(frozen=True, slots=True)
class GroupAudit:
    name: str
    earned_credits: float
    required_credits: float
    completed_courses: tuple[str, ...]
    remaining_courses: tuple[str, ...]
    satisfied: bool


@dataclass(frozen=True, slots=True)
class DegreeAuditResult:
    program: str
    earned_credits: float
    total_credits: float
    progress_percent: float
    groups: tuple[GroupAudit, ...]
    missing_groups: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return self.earned_credits >= self.total_credits and not self.missing_groups


GRADE_POINTS = {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7, "C+": 2.3, "C": 2.0, "C-": 1.7, "D": 1.0, "F": 0.0}


class DegreeAuditor:
    def __init__(self, program: DegreeProgram, course_credits: Mapping[str, float]):
        self.program = program
        self.course_credits = {code.upper(): float(value) for code, value in course_credits.items()}
        if any(value <= 0 for value in self.course_credits.values()):
            raise ValueError("course credits must be positive")

    def audit(self, completed: Iterable[str]) -> DegreeAuditResult:
        completed_set = {code.upper() for code in completed}
        earned = sum(self.course_credits.get(code, 0.0) for code in completed_set)
        group_results: list[GroupAudit] = []
        missing: list[str] = []
        for group in self.program.groups:
            eligible = set(group.course_codes)
            completed_group = sorted(completed_set & eligible)
            group_credits = sum(self.course_credits.get(code, 0.0) for code in completed_group)
            satisfied = len(completed_group) >= group.min_courses and group_credits + 1e-9 >= group.required_credits
            if not satisfied:
                missing.append(group.name)
            group_results.append(GroupAudit(group.name, group_credits, group.required_credits, tuple(completed_group), tuple(sorted(eligible - completed_set)), satisfied))
        progress = min(100.0, 100.0 * earned / self.program.total_credits)
        return DegreeAuditResult(self.program.name, earned, self.program.total_credits, round(progress, 2), tuple(group_results), tuple(missing))

    def weighted_gpa(self, grades: Mapping[str, str]) -> float | None:
        points = 0.0
        credits = 0.0
        for code, grade in grades.items():
            normalized = grade.strip().upper()
            if normalized not in GRADE_POINTS:
                raise ValueError(f"unsupported grade {grade!r}")
            weight = self.course_credits.get(code.upper())
            if weight is None:
                continue
            points += GRADE_POINTS[normalized] * weight
            credits += weight
        return round(points / credits, 3) if credits else None
