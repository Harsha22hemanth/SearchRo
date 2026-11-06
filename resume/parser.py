"""Extract plain text from uploaded PDF, DOCX and TXT resumes."""
from __future__ import annotations

import io
import re
from pathlib import Path

from utils.helpers import get_logger
from utils.validators import validate_resume_upload

log = get_logger("resume.parser")


class ResumeParseError(ValueError):
    """The resume could not be read. The message is safe to show to the user."""


def _from_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise ResumeParseError("This PDF is password protected. Remove the password and try again.")
            except ResumeParseError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ResumeParseError("This PDF is encrypted and cannot be read.") from exc
        pages = [(page.extract_text() or "") for page in reader.pages]
    except ResumeParseError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError, TypeError) as exc:
        raise ResumeParseError("Could not read this PDF. It may be corrupted.") from exc
    return "\n".join(pages)


def _from_docx(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - python-docx raises several unrelated types
        raise ResumeParseError("Could not read this DOCX file. It may be corrupted.") from exc
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell.text not in cells:
                    cells.append(cell.text)
            lines.append("  ".join(c.strip() for c in cells if c.strip()))
    return "\n".join(lines)


def _from_txt(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ResumeParseError("Could not decode this text file.")


def extract_text(filename: str, data: bytes) -> str:
    """Validate the upload, extract its text, and return it normalised."""
    ok, message = validate_resume_upload(filename, data)
    if not ok:
        raise ResumeParseError(message)
    ext = Path(filename).suffix.lower()
    text = {".pdf": _from_pdf, ".docx": _from_docx, ".txt": _from_txt}[ext](data)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    if len(text) < 30:
        raise ResumeParseError(
            "Almost no text could be extracted. If this is a scanned/image PDF, export a text-based "
            "version (OCR is not supported)."
        )
    log.info("Parsed resume: type=%s chars=%d", ext, len(text))   # never log the content itself
    return text
