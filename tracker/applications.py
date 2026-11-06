"""Application tracker logic on top of the database layer."""
from __future__ import annotations

from datetime import date

from ai.cover_letter import offline_cover_letter
from ai.interview import categories_for_job, job_skill_questions, questions_for_category
from database import db
from job_search.job_details import Job, make_job_key
from resume.matcher import MatchResult, match_resume_to_job
from utils.helpers import rows_to_csv
from utils.validators import clean_text, is_valid_email, is_valid_phone, is_valid_url, parse_iso_date, validate_status

EXPORT_COLUMNS = [
    "title", "company", "location", "status", "applied_date", "interview_date", "followup_date",
    "contact_name", "contact_email", "contact_phone", "url", "source", "notes", "updated_at",
]


def track_job(job: Job | dict, status: str = "Saved") -> tuple[int, int, bool]:
    """Save a job and create its tracker entry. Returns (application_id, saved_job_id, created)."""
    data = job.to_dict() if isinstance(job, Job) else dict(job)
    job_id, created = db.save_job(data)
    existing = db.get_application_for_job(job_id)
    if existing:
        return int(existing["id"]), job_id, False
    return db.create_application(job_id, status), job_id, created


def add_manual_job(title: str, company: str, url: str = "", location: str = "", description: str = "",
                   status: str = "Saved") -> tuple[int, int]:
    """Add a job found elsewhere (e.g. a Naukri/LinkedIn listing) to the tracker."""
    title, company = clean_text(title, 150), clean_text(company, 150)
    if not title:
        raise ValueError("Job title is required.")
    if url.strip() and not is_valid_url(url):
        raise ValueError("The job link must start with http:// or https://")
    job = Job(title=title, company=company, url=url.strip(), location=clean_text(location, 120),
              description=clean_text(description, 20000), source="Added manually", posted_date="")
    job.job_key = make_job_key(title, company)
    app_id, job_id, _ = track_job(job, status)
    return app_id, job_id


def validate_application_fields(fields: dict) -> list[str]:
    """Return a list of human-readable problems (empty list = OK)."""
    problems = []
    if fields.get("contact_email") and not is_valid_email(fields["contact_email"]):
        problems.append("Recruiter email address looks invalid.")
    if fields.get("contact_phone") and not is_valid_phone(fields["contact_phone"]):
        problems.append("Recruiter phone number looks invalid.")
    for key, label in (("applied_date", "Application date"), ("interview_date", "Interview date"),
                       ("followup_date", "Follow-up date")):
        if fields.get(key) and parse_iso_date(fields[key]) is None:
            problems.append(f"{label} must be a valid date.")
    try:
        validate_status(fields.get("status", "Saved"))
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def save_application_changes(app_id: int, fields: dict) -> list[str]:
    """Validate and persist edits. Returns problems; empty list means saved."""
    cleaned = {
        "status": fields.get("status", "Saved"),
        "applied_date": _date_str(fields.get("applied_date")),
        "interview_date": _date_str(fields.get("interview_date")),
        "followup_date": _date_str(fields.get("followup_date")),
        "contact_name": clean_text(fields.get("contact_name"), 120),
        "contact_email": clean_text(fields.get("contact_email"), 160),
        "contact_phone": clean_text(fields.get("contact_phone"), 40),
        "notes": clean_text(fields.get("notes"), 4000),
    }
    problems = validate_application_fields(cleaned)
    if problems:
        return problems
    if not db.update_application(app_id, **cleaned):
        return ["That record no longer exists."]
    return []


def _date_str(value: object) -> str:
    d = parse_iso_date(value)
    return d.isoformat() if d else ""


def export_applications_csv(rows: list[dict]) -> str:
    return rows_to_csv(rows, EXPORT_COLUMNS)


def build_checklist(job: Job | dict, app: dict | None = None) -> list[str]:
    job = Job.from_dict(job) if isinstance(job, dict) else job
    items = [
        f"Read the full job description for {job.title} and note the top 5 requirements",
        "Tailor your resume headline and top project bullets to those requirements",
        "Check your resume for spelling, one-page length and working GitHub/LinkedIn links",
        "Review and edit the cover letter draft; remove anything that is not true for you",
        f"Research {job.company or 'the company'}: product, tech stack, recent news",
        "Prepare answers for 5 technical and 3 HR interview questions",
        "Apply manually on the employer's official website or listed application link",
        "Record the application date and set a follow-up date in the tracker",
    ]
    skills = job.skills[:4]
    if skills:
        items.insert(3, f"Brush up on: {', '.join(skills)}")
    return items


def prep_summary(job: Job | dict, resume_skills: list[str], resume_text: str, profile: dict) -> dict:
    """Everything the 'Application preparation' page shows for one job."""
    job = Job.from_dict(job) if isinstance(job, dict) else job
    match: MatchResult = match_resume_to_job(resume_skills, resume_text, job)
    return {
        "match": match,
        "important_skills": job.skills,
        "cover_letter": offline_cover_letter(profile, job, match.matched_skills),
        "interview_categories": categories_for_job(job),
        "interview_questions": job_skill_questions(job) + [
            q for cat in categories_for_job(job)[:2] for q in questions_for_category(cat)[:3]
        ],
        "checklist": build_checklist(job),
    }


def recommend_next_actions(stats: dict, profile: dict, has_resume: bool, upcoming: list[dict]) -> list[str]:
    """Rule-based suggestions computed from the real database state."""
    actions: list[str] = []
    today = date.today().isoformat()
    for item in upcoming:
        app = item["app"]
        label = f"{app['title']} at {app['company']}" if app["company"] else app["title"]
        if item["kind"] == "interview":
            actions.append(f"Prepare for your interview on {item['date']}: {label}")
        elif item["date"] < today:
            actions.append(f"Follow-up overdue since {item['date']}: {label}")
        else:
            actions.append(f"Follow up by {item['date']}: {label}")
    if not has_resume:
        actions.append("Upload your resume so SearchRo can match you against jobs")
    if not (profile.get("full_name") or profile.get("email")):
        actions.append("Complete your candidate profile (used for cover letters)")
    if stats["searches"] == 0:
        actions.append("Run your first job search")
    counts = stats["status_counts"]
    if counts.get("Saved", 0):
        actions.append(f"You have {counts['Saved']} saved job(s) waiting: review them and start preparing")
    if counts.get("Preparing", 0):
        actions.append(f"Finish preparing {counts['Preparing']} application(s) and submit them on the employer sites")
    if stats["saved_jobs"] == 0 and stats["searches"] > 0:
        actions.append("Save promising jobs from your search results to track them")
    if not actions:
        actions.append("You are all caught up. Search for new roles or practise interview questions")
    return actions[:8]
