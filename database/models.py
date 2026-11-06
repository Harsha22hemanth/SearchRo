"""Database schema and small row helpers."""
from __future__ import annotations

import sqlite3

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS candidate_profile (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        full_name TEXT DEFAULT '',
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        location TEXT DEFAULT '',
        headline TEXT DEFAULT '',
        education TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        linkedin_url TEXT DEFAULT '',
        github_url TEXT DEFAULT '',
        skills_json TEXT DEFAULT '[]',
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        raw_text TEXT NOT NULL,
        analysis_json TEXT DEFAULT '{}',
        uploaded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS found_jobs (
        job_key TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        company TEXT DEFAULT '',
        source TEXT DEFAULT '',
        first_seen TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_key TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        company TEXT DEFAULT '',
        location TEXT DEFAULT '',
        country TEXT DEFAULT '',
        url TEXT DEFAULT '',
        source TEXT DEFAULT '',
        description TEXT DEFAULT '',
        job_type TEXT DEFAULT '',
        experience_level TEXT DEFAULT '',
        remote INTEGER DEFAULT 0,
        posted_date TEXT DEFAULT '',
        tags_json TEXT DEFAULT '[]',
        saved_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL REFERENCES saved_jobs(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'Saved',
        applied_date TEXT DEFAULT '',
        interview_date TEXT DEFAULT '',
        followup_date TEXT DEFAULT '',
        contact_name TEXT DEFAULT '',
        contact_email TEXT DEFAULT '',
        contact_phone TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS application_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
        note TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT DEFAULT '',
        location TEXT DEFAULT '',
        filters TEXT DEFAULT '',
        results_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prep_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER REFERENCES saved_jobs(id) ON DELETE SET NULL,
        kind TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)",
    "CREATE INDEX IF NOT EXISTS idx_notes_app ON application_notes(application_id)",
]

APPLICATION_UPDATE_FIELDS = (
    "status", "applied_date", "interview_date", "followup_date",
    "contact_name", "contact_email", "contact_phone", "notes",
)
PROFILE_FIELDS = (
    "full_name", "email", "phone", "location", "headline", "education",
    "summary", "linkedin_url", "github_url",
)


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
