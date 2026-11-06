"""Skill-gap analysis: compare your skills with one or more job postings and build a learning order."""
from __future__ import annotations

from collections import Counter

from ai.assistant import SYSTEM_BASE, ask
from config import settings
from job_search.job_details import Job


def _category_of(skill: str) -> str:
    for category, skills in settings.SKILL_CATEGORIES.items():
        if skill in skills:
            return category
    return "Other"


def analyze_skill_gap(resume_skills: list[str], jobs: list[Job | dict]) -> list[dict]:
    """Return missing skills ranked by how many of the given jobs require them."""
    have = {s.lower() for s in resume_skills}
    jobs = [Job.from_dict(j) if isinstance(j, dict) else j for j in jobs]
    if not jobs:
        return []
    counts: Counter[str] = Counter()
    for job in jobs:
        counts.update(s for s in job.skills if s.lower() not in have)
    gaps = []
    for skill, n in counts.most_common():
        share = n / len(jobs)
        gaps.append({
            "skill": skill,
            "category": _category_of(skill),
            "jobs_requiring": n,
            "share": round(share * 100),
            "priority": "High" if share >= 0.5 else "Medium" if share >= 0.25 else "Low",
        })
    return gaps


def build_roadmap(gaps: list[dict]) -> list[dict]:
    """Group gaps into ordered phases (High -> Medium -> Low). A suggested order, not a time estimate."""
    phases = []
    for priority, title in (("High", "Phase 1: learn first"), ("Medium", "Phase 2: learn next"),
                            ("Low", "Phase 3: nice to have")):
        items = [g for g in gaps if g["priority"] == priority]
        if items:
            phases.append({
                "phase": title,
                "skills": [g["skill"] for g in items],
                "how": "For each skill: read the official documentation basics, build one small project that "
                       "uses it, and add it to your resume only once you can explain it in an interview.",
            })
    return phases


def ai_roadmap(resume_skills: list[str], gaps: list[dict], target_role: str = "") -> str:
    prompt = (
        f"The candidate targets: {target_role or 'junior developer roles'}.\n"
        f"Current skills: {', '.join(resume_skills) or 'none listed'}.\n"
        "Missing skills ranked by demand in the selected jobs (skill, % of jobs requiring it): "
        + "; ".join(f"{g['skill']} ({g['share']}%)" for g in gaps[:15]) + ".\n\n"
        "Write a prioritised learning roadmap: explain the order and why, suggest one concrete beginner "
        "project per priority skill, and name free resources by type (official docs, well-known courses) "
        "without inventing links. Keep it practical for someone with a CS degree and no work experience."
    )
    return ask(prompt, system=SYSTEM_BASE, max_tokens=1600)
