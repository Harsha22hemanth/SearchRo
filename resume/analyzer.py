"""Rule-based resume analysis. Only reports what is actually in the text; never invents details."""
from __future__ import annotations

import re

from utils.helpers import find_skills, flat_skills
from utils.validators import is_valid_email

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s().\-]{8,17}\d)(?!\d)")
_LINK_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com)/[A-Za-z0-9_\-./%]+", re.I)
_BULLET_RE = re.compile(r"^\s*[•●▪■◦\-–—*·►✓]+\s*")

SECTION_ALIASES = {
    "summary": ["summary", "profile", "objective", "career objective", "professional summary", "about me"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "technologies", "tech stack"],
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "internship", "internships", "internship experience", "work history"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "project work"],
    "education": ["education", "academic background", "academics", "educational qualification",
                  "educational qualifications", "qualifications"],
    "certifications": ["certifications", "certificates", "certification", "licenses", "courses",
                       "training", "licenses & certifications", "certifications & courses"],
}
_HEADING_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}
_NOT_NAME_WORDS = {"resume", "curriculum", "vitae", "cv", "profile", "summary", "objective", "contact", "email",
                   "phone", "address"}
WEAK_STARTS = ("responsible for", "worked on", "helped", "duties included", "assisted with", "involved in",
               "tasked with")
ACTION_VERBS = {
    "built", "developed", "designed", "implemented", "created", "led", "improved", "optimized", "reduced",
    "increased", "automated", "deployed", "analyzed", "analysed", "engineered", "integrated", "migrated",
    "trained", "tested", "launched", "architected", "managed", "delivered", "wrote", "configured", "debugged",
}


def _heading_key(line: str) -> str | None:
    cleaned = re.sub(r"[:\-–—_=|]+$", "", line.strip().strip("*#").strip()).lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if 0 < len(cleaned) <= 40:
        return _HEADING_LOOKUP.get(cleaned)
    return None


def split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in text.split("\n"):
        key = _heading_key(line)
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _split_entries(section: str, limit: int = 8) -> list[str]:
    """Group a section's lines into entries (a new entry starts after a blank line or after bullets)."""
    entries: list[list[str]] = []
    current: list[str] = []
    saw_bullet = False
    for raw in section.split("\n"):
        line = raw.strip()
        if not line:
            if current:
                entries.append(current)
                current, saw_bullet = [], False
            continue
        bullet = _is_bullet(line)
        if not bullet and saw_bullet and current:
            entries.append(current)
            current, saw_bullet = [], False
        saw_bullet = saw_bullet or bullet
        current.append(_BULLET_RE.sub("", line))
    if current:
        entries.append(current)
    return [" — ".join(e)[:400] for e in entries[:limit] if e]


def extract_name(text: str) -> str:
    for line in [l.strip() for l in text.split("\n") if l.strip()][:6]:
        if "@" in line or re.search(r"\d", line) or "http" in line.lower() or _heading_key(line):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z.'\-]*", line)
        if 2 <= len(words) <= 4 and len(" ".join(words)) == len(line.replace("  ", " ")) \
                and not {w.lower() for w in words} & _NOT_NAME_WORDS:
            return " ".join(w.capitalize() if w.isupper() else w for w in words)
    return ""


def extract_phone(text: str) -> str:
    for match in _PHONE_RE.finditer(text):
        candidate = match.group(1).strip()
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 13 and not re.fullmatch(r"(19|20)\d{2}\D+(19|20)\d{2}", candidate):
            return candidate
    return ""


def analyze_resume(text: str) -> dict:
    """Return a structured dict. Missing items are '' or [] — never guessed."""
    sections = split_sections(text)
    emails = [e for e in _EMAIL_RE.findall(text) if is_valid_email(e)]
    skill_groups = find_skills(text)
    links = sorted({m.group(0) for m in _LINK_RE.finditer(text)})
    certs = [_BULLET_RE.sub("", l).strip() for l in sections.get("certifications", "").split("\n") if l.strip()]
    return {
        "name": extract_name(text),
        "email": emails[0] if emails else "",
        "phone": extract_phone(text),
        "links": links,
        "skills": flat_skills(text),
        "skill_groups": skill_groups,
        "languages": skill_groups.get("Programming Languages", []),
        "frameworks": skill_groups.get("Frameworks & Libraries", []),
        "databases": skill_groups.get("Databases", []),
        "tools": skill_groups.get("Tools & Platforms", []),
        "projects": _split_entries(sections.get("projects", "")),
        "education": _split_entries(sections.get("education", ""), limit=5),
        "experience": _split_entries(sections.get("experience", "")),
        "certifications": certs[:10],
        "sections_found": [k for k in sections if k != "header"],
        "word_count": len(text.split()),
    }


def resume_quality_report(text: str, analysis: dict) -> dict:
    """Deterministic checklist score (0-100) with concrete tips. Works without any API key."""
    bullets = [_BULLET_RE.sub("", l).strip() for l in text.split("\n") if _is_bullet(l)]
    weak = [b for b in bullets if b.lower().startswith(WEAK_STARTS)]
    quantified = [b for b in bullets if re.search(r"\d+\s*%|\d{2,}|\$\s*\d|\d+x\b", b)]
    with_verbs = [b for b in bullets if b.split(" ")[0].lower().rstrip(",.") in ACTION_VERBS]
    words = analysis.get("word_count", len(text.split()))
    links_text = " ".join(analysis.get("links", [])).lower()
    checks = [
        ("Email address present", bool(analysis.get("email")), 10, "Add a professional email address."),
        ("Phone number present", bool(analysis.get("phone")), 5, "Add a phone number recruiters can call."),
        ("LinkedIn or GitHub link", "linkedin" in links_text or "github" in links_text, 10,
         "Add your GitHub and/or LinkedIn profile URL."),
        ("Skills section / enough skills", len(analysis.get("skills", [])) >= 6, 15,
         "List at least 6 relevant technical skills (languages, frameworks, tools)."),
        ("Projects described", bool(analysis.get("projects")), 15,
         "Add a Projects section with what you built, the stack and the outcome."),
        ("Education listed", bool(analysis.get("education")), 10, "Add an Education section."),
        ("Reasonable length (150–900 words)", 150 <= words <= 900, 10,
         "Aim for one page for freshers (roughly 300–600 words)."),
        ("Bullets start with action verbs",
         bool(bullets) and len(with_verbs) / len(bullets) >= 0.4, 10,
         "Start bullets with verbs such as Built, Developed, Implemented, Optimized."),
        ("Some quantified results", len(quantified) >= 2, 10,
         "Add numbers where true: dataset sizes, accuracy %, users, speed-ups."),
        ("No weak bullet openers", not weak, 5, "Rewrite bullets that start with 'Responsible for' or 'Worked on'."),
    ]
    score = sum(weight for _, ok, weight, _ in checks if ok)
    return {
        "score": score,
        "checks": [{"label": l, "passed": ok, "tip": tip} for l, ok, _, tip in checks],
        "tips": [tip for _, ok, _, tip in checks if not ok],
        "weak_bullets": weak[:8],
        "bullet_count": len(bullets),
    }
