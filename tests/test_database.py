"""Tests for SQLite operations, the application tracker and CSV export."""
import pytest

from config import settings
from database import db
from job_search.job_details import Job
from tracker import applications as tracker


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "test.db")
    db.init_db()


def make_job(title="Junior Python Developer", company="Acme", **kw) -> Job:
    return Job(title=title, company=company, description="Python SQL", url="https://example.com/job",
               source="Remotive", tags=["python"], **kw)


def test_init_db_is_idempotent_and_creates_tables():
    db.init_db()
    with db.get_connection() as conn:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"saved_jobs", "applications", "candidate_profile", "resume_info", "application_notes",
            "prep_history", "search_history", "found_jobs"} <= names


def test_save_job_does_not_duplicate_and_roundtrips_fields():
    job = make_job(remote=True)
    job_id, created = db.save_job(job.to_dict())
    again_id, created_again = db.save_job(job.to_dict())
    assert created and not created_again and job_id == again_id
    saved = db.get_saved_job(job_id)
    assert saved["title"] == job.title and saved["remote"] is True and saved["tags"] == ["python"]


def test_application_crud_and_status_update_logs_activity():
    app_id, job_id, created = tracker.track_job(make_job())
    assert created and db.get_application(app_id)["status"] == "Saved"
    assert tracker.save_application_changes(app_id, {
        "status": "Applied", "applied_date": "2026-11-02", "followup_date": "2026-11-09",
        "contact_name": "Priya", "contact_email": "priya@acme.com", "contact_phone": "+91 99999 11111",
        "notes": "Applied on the careers page"}) == []
    app = db.get_application(app_id)
    assert (app["status"], app["applied_date"], app["contact_name"]) == ("Applied", "2026-11-02", "Priya")
    notes = [n["note"] for n in db.list_notes(app_id)]
    assert any("Saved → Applied" in n for n in notes)


def test_track_job_twice_keeps_single_application():
    job = make_job()
    first, _, _ = tracker.track_job(job)
    second, _, created = tracker.track_job(job)
    assert first == second and not created and len(db.list_applications()) == 1


def test_invalid_status_and_fields_are_rejected():
    app_id, _, _ = tracker.track_job(make_job())
    with pytest.raises(ValueError):
        db.update_application(app_id, status="Hired!!")
    with pytest.raises(ValueError):
        db.update_application(app_id, job_id=5)           # not a whitelisted column
    problems = tracker.save_application_changes(app_id, {"status": "Applied", "contact_email": "nope"})
    assert any("email" in p.lower() for p in problems)


def test_sql_injection_text_is_stored_literally():
    nasty = "x'); DROP TABLE applications;--"
    app_id, _, _ = tracker.track_job(make_job(title=nasty))
    assert db.get_application(app_id)["title"] == nasty
    assert db.list_applications(search="DROP TABLE")        # still queryable, table still exists


def test_search_and_filter_applications():
    a, _, _ = tracker.track_job(make_job("Python Developer", "Acme"))
    b, _, _ = tracker.track_job(make_job("Data Analyst", "Globex"))
    db.update_application(b, status="Interview")
    assert [r["id"] for r in db.list_applications(status="Interview")] == [b]
    assert [r["id"] for r in db.list_applications(search="globex")] == [b]
    assert {r["id"] for r in db.list_applications("All", "")} == {a, b}


def test_notes_add_list_delete():
    app_id, _, _ = tracker.track_job(make_job())
    note_id = db.add_note(app_id, "Recruiter said to expect a call Friday")
    assert db.list_notes(app_id)[0]["note"].startswith("Recruiter")
    assert db.delete_note(note_id) and not db.delete_note(note_id)
    with pytest.raises(ValueError):
        db.add_note(app_id, "   ")


def test_delete_application_removes_job_and_notes():
    app_id, job_id, _ = tracker.track_job(make_job())
    db.add_note(app_id, "hello")
    assert db.delete_application(app_id)
    assert db.get_saved_job(job_id) is None and db.list_notes(app_id) == []
    assert not db.delete_application(app_id)


def test_profile_and_resume_persist_between_connections():
    assert db.get_profile()["full_name"] == "" and db.get_latest_resume() is None
    db.save_profile({"full_name": "Harsha", "email": "h@example.com"}, ["Python", "SQL"])
    db.save_profile({"headline": "CSE student"})              # partial update keeps earlier values
    profile = db.get_profile()
    assert (profile["full_name"], profile["headline"], profile["skills"]) == ("Harsha", "CSE student", ["Python", "SQL"])
    db.save_resume_info("cv.txt", "resume text", {"skills": ["Python"]})
    latest = db.get_latest_resume()
    assert latest["filename"] == "cv.txt" and latest["analysis"]["skills"] == ["Python"]


def test_dashboard_stats_come_from_real_data():
    empty = db.get_dashboard_stats()
    assert all(empty[k] == 0 for k in ("jobs_found", "saved_jobs", "submitted", "interviews", "offers", "rejected"))
    jobs = [make_job(f"Job {i}", f"Co{i}") for i in range(5)]
    db.record_found_jobs([j.to_dict() for j in jobs])
    db.record_found_jobs([jobs[0].to_dict()])                  # same job again is not double counted
    db.record_search("python", "Hyderabad", "", 5)
    ids = [tracker.track_job(j)[0] for j in jobs[:4]]
    db.update_application(ids[0], status="Applied")
    db.update_application(ids[1], status="Interview")
    db.update_application(ids[2], status="Offer")
    db.update_application(ids[3], status="Rejected")
    stats = db.get_dashboard_stats()
    assert stats["jobs_found"] == 5 and stats["saved_jobs"] == 4 and stats["searches"] == 1
    assert (stats["submitted"], stats["interviews"], stats["offers"], stats["rejected"]) == (4, 1, 1, 1)
    assert stats["status_counts"]["Applied"] == 1 and db.get_recent_activity()


def test_next_actions_reflect_state():
    stats = db.get_dashboard_stats()
    actions = tracker.recommend_next_actions(stats, db.get_profile(), has_resume=False, upcoming=[])
    assert any("Upload your resume" in a for a in actions) and any("first job search" in a for a in actions)


def test_manual_job_validation():
    app_id, job_id = tracker.add_manual_job("ML Intern", "Initech", "https://initech.example/jobs/1")
    assert db.get_application(app_id)["source"] == "Added manually"
    with pytest.raises(ValueError):
        tracker.add_manual_job("", "X")
    with pytest.raises(ValueError):
        tracker.add_manual_job("Dev", "X", "javascript:alert(1)")


def test_csv_export_neutralises_formulas():
    tracker.track_job(make_job(title="=HYPERLINK(\"http://evil\")", company="Acme"))
    csv_text = tracker.export_applications_csv(db.list_applications())
    assert csv_text.splitlines()[0].startswith("title,company")
    assert "'=HYPERLINK" in csv_text
