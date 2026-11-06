"""Naukri.com search-link generator.

IMPORTANT: this is NOT an API integration. Naukri has no public job API, and SearchRo does not
scrape it. It builds a normal public search page URL that opens in your browser.

The URL formats live in ``config/settings.py`` (and can be overridden in ``.env``) so you can
update them quickly if Naukri changes its URL structure.
"""
from __future__ import annotations

from config import settings
from utils.helpers import slugify
from utils.validators import clean_text

LIMITATION_NOTE = (
    "Naukri has no public job API, so jobs can't be listed inside SearchRo. The button opens a "
    "Naukri search for your role and location in a new tab."
)


def build_naukri_url(role: str, location: str = "", fresher: bool = False) -> str:
    role_slug = slugify(clean_text(role, 120))
    if fresher and role_slug and "fresher" not in role_slug:
        role_slug += "-fresher"
    location_slug = slugify(clean_text(location, 120))
    templates = settings.NAUKRI_URL_TEMPLATES

    if role_slug and location_slug:
        key, values = "role_location", {"role": role_slug, "location": location_slug}
    elif role_slug:
        key, values = "role_only", {"role": role_slug}
    elif location_slug:
        key, values = "location_only", {"location": location_slug}
    else:
        return settings.NAUKRI_FALLBACK_URL
    try:
        return templates[key].format(**values)
    except (KeyError, IndexError, ValueError):
        return settings.NAUKRI_FALLBACK_URL
