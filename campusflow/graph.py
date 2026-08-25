"""Prerequisite graph analysis and multi-term schedule optimization for CampusFlow."""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict, deque
from typing import Iterable

TERMS = ("FALL", "WINTER", "SUMMER")


@dataclass(frozen=True, slots=True)
class CourseSpec:
    code: str
    title: str
    credits: float = 0.5
    terms: tuple[str, ...] = TERMS
    prerequisites: tuple[str, ...] = ()
    difficulty: int = 3
    workload_hours: float = 6.0

    def __post_init__(self) -> None:
        code = self.code.strip().upper()
        if not code:
            raise ValueError("course code is required")
        object.__setattr__(self, "code", code)
        normalized_terms = tuple(dict.fromkeys(term.strip().upper() for term in self.terms))
        if not normalized_terms or any(term not in TERMS for term in normalized_terms):
            raise ValueError(f"invalid offered terms for {code}: {self.terms!r}")
        object.__setattr__(self, "terms", normalized_terms)
        object.__setattr__(self, "prerequisites", tuple(p.strip().upper() for p in self.prerequisites))
        if self.credits <= 0:
            raise ValueError("credits must be positive")
        if not 1 <= self.difficulty <= 5:
            raise ValueError("difficulty must be 1..5")
        if self.workload_hours <= 0:
            raise ValueError("workload_hours must be positive")


@dataclass(frozen=True, slots=True)
class PlanConstraints:
    max_credits: float = 2.5
    max_courses: int = 5
    max_workload_hours: float = 32.0
    preferred_difficulty: float = 3.2

    def __post_init__(self) -> None:
        if self.max_credits <= 0 or self.max_courses <= 0 or self.max_workload_hours <= 0:
            raise ValueError("plan limits must be positive")


@dataclass(frozen=True, slots=True)
class SemesterPlan:
    index: int
    term: str
    courses: tuple[CourseSpec, ...]
    credits: float
    workload_hours: float
    difficulty_score: float


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    semesters: tuple[SemesterPlan, ...]
    unscheduled: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def scheduled_codes(self) -> tuple[str, ...]:
        return tuple(course.code for semester in self.semesters for course in semester.courses)

    @property
    def total_credits(self) -> float:
        return sum(semester.credits for semester in self.semesters)

    def to_mermaid(self) -> str:
        lines = ["flowchart LR"]
        for semester in self.semesters:
            node = f"T{semester.index}"
            label = f"{semester.term} {semester.index}\\n" + "\\n".join(c.code for c in semester.courses)
            lines.append(f'  {node}["{label}"]')
        for left, right in zip(self.semesters, self.semesters[1:]):
            lines.append(f"  T{left.index} --> T{right.index}")
        return "\n".join(lines)


class CourseGraph:
    """Validated directed acyclic prerequisite graph."""

    def __init__(self, courses: Iterable[CourseSpec]):
        self.courses: dict[str, CourseSpec] = {}
        for course in courses:
            if course.code in self.courses:
                raise ValueError(f"duplicate course: {course.code}")
            self.courses[course.code] = course
        self._children: dict[str, set[str]] = defaultdict(set)
        for course in self.courses.values():
            for prereq in course.prerequisites:
                if prereq not in self.courses:
                    raise ValueError(f"{course.code} references unknown prerequisite {prereq}")
                self._children[prereq].add(course.code)
        cycle = self.find_cycle()
        if cycle:
            raise ValueError("prerequisite cycle: " + " -> ".join(cycle))

    def find_cycle(self) -> tuple[str, ...]:
        state: dict[str, int] = {code: 0 for code in self.courses}
        stack: list[str] = []

        def visit(code: str) -> tuple[str, ...]:
            state[code] = 1
            stack.append(code)
            for prereq in self.courses[code].prerequisites:
                if state[prereq] == 0:
                    found = visit(prereq)
                    if found:
                        return found
                elif state[prereq] == 1:
                    start = stack.index(prereq)
                    return tuple(stack[start:] + [prereq])
            stack.pop()
            state[code] = 2
            return ()

        for code in self.courses:
            if state[code] == 0:
                found = visit(code)
                if found:
                    return found
        return ()

    def topological_order(self) -> tuple[str, ...]:
        indegree = {code: len(course.prerequisites) for code, course in self.courses.items()}
        ready = deque(sorted(code for code, degree in indegree.items() if degree == 0))
        result: list[str] = []
        while ready:
            code = ready.popleft()
            result.append(code)
            for child in sorted(self._children[code]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(result) != len(self.courses):
            raise ValueError("graph contains a cycle")
        return tuple(result)

    def prerequisites_met(self, code: str, completed: Iterable[str]) -> bool:
        course = self.courses[code.upper()]
        completed_set = {value.upper() for value in completed}
        return set(course.prerequisites) <= completed_set

    def eligible(self, completed: Iterable[str], term: str | None = None) -> tuple[CourseSpec, ...]:
        completed_set = {value.upper() for value in completed}
        term_norm = term.upper() if term else None
        result = [course for course in self.courses.values() if course.code not in completed_set and set(course.prerequisites) <= completed_set and (term_norm is None or term_norm in course.terms)]
        return tuple(sorted(result, key=lambda course: course.code))

    def descendants(self, code: str) -> tuple[str, ...]:
        start = code.upper()
        if start not in self.courses:
            raise KeyError(start)
        seen: set[str] = set()
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for child in self._children[current]:
                if child not in seen:
                    seen.add(child)
                    queue.append(child)
        return tuple(sorted(seen))

    def critical_path(self, targets: Iterable[str] | None = None) -> tuple[str, ...]:
        target_set = {t.upper() for t in targets} if targets else set(self.courses)
        best: dict[str, tuple[str, ...]] = {}
        for code in self.topological_order():
            prereq_paths = [best[p] for p in self.courses[code].prerequisites]
            prefix = max(prereq_paths, key=len) if prereq_paths else ()
            best[code] = prefix + (code,)
        candidates = [best[code] for code in target_set]
        return max(candidates, key=len, default=())

    def bottleneck_scores(self) -> dict[str, int]:
        return {code: len(self.descendants(code)) for code in self.courses}

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        for course in sorted(self.courses.values(), key=lambda item: item.code):
            safe = course.code.replace("*", "_").replace("-", "_")
            lines.append(f'  {safe}["{course.code} · {course.title}"]')
            for prereq in course.prerequisites:
                parent = prereq.replace("*", "_").replace("-", "_")
                lines.append(f"  {parent} --> {safe}")
        return "\n".join(lines)


class ScheduleOptimizer:
    """Deterministic greedy scheduler balancing prerequisites, unlock value and workload."""

    def __init__(self, graph: CourseGraph, constraints: PlanConstraints | None = None):
        self.graph = graph
        self.constraints = constraints or PlanConstraints()

    def optimize(self, required_codes: Iterable[str], *, completed: Iterable[str] = (), start_term: str = "FALL", max_terms: int = 12) -> ScheduleResult:
        start = start_term.upper()
        if start not in TERMS:
            raise ValueError(f"invalid start term: {start_term}")
        required = {code.upper() for code in required_codes}
        missing = required - self.graph.courses.keys()
        if missing:
            raise KeyError(f"unknown required courses: {sorted(missing)}")
        done = {code.upper() for code in completed}
        remaining = required - done
        bottlenecks = self.graph.bottleneck_scores()
        semester_plans: list[SemesterPlan] = []
        warnings: list[str] = []
        term_index = TERMS.index(start)

        for index in range(1, max_terms + 1):
            if not remaining:
                break
            term = TERMS[(term_index + index - 1) % len(TERMS)]
            eligible = [self.graph.courses[code] for code in remaining if set(self.graph.courses[code].prerequisites) <= done and term in self.graph.courses[code].terms]
            eligible.sort(key=lambda c: (-bottlenecks[c.code], abs(c.difficulty - self.constraints.preferred_difficulty), c.workload_hours, c.code))
            chosen: list[CourseSpec] = []
            credits = 0.0
            workload = 0.0
            for course in eligible:
                if len(chosen) >= self.constraints.max_courses:
                    break
                if credits + course.credits > self.constraints.max_credits + 1e-9:
                    continue
                if workload + course.workload_hours > self.constraints.max_workload_hours + 1e-9:
                    continue
                chosen.append(course)
                credits += course.credits
                workload += course.workload_hours
            if not chosen:
                semester_plans.append(SemesterPlan(index, term, (), 0.0, 0.0, 0.0))
                continue
            difficulty = sum(course.difficulty for course in chosen) / len(chosen)
            semester_plans.append(SemesterPlan(index, term, tuple(chosen), credits, workload, difficulty))
            done.update(course.code for course in chosen)
            remaining.difference_update(course.code for course in chosen)

        if remaining:
            warnings.append("Some required courses could not be scheduled within the configured horizon: " + ", ".join(sorted(remaining)))
        return ScheduleResult(tuple(semester_plans), tuple(sorted(remaining)), tuple(warnings))
