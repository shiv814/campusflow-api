"""RFC 5545-compatible iCalendar export for planned course meetings."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha1

DAY_INDEX = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
DAY_ICS = {"MON": "MO", "TUE": "TU", "WED": "WE", "THU": "TH", "FRI": "FR", "SAT": "SA", "SUN": "SU"}


@dataclass(frozen=True, slots=True)
class Meeting:
    course_code: str
    title: str
    day: str
    start: time
    end: time
    location: str = ""

    def __post_init__(self) -> None:
        day = self.day.strip().upper()[:3]
        if day not in DAY_INDEX:
            raise ValueError(f"invalid weekday: {self.day}")
        if self.end <= self.start:
            raise ValueError("meeting end must be after start")
        object.__setattr__(self, "day", day)
        object.__setattr__(self, "course_code", self.course_code.strip().upper())


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _first_day(term_start: date, weekday: int) -> date:
    return term_start + timedelta(days=(weekday - term_start.weekday()) % 7)


def export_ics(meetings: list[Meeting], *, term_start: date, term_end: date, calendar_name: str = "CampusFlow Plan") -> str:
    if term_end < term_start:
        raise ValueError("term_end must not precede term_start")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CampusFlow//Academic Plan//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(calendar_name)}"]
    for meeting in meetings:
        first = _first_day(term_start, DAY_INDEX[meeting.day])
        start_dt = datetime.combine(first, meeting.start)
        end_dt = datetime.combine(first, meeting.end)
        uid_source = f"{meeting.course_code}|{meeting.day}|{meeting.start}|{term_start}"
        uid = sha1(uid_source.encode("utf-8")).hexdigest()[:20] + "@campusflow"
        lines.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}", f"RRULE:FREQ=WEEKLY;BYDAY={DAY_ICS[meeting.day]};UNTIL={term_end.strftime('%Y%m%d')}T235959", f"SUMMARY:{_escape(meeting.course_code + ' · ' + meeting.title)}", f"LOCATION:{_escape(meeting.location)}", "END:VEVENT"])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
