"""LinkedIn Jobs search-link generator.

IMPORTANT: this is NOT an API integration. LinkedIn offers no public job-search API for
individual users, and scraping it (especially behind a login) violates its terms. SearchRo
therefore only builds a normal public search URL that opens in your own browser, where you
can log in and apply as usual.
"""
from __future__ import annotations

from urllib.parse import urlencode, quote

from config import settings
from utils.validators import clean_text

LIMITATION_NOTE = (
    "LinkedIn has no public job-search API, so SearchRo can't list LinkedIn jobs inside the app. "
    "The button opens a LinkedIn Jobs search with your keywords and location in a new tab."
)


def build_linkedin_url(role: str, location: str = "", entry_level: bool = False, remote: bool = False) -> str:
    """Return https://www.linkedin.com/jobs/search/?keywords=ROLE&location=LOCATION (URL encoded).

    ``entry_level`` and ``remote`` add the widely used ``f_E`` / ``f_WT`` filter parameters.
    Those two are not officially documented by LinkedIn, so they are optional and off by default.
    """
    params: dict[str, str] = {"keywords": clean_text(role, 120)}
    if clean_text(location, 120):
        params["location"] = clean_text(location, 120)
    if entry_level:
        params["f_E"] = "1,2"   # 1 = internship, 2 = entry level
    if remote:
        params["f_WT"] = "2"    # 2 = remote
    return f"{settings.LINKEDIN_JOBS_URL}?{urlencode(params, quote_via=quote)}"
