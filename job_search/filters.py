"""Filtering, entry-level detection, de-duplication and sorting (all keyword based)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import settings
from job_search.job_details import Job
from utils.helpers import flat_skills

# Words that appear in almost every query and should not *restrict* results.
GENERIC_TERMS = frozenset({
    "developer", "engineer", "programmer", "analyst", "job", "jobs", "fresher", "freshers", "junior",
    "trainee", "intern", "internship", "associate", "software", "entry", "level", "graduate", "role",
    "remote", "and", "the", "for", "a", "of", "in", "senior",
})

COUNTRY_ALIASES = {
    "united states": ["united states", "usa", "u.s.", "us only", "north america", "america"],
    "united kingdom": ["united kingdom", "uk", "england", "scotland", "wales", "london"],
    "india": ["india", "bangalore", "bengaluru", "hyderabad", "mumbai", "pune", "chennai", "delhi", "gurgaon",
              "gurugram", "noida", "kolkata"],
    "germany": ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne"],
    "canada": ["canada", "toronto", "vancouver"],
    "europe": ["europe", "emea", "eu"],
}


@dataclass
class SearchParams:
    query: str = ""
    skills: list[str] = field(default_factory=list)
    company: str = ""
    location: str = ""
    country: str = ""
    work_mode: str = "Any"            # Any / Remote / Onsite
    employment_type: str = "Any"      # Any / Full-time / Part-time / Contract / Internship
    experience_level: str = "Any"     # Any / Entry-level / Mid-level / Senior / Unspecified
    fresher_only: bool = False
    sort_by: str = "Relevance"        # Relevance / Newest


def query_terms(query: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9+#.]+", (query or "").lower()) if len(t) > 1 or t in ("c", "r")]


def essential_terms(query: str) -> list[str]:
    terms = query_terms(query)
    core = [t for t in terms if t not in GENERIC_TERMS]
    return core or terms


# --------------------------------------------------------------------- entry-level detection
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|-\s*\d{1,2}|to\s*\d{1,2})?\s*(?:years?|yrs?)\b(?:\s+of)?\s+"
    r"(?:[a-z\-]+\s+){0,3}?experience",
    re.IGNORECASE,
)


def _has_word(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None


def min_years_required(job: Job) -> int | None:
    """Smallest 'N years experience' number found in the description (None if none stated)."""
    matches = [int(m.group(1)) for m in _YEARS_RE.finditer(job.description or "")]
    return min(matches) if matches else None


def fresher_signals(job: Job) -> dict:
    """Explain why a job is (or is not) treated as entry-level. Fully keyword based."""
    title = (job.title or "").lower()
    text = f"{title} {(job.description or '').lower()}"
    positives = [k for k in settings.ENTRY_TITLE_KEYWORDS if _has_word(title, k)]
    positives += [k for k in settings.ENTRY_TEXT_KEYWORDS if k in text and k not in positives]
    blockers = [k for k in settings.SENIOR_TITLE_KEYWORDS if _has_word(title, k)]
    years = min_years_required(job)
    if years is not None:
        if years >= 2:
            blockers.append(f"asks for {years}+ years of experience")
        elif years <= 1:
            positives.append(f"asks for ≤{years} year(s) of experience")
    return {
        "is_entry_level": bool(positives) and not blockers,
        "positives": positives,
        "blockers": blockers,
        "years": years,
    }


def is_fresher_friendly(job: Job) -> bool:
    return fresher_signals(job)["is_entry_level"]


def classify_experience(job: Job) -> str:
    sig = fresher_signals(job)
    if sig["is_entry_level"]:
        return "Entry-level"
    title_senior = any(_has_word((job.title or "").lower(), k) for k in settings.SENIOR_TITLE_KEYWORDS)
    years = sig["years"]
    if title_senior or (years is not None and years >= 5):
        return "Senior"
    if years is not None and years >= 2:
        return "Mid-level"
    return "Unspecified"


# --------------------------------------------------------------------- individual filters
def matches_work_mode(job: Job, mode: str) -> bool:
    if mode == "Remote":
        return job.remote
    if mode == "Onsite":
        return not job.remote
    return True


def matches_employment_type(job: Job, wanted: str) -> bool:
    if wanted in ("", "Any"):
        return True
    if wanted == "Internship":
        return job.job_type == "Internship" or _has_word((job.title or "").lower(), "intern") \
            or _has_word((job.title or "").lower(), "internship")
    return job.job_type == wanted


def _location_text(job: Job) -> str:
    return f"{job.location} {job.country}".lower()


def matches_location(job: Job, location: str = "", country: str = "") -> bool:
    text = _location_text(job)
    open_remote = job.remote and any(w in text for w in ("worldwide", "anywhere", "global"))
    if location.strip():
        if location.strip().lower() not in text and not open_remote:
            return False
    if country.strip():
        wanted = country.strip().lower()
        names = COUNTRY_ALIASES.get(wanted, [wanted])
        if wanted not in names:
            names = [wanted, *names]
        if not any(re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", text) for n in names) and not open_remote:
            return False
    return True


def matches_company(job: Job, company: str) -> bool:
    return not company.strip() or company.strip().lower() in (job.company or "").lower()


def _searchable(job: Job) -> tuple[str, str, str]:
    return (job.title or "").lower(), " ".join(job.tags).lower(), (job.description or "").lower()


def relevance_score(job: Job, params: SearchParams) -> float:
    """Transparent score: title hit = 3, tag hit = 2, description hit = 1 per query term / skill."""
    title, tags, desc = _searchable(job)
    score = 0.0
    for term in query_terms(params.query) + [s.lower() for s in params.skills]:
        if term in title:
            score += 3
        if term in tags:
            score += 2
        if term in desc:
            score += 1
    if params.query and params.query.lower().strip() in title:
        score += 4
    return score


def matches_query(job: Job, params: SearchParams) -> bool:
    title, tags, desc = _searchable(job)
    blob = f"{title} {tags} {desc} {(job.company or '').lower()}"
    if not all(term in blob for term in essential_terms(params.query)):
        return False
    skills = [s.lower() for s in params.skills if s.strip()]
    if skills and not any(s in blob for s in skills):
        return False
    return True


def apply_filters(jobs: list[Job], params: SearchParams) -> list[Job]:
    result = []
    for job in jobs:
        if not job.experience_level or job.experience_level == "Unspecified":
            job.experience_level = classify_experience(job)
        if not matches_query(job, params):
            continue
        if not matches_company(job, params.company):
            continue
        if not matches_location(job, params.location, params.country):
            continue
        if not matches_work_mode(job, params.work_mode):
            continue
        if not matches_employment_type(job, params.employment_type):
            continue
        if params.experience_level not in ("", "Any") and job.experience_level != params.experience_level:
            continue
        if params.fresher_only and not is_fresher_friendly(job):
            continue
        result.append(job)
    return result


# --------------------------------------------------------------------- duplicates and sorting
def deduplicate_jobs(jobs: list[Job]) -> list[Job]:
    """Remove duplicates (same title+company, or same URL). Keeps the richest copy, notes other sources."""
    kept: dict[str, Job] = {}
    by_url: dict[str, str] = {}
    for job in jobs:
        url = (job.url or "").split("?")[0].rstrip("/").lower()
        key = by_url.get(url) if url and url in by_url else job.job_key
        existing = kept.get(key)
        if existing is None:
            kept[key] = job
            if url:
                by_url[url] = key
            continue
        winner, loser = (job, existing) if len(job.description) > len(existing.description) else (existing, job)
        if loser.source and loser.source != winner.source and loser.source not in winner.also_listed_on:
            winner.also_listed_on.append(loser.source)
        for src in loser.also_listed_on:
            if src != winner.source and src not in winner.also_listed_on:
                winner.also_listed_on.append(src)
        kept[key] = winner
    return list(kept.values())


def sort_jobs(jobs: list[Job], params: SearchParams) -> list[Job]:
    if params.sort_by == "Newest":
        return sorted(jobs, key=lambda j: j.posted_date or "", reverse=True)
    return sorted(jobs, key=lambda j: (relevance_score(j, params), j.posted_date or ""), reverse=True)


def required_skills(job: Job) -> list[str]:
    return flat_skills(f"{job.title} {' '.join(job.tags)} {job.description}")
