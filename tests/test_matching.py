"""Tests for resume parsing/analysis and resume-to-job matching (no API key needed)."""
import io

import pytest
from docx import Document

from job_search.job_details import Job
from resume.analyzer import analyze_resume, resume_quality_report
from resume.matcher import compare_jobs, match_resume_to_job
from resume.parser import ResumeParseError, extract_text

RESUME = """HARSHA KUMAR
Hyderabad | harsha@example.com | +91 98765 43210
github.com/harsha1922

SKILLS
Python, Java, SQL, MySQL, Git, Flask, REST APIs

PROJECTS
Online Bookstore
• Built a Flask and MySQL web app with 200+ books
• Implemented login and a shopping cart

EDUCATION
B.Tech Computer Science and Engineering, CGPA 8.2

CERTIFICATIONS
• Python for Data Science
"""

PY_JOB = Job(title="Junior Python Developer", company="Acme",
             description="We need Python, Django, SQL and REST APIs experience. Use Git and Docker.")
JAVA_JOB = Job(title="Senior Java Engineer", company="Beta",
               description="Java, Spring Boot, Kubernetes, AWS and microservices. 6+ years of experience.")


@pytest.fixture
def analysis():
    return analyze_resume(RESUME)


def test_analyzer_extracts_contact_details(analysis):
    assert analysis["name"] == "Harsha Kumar"
    assert analysis["email"] == "harsha@example.com"
    assert analysis["phone"] == "+91 98765 43210"
    assert any("github.com" in link for link in analysis["links"])


def test_analyzer_extracts_skills_and_sections(analysis):
    assert {"Python", "Java", "SQL", "MySQL", "Git", "Flask", "REST APIs"} <= set(analysis["skills"])
    assert "Python" in analysis["languages"] and "Flask" in analysis["frameworks"]
    assert "MySQL" in analysis["databases"] and "Git" in analysis["tools"]
    assert len(analysis["projects"]) == 1 and "Bookstore" in analysis["projects"][0]
    assert analysis["education"] and analysis["certifications"] == ["Python for Data Science"]
    assert analysis["experience"] == []          # nothing is invented


def test_analyzer_does_not_fabricate_for_empty_text():
    result = analyze_resume("just some words without structure")
    assert result["name"] == "" and result["email"] == "" and result["phone"] == ""
    assert result["skills"] == [] and result["projects"] == []


def test_quality_report_scores_and_tips(analysis):
    report = resume_quality_report(RESUME, analysis)
    assert 0 <= report["score"] <= 100
    assert isinstance(report["tips"], list)


def test_parse_txt_and_docx_give_same_text():
    txt = extract_text("resume.txt", RESUME.encode())
    doc = Document()
    for line in RESUME.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    docx_text = extract_text("resume.docx", buf.getvalue())
    assert analyze_resume(txt)["skills"] == analyze_resume(docx_text)["skills"]


def test_parser_rejects_bad_uploads():
    with pytest.raises(ResumeParseError):
        extract_text("resume.exe", b"abc")
    with pytest.raises(ResumeParseError):
        extract_text("resume.pdf", b"not a pdf")
    with pytest.raises(ResumeParseError):
        extract_text("resume.txt", b"")
    with pytest.raises(ResumeParseError):
        extract_text("resume.pdf", b"%PDF-1.4 garbage that is not a real pdf")


def test_match_python_job_scores_higher_than_senior_java(analysis):
    py = match_resume_to_job(analysis["skills"], RESUME, PY_JOB)
    java = match_resume_to_job(analysis["skills"], RESUME, JAVA_JOB)
    assert py.overall > java.overall
    assert {"Python", "SQL", "REST APIs", "Git"} <= set(py.matched_skills)
    assert {"Django", "Docker"} <= set(py.missing_skills)
    assert 0 <= py.overall <= 100 and py.label in ("Strong overlap", "Moderate overlap", "Low overlap")


def test_match_suggestions_mention_missing_skills_and_experience(analysis):
    py = match_resume_to_job(analysis["skills"], RESUME, PY_JOB)
    assert any("Django" in tip for tip in py.suggestions)
    java = match_resume_to_job(analysis["skills"], RESUME, JAVA_JOB)
    assert any("6+ years" in tip for tip in java.suggestions)


def test_match_uses_edited_skill_list():
    base = match_resume_to_job(["Python"], RESUME, PY_JOB)
    more = match_resume_to_job(["Python", "Django", "Docker", "SQL", "Git", "REST APIs"], RESUME, PY_JOB)
    assert more.overall > base.overall and more.missing_skills == []


def test_match_empty_resume_is_low_not_crashing():
    result = match_resume_to_job([], "", PY_JOB)
    assert result.overall < 30 and result.matched_skills == []


def test_match_job_without_known_skills_reweights():
    job = Job(title="Office Assistant", description="Answer phones and greet visitors politely.")
    result = match_resume_to_job(["Python"], RESUME, job)
    assert result.skill_score is None and "skills" not in result.weights_used
    assert abs(sum(result.weights_used.values()) - 1) < 0.02


def test_match_accepts_dicts_and_compare_sorts_best_first(analysis):
    ranked = compare_jobs(analysis["skills"], RESUME, [JAVA_JOB.to_dict(), PY_JOB.to_dict()])
    assert ranked[0][0].title == PY_JOB.title
    assert ranked[0][1].overall >= ranked[1][1].overall
