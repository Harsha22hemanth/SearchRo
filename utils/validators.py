"""Input validation helpers."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from config import settings

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def clean_text(value: object, max_len: int = 500) -> str:
    """Return a stripped string with control characters removed and a length cap."""
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
    return text[:max_len]


def is_valid_email(value: str) -> bool:
    return bool(value) and bool(_EMAIL_RE.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return 7 <= len(digits) <= 15 and bool(re.fullmatch(r"[+\d\s().\-]+", value.strip()))


def is_valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_iso_date(value: object) -> date | None:
    """Parse 'YYYY-MM-DD' (or a date/datetime) into a date; None when blank/invalid."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def validate_status(status: str) -> str:
    if status not in settings.APPLICATION_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Choose one of: {', '.join(settings.APPLICATION_STATUSES)}")
    return status


def validate_resume_upload(filename: str, data: bytes) -> tuple[bool, str]:
    """Check extension, size and file signature of an uploaded resume."""
    ext = Path(filename or "").suffix.lower()
    if ext not in settings.ALLOWED_RESUME_EXTENSIONS:
        return False, f"Unsupported file type '{ext or 'unknown'}'. Please upload a PDF, DOCX or TXT file."
    if not data:
        return False, "The uploaded file is empty."
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        return False, f"File is larger than {settings.MAX_UPLOAD_MB} MB."
    if ext == ".pdf" and not data.lstrip()[:5] == b"%PDF-":
        return False, "This file does not look like a valid PDF."
    if ext == ".docx" and not data[:2] == b"PK":
        return False, "This file does not look like a valid DOCX document."
    if ext == ".txt" and b"\x00" in data[:2048]:
        return False, "This file does not look like a plain-text file."
    return True, ""


def validate_search_query(query: str, max_len: int = 120) -> str:
    return clean_text(query, max_len)
