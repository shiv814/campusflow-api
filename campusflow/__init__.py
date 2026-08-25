"""CampusFlow academic-planning toolkit."""

from .db import ConflictError, CoursePlanner, ValidationError
from .graph import CourseGraph, CourseSpec, PlanConstraints, ScheduleOptimizer
from .audit import DegreeAuditor, DegreeProgram, RequirementGroup

__all__ = ["ConflictError", "CoursePlanner", "ValidationError", "CourseGraph", "CourseSpec", "PlanConstraints", "ScheduleOptimizer", "DegreeAuditor", "DegreeProgram", "RequirementGroup"]
__version__ = "3.0.0"
