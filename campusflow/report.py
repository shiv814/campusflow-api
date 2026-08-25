"""Portable HTML report generation for CampusFlow planning results."""
from __future__ import annotations

from html import escape
from .graph import ScheduleResult
from .audit import DegreeAuditResult


def _progress(value: float) -> str:
    pct = max(0.0, min(100.0, value))
    return f'<div class="progress"><span style="width:{pct:.2f}%"></span></div>'


def build_html_report(schedule: ScheduleResult, audit: DegreeAuditResult, *, student_name: str = "Student") -> str:
    semester_cards = []
    for semester in schedule.semesters:
        courses = "".join(f'<li><strong>{escape(course.code)}</strong><span>{escape(course.title)}</span></li>' for course in semester.courses) or '<li class="muted">No scheduled courses</li>'
        semester_cards.append(f'<article class="term"><div class="term-head"><b>Term {semester.index}</b><span>{escape(semester.term.title())}</span></div><ul>{courses}</ul><footer>{semester.credits:.1f} credits · {semester.workload_hours:.0f} h/week · difficulty {semester.difficulty_score:.1f}/5</footer></article>')
    groups = "".join(f'<tr><td>{escape(group.name)}</td><td>{group.earned_credits:.1f}/{group.required_credits:.1f}</td><td><span class="pill {"ok" if group.satisfied else "warn"}">{"Complete" if group.satisfied else "In progress"}</span></td></tr>' for group in audit.groups)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in schedule.warnings)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CampusFlow · {escape(student_name)}</title><style>
:root{{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--soft:#eff6ff;--ok:#166534;--warn:#92400e}}*{{box-sizing:border-box}}body{{margin:0;background:#f8fafc;color:var(--ink);font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:1040px;margin:0 auto;padding:48px 24px 72px}}.hero{{background:linear-gradient(135deg,#0f172a,#1d4ed8);color:white;border-radius:24px;padding:34px;box-shadow:0 20px 55px #0f172a18}}.eyebrow{{text-transform:uppercase;letter-spacing:.16em;font-size:11px;opacity:.75}}h1{{font-size:34px;margin:6px 0}}.hero p{{margin:0;opacity:.86}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin-top:20px}}.metric,.term,.panel{{background:white;border:1px solid var(--line);border-radius:18px;box-shadow:0 8px 24px #0f172a08}}.metric{{padding:20px}}.metric b{{font-size:25px;display:block}}.metric span{{color:var(--muted)}}h2{{margin:34px 0 14px;font-size:20px}}.progress{{height:8px;background:#e2e8f0;border-radius:99px;overflow:hidden;margin-top:12px}}.progress span{{height:100%;background:linear-gradient(90deg,#3b82f6,#22c55e);display:block}}.term{{padding:18px}}.term-head{{display:flex;justify-content:space-between;align-items:center}}.term-head span{{font-size:12px;background:var(--soft);color:#1d4ed8;padding:4px 9px;border-radius:99px}}ul{{padding-left:18px}}.term li span{{display:block;color:var(--muted);font-size:13px}}.term footer{{border-top:1px solid var(--line);padding-top:10px;color:var(--muted);font-size:12px}}.panel{{padding:20px}}table{{width:100%;border-collapse:collapse}}td{{padding:10px 8px;border-bottom:1px solid var(--line)}}.pill{{font-size:11px;border-radius:99px;padding:4px 8px}}.pill.ok{{background:#dcfce7;color:var(--ok)}}.pill.warn{{background:#fef3c7;color:var(--warn)}}.muted{{color:var(--muted)}}</style></head><body><main>
<section class="hero"><div class="eyebrow">CampusFlow academic plan</div><h1>{escape(student_name)}</h1><p>{escape(audit.program)} · generated locally with no external dependencies</p></section><section class="grid"><div class="metric"><b>{audit.progress_percent:.1f}%</b><span>degree progress</span>{_progress(audit.progress_percent)}</div><div class="metric"><b>{audit.earned_credits:.1f}</b><span>credits completed</span></div><div class="metric"><b>{schedule.total_credits:.1f}</b><span>credits scheduled</span></div></section><h2>Recommended sequence</h2><section class="grid">{''.join(semester_cards)}</section><h2>Requirement audit</h2><section class="panel"><table><tbody>{groups}</tbody></table></section>{f'<h2>Planning notes</h2><section class="panel"><ul>{warnings}</ul></section>' if warnings else ''}</main></body></html>'''
