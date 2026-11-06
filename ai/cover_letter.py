"""Cover letters: an offline template draft (always available) and an optional AI-written version."""
from __future__ import annotations

from ai.assistant import SYSTEM_BASE, ask
from job_search.job_details import Job


def offline_cover_letter(profile: dict, job: Job | dict, matched_skills: list[str] | None = None) -> str:
    """A plain template filled ONLY with facts you have saved. Edit it before sending."""
    job = Job.from_dict(job) if isinstance(job, dict) else job
    name = (profile.get("full_name") or "").strip()
    skills = [s for s in (matched_skills or profile.get("skills") or []) if s][:6]
    education = (profile.get("education") or "").strip()
    headline = (profile.get("headline") or "").strip()

    intro = f"I am writing to apply for the {job.title} position"
    intro += f" at {job.company}." if job.company else "."
    if headline:
        intro += f" I am a {headline.rstrip('.')} looking to start my career in this field."
    paragraphs = [intro]
    if education:
        paragraphs.append(f"My educational background: {education.rstrip('.')}.")
    if skills:
        paragraphs.append(
            f"The skills I would bring to this role include {', '.join(skills[:-1]) + ' and ' + skills[-1] if len(skills) > 1 else skills[0]}, "
            "which match several requirements in your job description. I enjoy learning quickly and "
            "applying new tools to real problems."
        )
    paragraphs.append(
        f"I would welcome the chance to discuss how I can contribute to {job.company or 'your team'}. "
        "Thank you for your time and consideration."
    )
    signature = "Sincerely,\n" + (name or "")
    contact = " | ".join(x for x in (profile.get("email"), profile.get("phone")) if x)
    if contact:
        signature += "\n" + contact
    return "Dear Hiring Manager,\n\n" + "\n\n".join(paragraphs) + "\n\n" + signature.strip()


def generate_cover_letter(profile: dict, job: Job | dict, resume_text: str = "",
                          matched_skills: list[str] | None = None) -> str:
    """AI cover letter grounded in the saved profile, resume text and job description."""
    job = Job.from_dict(job) if isinstance(job, dict) else job
    prompt = (
        "Write a concise, professional cover letter (250-320 words) for this job. Use ONLY facts from the "
        "candidate information below; do not invent projects, employers, numbers or skills. Mention 2-3 "
        "relevant skills/projects that genuinely appear in the candidate information. No placeholders in "
        "square brackets. End with the candidate's name.\n\n"
        f"JOB TITLE: {job.title}\nCOMPANY: {job.company}\nJOB DESCRIPTION:\n{job.description[:4000]}\n\n"
        f"CANDIDATE NAME: {profile.get('full_name', '')}\nHEADLINE: {profile.get('headline', '')}\n"
        f"EDUCATION: {profile.get('education', '')}\nSUMMARY: {profile.get('summary', '')}\n"
        f"SKILLS THAT MATCH THE JOB: {', '.join(matched_skills or [])}\n"
        f"RESUME TEXT:\n{(resume_text or 'not provided')[:5000]}"
    )
    return ask(prompt, system=SYSTEM_BASE, max_tokens=900)
