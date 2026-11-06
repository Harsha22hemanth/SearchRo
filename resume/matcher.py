"""Transparent resume-to-job matching.

Overall score (0-100) = weighted average of three components:

* Skills coverage      (60%) - share of the job's recognised skills that appear in your skill list
* Keyword overlap      (25%) - share of the job's 25 most frequent content words found in your resume
* Title relevance      (15%) - share of the job title's words found in your resume

Components that cannot be computed (e.g. the job text names no known skills) are dropped and
the remaining weights are re-scaled. This is a text-overlap indicator, NOT a prediction of
hiring chances.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from job_search.filters import GENERIC_TERMS, min_years_required
from job_search.job_details import Job
from utils.helpers import keywords, tokenize

WEIGHTS = {"skills": 0.60, "keywords": 0.25, "title": 0.15}
DISCLAIMER = ("Match scores measure keyword/skill overlap between your resume and the posting. "
              "They are not a prediction of whether you will be hired.")


@dataclass
class MatchResult:
    overall: int = 0
    skill_score: int | None = None
    keyword_score: int | None = None
    title_score: int | None = None
    job_skills: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    label: str = "Low overlap"
    weights_used: dict[str, float] = field(default_factory=dict)


def _label(score: int) -> str:
    return "Strong overlap" if score >= 70 else "Moderate overlap" if score >= 45 else "Low overlap"


def _top_job_keywords(job: Job, n: int = 25) -> list[str]:
    skill_words = {w.lower() for s in job.skills for w in tokenize(s)}
    counts = Counter(k for k in keywords(f"{job.title} {job.title} {job.description}")
                     if k not in GENERIC_TERMS and k not in skill_words)
    return [w for w, _ in counts.most_common(n)]


def match_resume_to_job(resume_skills: list[str], resume_text: str, job: Job | dict) -> MatchResult:
    job = Job.from_dict(job) if isinstance(job, dict) else job
    resume_set = {s.strip().lower() for s in resume_skills if s.strip()}
    resume_tokens = set(tokenize(resume_text)) | {w for s in resume_set for w in tokenize(s)}
    result = MatchResult()

    result.job_skills = job.skills
    result.matched_skills = [s for s in result.job_skills if s.lower() in resume_set]
    result.missing_skills = [s for s in result.job_skills if s.lower() not in resume_set]
    scores: dict[str, float] = {}
    if result.job_skills:
        scores["skills"] = 100 * len(result.matched_skills) / len(result.job_skills)
        result.skill_score = round(scores["skills"])

    top = _top_job_keywords(job)
    if top:
        result.matched_keywords = [w for w in top if w in resume_tokens]
        result.missing_keywords = [w for w in top if w not in resume_tokens]
        scores["keywords"] = 100 * len(result.matched_keywords) / len(top)
        result.keyword_score = round(scores["keywords"])

    title_words = [w for w in keywords(job.title) if w not in {"senior", "junior"}]
    if title_words:
        scores["title"] = 100 * sum(w in resume_tokens for w in title_words) / len(title_words)
        result.title_score = round(scores["title"])

    if scores:
        total_weight = sum(WEIGHTS[k] for k in scores)
        result.weights_used = {k: round(WEIGHTS[k] / total_weight, 2) for k in scores}
        result.overall = round(sum(scores[k] * WEIGHTS[k] for k in scores) / total_weight)
    result.label = _label(result.overall)
    result.suggestions = _suggestions(result, job)
    return result


def _suggestions(r: MatchResult, job: Job) -> list[str]:
    tips: list[str] = []
    if r.missing_skills:
        top = ", ".join(r.missing_skills[:5])
        tips.append(f"The posting mentions {top}. If you have real experience with these, add them to your "
                    "skills and project bullets; if not, they are good learning targets.")
    if r.keyword_score is not None and r.keyword_score < 50 and r.missing_keywords:
        tips.append("Where it is truthful, reuse the posting's wording, e.g. "
                    + ", ".join(r.missing_keywords[:6]) + ".")
    if r.title_score is not None and r.title_score < 50:
        tips.append(f"Consider a headline or summary line that names the target role ('{job.title}').")
    years = min_years_required(job)
    if years is not None and years >= 2:
        tips.append(f"The posting asks for {years}+ years of experience; emphasise projects and internships "
                    "that show equivalent hands-on work, or prioritise entry-level listings.")
    if not r.job_skills:
        tips.append("No known technical skills were recognised in this posting, so the score uses wording overlap only.")
    if not tips:
        tips.append("Good overlap. Tailor your top two project bullets to this role's responsibilities.")
    return tips


def compare_jobs(resume_skills: list[str], resume_text: str, jobs: list[Job | dict]) -> list[tuple[Job, MatchResult]]:
    pairs = []
    for job in jobs:
        job_obj = Job.from_dict(job) if isinstance(job, dict) else job
        pairs.append((job_obj, match_resume_to_job(resume_skills, resume_text, job_obj)))
    return sorted(pairs, key=lambda p: p[1].overall, reverse=True)
