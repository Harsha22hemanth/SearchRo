"""The normalised Job model and converters from each source's raw format."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from utils.helpers import flat_skills, parse_date_to_iso, strip_html


@dataclass
class Job:
    title: str
    company: str = ""
    location: str = ""
    country: str = ""
    url: str = ""
    source: str = ""
    description: str = ""
    posted_date: str = ""          # ISO 'YYYY-MM-DD' or ''
    job_type: str = ""             # Full-time / Part-time / Contract / Internship / ''
    remote: bool = False
    tags: list[str] = field(default_factory=list)
    salary: str = ""
    experience_level: str = "Unspecified"
    also_listed_on: list[str] = field(default_factory=list)
    job_key: str = ""

    def __post_init__(self) -> None:
        if not self.job_key:
            self.job_key = make_job_key(self.title, self.company)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in names})

    @property
    def skills(self) -> list[str]:
        return flat_skills(f"{self.title} {' '.join(self.tags)} {self.description}")


def make_job_key(title: str, company: str) -> str:
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())  # noqa: E731
    return hashlib.sha1(f"{norm(title)}|{norm(company)}".encode()).hexdigest()[:16]


_JOB_TYPE_MAP = (
    ("intern", "Internship"),
    ("part", "Part-time"),
    ("contract", "Contract"),
    ("freelance", "Contract"),
    ("full", "Full-time"),
    ("permanent", "Full-time"),
)


def normalize_job_type(raw: str | list | None) -> str:
    if isinstance(raw, list):
        raw = " ".join(str(r) for r in raw)
    text = str(raw or "").lower().replace("_", " ").replace("-", " ")
    for needle, label in _JOB_TYPE_MAP:
        if needle in text:
            return label
    return ""


def normalize_remotive(item: dict) -> Job | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    location = str(item.get("candidate_required_location") or "").strip() or "Remote"
    category = str(item.get("category") or "").strip()
    tags = [str(t) for t in (item.get("tags") or [])]
    if category and category not in tags:
        tags.append(category)
    return Job(
        title=title,
        company=str(item.get("company_name") or "").strip(),
        location=location,
        url=str(item.get("url") or "").strip(),
        source="Remotive",
        description=strip_html(str(item.get("description") or "")),
        posted_date=parse_date_to_iso(item.get("publication_date")),
        job_type=normalize_job_type(item.get("job_type")),
        remote=True,
        tags=tags,
        salary=str(item.get("salary") or "").strip(),
    )


def normalize_arbeitnow(item: dict) -> Job | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    return Job(
        title=title,
        company=str(item.get("company_name") or "").strip(),
        location=str(item.get("location") or "").strip(),
        url=str(item.get("url") or "").strip(),
        source="Arbeitnow",
        description=strip_html(str(item.get("description") or "")),
        posted_date=parse_date_to_iso(item.get("created_at")),
        job_type=normalize_job_type(item.get("job_types")),
        remote=bool(item.get("remote")),
        tags=[str(t) for t in (item.get("tags") or [])],
    )
