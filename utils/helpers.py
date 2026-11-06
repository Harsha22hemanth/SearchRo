"""General helpers: logging, text utilities, skill detection, CSV export."""
from __future__ import annotations

import csv
import html
import io
import logging
import re
from datetime import date, datetime, timezone
from functools import lru_cache
from logging.handlers import RotatingFileHandler

from config import settings

# ------------------------------------------------------------------ logging
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


class RedactingFilter(logging.Filter):
    """Removes API keys from log messages before they are written."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = _SECRET_RE.sub("[REDACTED]", message)
        key = settings.get_openai_key()
        if key:
            message = message.replace(key, "[REDACTED]")
        record.msg, record.args = message, ()
        return True


def setup_logging() -> logging.Logger:
    """Configure the 'searchro' logger once (file + console). Never logs resume contents."""
    logger = logging.getLogger("searchro")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    try:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(settings.LOG_PATH, maxBytes=500_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # logging to file is optional
    logger.addFilter(RedactingFilter())
    for handler in logger.handlers:
        handler.addFilter(RedactingFilter())
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"searchro.{name}")


# ------------------------------------------------------------------ text helpers
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(text: str) -> str:
    """'Python Developer / ML' -> 'python-developer-ml' (ASCII only)."""
    text = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return text.strip("-")


def strip_html(raw: str) -> str:
    """Convert simple HTML into readable plain text."""
    if not raw:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|ul|ol|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n\s*\n(?=•)", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_date_to_iso(value: object) -> str:
    """Accept ISO strings or unix timestamps; return 'YYYY-MM-DD' or ''."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
        text = str(value).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ""


def days_until(value: str | None, today: date | None = None) -> int | None:
    from utils.validators import parse_iso_date

    d = parse_iso_date(value)
    if d is None:
        return None
    return (d - (today or date.today())).days


_STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being below between both but
    by can could did do does doing down during each few for from further had has have having he her here hers him his
    how i if in into is it its just me more most my no nor not now of off on once only or other our out over own same
    she should so some such than that the their them then there these they this those through to too under until up
    very was we were what when where which while who whom why will with would you your yours able across etc via
    team work working company role job position candidate candidates join looking opportunity ability strong good
    experience years year including include required requirements responsibilities skills must new using use well
    will be plus preferred minimum etc excellent understanding knowledge environment business customers customer
    people great help best need needs build develop developing building features services ensure support""".split()
)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", text or "")]


def keywords(text: str) -> list[str]:
    """Lower-case content words (no stopwords, length >= 3)."""
    return [t for t in tokenize(text) if len(t) >= 3 and t not in _STOPWORDS]


# ------------------------------------------------------------------ skills detection
@lru_cache(maxsize=1)
def _skill_patterns() -> tuple[tuple[str, str, re.Pattern], ...]:
    patterns = []
    for category, skills in settings.SKILL_CATEGORIES.items():
        for canonical, aliases in skills.items():
            names = sorted({canonical.lower(), *[a.lower() for a in aliases]}, key=len, reverse=True)
            body = "|".join(re.escape(n) for n in names)
            regex = re.compile(r"(?<![A-Za-z0-9+#.])(?:" + body + r")(?![A-Za-z0-9+#])", re.IGNORECASE)
            patterns.append((category, canonical, regex))
    return tuple(patterns)


def find_skills(text: str) -> dict[str, list[str]]:
    """Return {category: [skills]} for every vocabulary skill that appears in the text."""
    found: dict[str, list[str]] = {}
    if not text:
        return found
    for category, canonical, regex in _skill_patterns():
        if regex.search(text):
            found.setdefault(category, []).append(canonical)
    return found


def flat_skills(text: str) -> list[str]:
    return sorted({s for group in find_skills(text).values() for s in group}, key=str.lower)


def all_known_skills() -> list[str]:
    return sorted({s for group in settings.SKILL_CATEGORIES.values() for s in group}, key=str.lower)


def parse_skill_list(raw: str) -> list[str]:
    """Split a comma/newline separated skills string, de-duplicating case-insensitively."""
    seen: dict[str, str] = {}
    for part in re.split(r"[,\n;]", raw or ""):
        item = part.strip()
        if item and item.lower() not in seen:
            seen[item.lower()] = item[:60]
    return list(seen.values())


# ------------------------------------------------------------------ CSV export
def safe_csv_cell(value: object) -> str:
    """Neutralise spreadsheet formula injection (cells starting with = + - @)."""
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def rows_to_csv(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([safe_csv_cell(row.get(col, "")) for col in columns])
    return buffer.getvalue()
