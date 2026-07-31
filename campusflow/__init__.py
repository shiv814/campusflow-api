"""CampusFlow academic-planning toolkit."""

from .db import ConflictError, CoursePlanner, ValidationError

__all__ = ["ConflictError", "CoursePlanner", "ValidationError"]
__version__ = "2.0.0"
