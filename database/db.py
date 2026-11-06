"""SQLite access layer. Every query is parameterised."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterator

from config import settings
from database.models import (
    APPLICATION_UPDATE_FIELDS, PROFILE_FIELDS, SCHEMA_STATEMENTS, row_to_dict,
)
from utils.helpers import get_logger, now_iso
from utils.validators import validate_status

log = get_logger("db")


class DatabaseError(RuntimeError):
    """Raised for any database failure, with a message safe to show the user."""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = None
    try:
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        log.error("Database error: %s", exc)
        raise DatabaseError(f"Database error: {exc}") from exc
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def init_db() -> None:
    """Create all tables if they do not exist yet (safe to call on every start)."""
    with get_connection() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)


# ------------------------------------------------------------------ search history / found jobs
def record_search(query: str, location: str, filters: str, results_count: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO search_history (query, location, filters, results_count, created_at) VALUES (?,?,?,?,?)",
            (query, location, filters, int(results_count), now_iso()),
        )
        return int(cur.lastrowid)


def get_search_history(limit: int = 15) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM search_history ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [dict(r) for r in rows]


def record_found_jobs(jobs: list[dict]) -> int:
    """Remember every distinct job seen in searches. Returns how many were new."""
    new = 0
    with get_connection() as conn:
        for job in jobs:
            cur = conn.execute(
                "INSERT OR IGNORE INTO found_jobs (job_key, title, company, source, first_seen) VALUES (?,?,?,?,?)",
                (job["job_key"], job.get("title", ""), job.get("company", ""), job.get("source", ""), now_iso()),
            )
            new += cur.rowcount
    return new


# ------------------------------------------------------------------ saved jobs
def _job_row_values(job: dict) -> tuple:
    return (
        job["job_key"], job.get("title", ""), job.get("company", ""), job.get("location", ""),
        job.get("country", ""), job.get("url", ""), job.get("source", ""), job.get("description", ""),
        job.get("job_type", ""), job.get("experience_level", ""), 1 if job.get("remote") else 0,
        job.get("posted_date", ""), json.dumps(list(job.get("tags") or [])), now_iso(),
    )


def save_job(job: dict) -> tuple[int, bool]:
    """Save a job. Returns (saved_job_id, created). Existing jobs are not duplicated."""
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM saved_jobs WHERE job_key = ?", (job["job_key"],)).fetchone()
        if existing:
            return int(existing["id"]), False
        cur = conn.execute(
            """INSERT INTO saved_jobs (job_key, title, company, location, country, url, source, description,
               job_type, experience_level, remote, posted_date, tags_json, saved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            _job_row_values(job),
        )
        return int(cur.lastrowid), True


def _saved_job_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    data["remote"] = bool(data["remote"])
    return data


def get_saved_job(job_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM saved_jobs WHERE id = ?", (job_id,)).fetchone()
    return _saved_job_from_row(row) if row else None


def list_saved_jobs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM saved_jobs ORDER BY id DESC").fetchall()
    return [_saved_job_from_row(r) for r in rows]


def saved_job_keys() -> set[str]:
    with get_connection() as conn:
        return {r["job_key"] for r in conn.execute("SELECT job_key FROM saved_jobs")}


def delete_saved_job(job_id: int) -> bool:
    with get_connection() as conn:
        return conn.execute("DELETE FROM saved_jobs WHERE id = ?", (job_id,)).rowcount > 0


# ------------------------------------------------------------------ applications
def create_application(job_id: int, status: str = "Saved") -> int:
    validate_status(status)
    ts = now_iso()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO applications (job_id, status, created_at, updated_at) VALUES (?,?,?,?)",
            (job_id, status, ts, ts),
        )
        app_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO application_notes (application_id, note, created_at) VALUES (?,?,?)",
            (app_id, f"[status] Added to tracker as {status}", ts),
        )
    return app_id


def get_application_for_job(job_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ? ORDER BY id LIMIT 1", (job_id,)
        ).fetchone()
    return row_to_dict(row)


_APP_SELECT = """
    SELECT a.*, j.title, j.company, j.location, j.url, j.source, j.job_key
    FROM applications a JOIN saved_jobs j ON j.id = a.job_id
"""


def get_application(app_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(_APP_SELECT + " WHERE a.id = ?", (app_id,)).fetchone()
    return row_to_dict(row)


def list_applications(status: str | None = None, search: str = "") -> list[dict]:
    sql, params = _APP_SELECT + " WHERE 1=1", []
    if status and status != "All":
        sql += " AND a.status = ?"
        params.append(status)
    term = (search or "").strip()
    if term:
        like = f"%{term.lower()}%"
        sql += (" AND (LOWER(j.title) LIKE ? OR LOWER(j.company) LIKE ? OR LOWER(a.notes) LIKE ?"
                " OR LOWER(a.contact_name) LIKE ? OR LOWER(j.location) LIKE ?)")
        params.extend([like] * 5)
    sql += " ORDER BY a.updated_at DESC, a.id DESC"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_application(app_id: int, **fields: str) -> bool:
    """Update whitelisted columns. Changing the status writes an activity note."""
    unknown = set(fields) - set(APPLICATION_UPDATE_FIELDS)
    if unknown:
        raise ValueError(f"Unknown application fields: {', '.join(sorted(unknown))}")
    if not fields:
        return False
    if "status" in fields:
        validate_status(fields["status"])
    with get_connection() as conn:
        current = conn.execute("SELECT status FROM applications WHERE id = ?", (app_id,)).fetchone()
        if current is None:
            return False
        ts = now_iso()
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(
            f"UPDATE applications SET {assignments}, updated_at = ? WHERE id = ?",
            (*fields.values(), ts, app_id),
        )
        if "status" in fields and fields["status"] != current["status"]:
            conn.execute(
                "INSERT INTO application_notes (application_id, note, created_at) VALUES (?,?,?)",
                (app_id, f"[status] {current['status']} → {fields['status']}", ts),
            )
    return True


def delete_application(app_id: int, delete_job: bool = True) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT job_id FROM applications WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            return False
        if delete_job:
            conn.execute("DELETE FROM saved_jobs WHERE id = ?", (row["job_id"],))  # cascades
        else:
            conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    return True


# ------------------------------------------------------------------ notes
def add_note(app_id: int, note: str) -> int:
    text = (note or "").strip()
    if not text:
        raise ValueError("Note cannot be empty.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO application_notes (application_id, note, created_at) VALUES (?,?,?)",
            (app_id, text[:2000], now_iso()),
        )
        conn.execute("UPDATE applications SET updated_at = ? WHERE id = ?", (now_iso(), app_id))
        return int(cur.lastrowid)


def list_notes(app_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM application_notes WHERE application_id = ? ORDER BY id DESC", (app_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_note(note_id: int) -> bool:
    with get_connection() as conn:
        return conn.execute("DELETE FROM application_notes WHERE id = ?", (note_id,)).rowcount > 0


# ------------------------------------------------------------------ candidate profile / resume
def get_profile() -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM candidate_profile WHERE id = 1").fetchone()
    if row is None:
        return {**{f: "" for f in PROFILE_FIELDS}, "skills": []}
    data = dict(row)
    data["skills"] = json.loads(data.pop("skills_json") or "[]")
    return data


def save_profile(profile: dict, skills: list[str] | None = None) -> None:
    current = get_profile()
    values = {f: str(profile.get(f, current.get(f, "")) or "") for f in PROFILE_FIELDS}
    skill_list = list(skills) if skills is not None else current["skills"]
    with get_connection() as conn:
        conn.execute(
            f"""INSERT INTO candidate_profile (id, {', '.join(PROFILE_FIELDS)}, skills_json, updated_at)
                VALUES (1, {', '.join('?' for _ in PROFILE_FIELDS)}, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                {', '.join(f'{f}=excluded.{f}' for f in PROFILE_FIELDS)},
                skills_json=excluded.skills_json, updated_at=excluded.updated_at""",
            (*values.values(), json.dumps(skill_list), now_iso()),
        )


def save_resume_info(filename: str, raw_text: str, analysis: dict) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO resume_info (filename, raw_text, analysis_json, uploaded_at) VALUES (?,?,?,?)",
            (filename, raw_text, json.dumps(analysis), now_iso()),
        )
        return int(cur.lastrowid)


def get_latest_resume() -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM resume_info ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    data = dict(row)
    data["analysis"] = json.loads(data.pop("analysis_json") or "{}")
    return data


# ------------------------------------------------------------------ prep history
def add_prep_history(kind: str, content: str, job_id: int | None = None) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO prep_history (job_id, kind, content, created_at) VALUES (?,?,?,?)",
            (job_id, kind, content, now_iso()),
        )
        return int(cur.lastrowid)


def list_prep_history(job_id: int | None = None, limit: int = 20) -> list[dict]:
    sql, params = "SELECT * FROM prep_history", []
    if job_id is not None:
        sql += " WHERE job_id = ?"
        params.append(job_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ------------------------------------------------------------------ dashboard
def get_status_counts() -> dict[str, int]:
    counts = {s: 0 for s in settings.APPLICATION_STATUSES}
    with get_connection() as conn:
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM applications GROUP BY status"):
            counts[row["status"]] = row["n"]
    return counts


def get_dashboard_stats() -> dict:
    submitted = ", ".join(f"'{s}'" for s in settings.SUBMITTED_STATUSES)  # constants, not user input
    with get_connection() as conn:
        one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0]  # noqa: E731
        stats = {
            "jobs_found": one("SELECT COUNT(*) FROM found_jobs"),
            "saved_jobs": one("SELECT COUNT(*) FROM saved_jobs"),
            "applications_total": one("SELECT COUNT(*) FROM applications"),
            "submitted": one(
                f"SELECT COUNT(*) FROM applications WHERE status IN ({submitted}) "
                "OR (applied_date IS NOT NULL AND applied_date != '')"
            ),
            "interviews": one(
                "SELECT COUNT(*) FROM applications WHERE status = 'Interview' OR "
                "(interview_date != '' AND status NOT IN ('Rejected','Withdrawn'))"
            ),
            "offers": one("SELECT COUNT(*) FROM applications WHERE status = 'Offer'"),
            "rejected": one("SELECT COUNT(*) FROM applications WHERE status = 'Rejected'"),
            "searches": one("SELECT COUNT(*) FROM search_history"),
        }
    stats["status_counts"] = get_status_counts()
    return stats


def get_recent_activity(limit: int = 8) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT n.created_at, n.note, j.title, j.company
               FROM application_notes n
               JOIN applications a ON a.id = n.application_id
               JOIN saved_jobs j ON j.id = a.job_id
               ORDER BY n.id DESC LIMIT ?""",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_upcoming_dates(days: int = 7) -> list[dict]:
    """Interviews and follow-ups due within `days` (or already overdue for follow-ups)."""
    horizon = (date.today() + timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    items: list[dict] = []
    with get_connection() as conn:
        rows = conn.execute(
            _APP_SELECT + " WHERE a.status NOT IN ('Rejected','Withdrawn','Offer')"
        ).fetchall()
    for row in rows:
        r = dict(row)
        if r["interview_date"] and today <= r["interview_date"] <= horizon:
            items.append({"kind": "interview", "date": r["interview_date"], "app": r})
        if r["followup_date"] and r["followup_date"] <= horizon:
            items.append({"kind": "followup", "date": r["followup_date"], "app": r})
    return sorted(items, key=lambda i: i["date"])
