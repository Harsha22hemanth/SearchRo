"""Multi-source job search: Remotive + Arbeitnow public APIs.

Both are free, documented public APIs. Results are normalised into ``Job`` objects,
filtered, de-duplicated and sorted. A failing source never crashes the search; its error
is reported in ``SearchResult.errors`` instead.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests

from config import settings
from job_search import filters
from job_search.filters import SearchParams
from job_search.job_details import Job, normalize_arbeitnow, normalize_remotive
from utils.helpers import get_logger

log = get_logger("search")


class JobSourceError(RuntimeError):
    """A job source could not be reached or returned unusable data."""


@dataclass
class SearchResult:
    jobs: list[Job] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)   # raw jobs fetched per source
    fetched_total: int = 0                                         # before filters / dedupe


def _get_json(url: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(url, params=params, headers=settings.HTTP_HEADERS, timeout=settings.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except requests.Timeout as exc:
        raise JobSourceError(f"timed out after {settings.REQUEST_TIMEOUT:g}s") from exc
    except requests.HTTPError as exc:
        raise JobSourceError(f"HTTP {exc.response.status_code if exc.response is not None else 'error'}") from exc
    except requests.RequestException as exc:
        raise JobSourceError("network error (check your internet connection)") from exc
    except ValueError as exc:
        raise JobSourceError("returned data that is not valid JSON") from exc
    if not isinstance(data, dict):
        raise JobSourceError("returned an unexpected response format")
    return data


def fetch_remotive(params: SearchParams) -> list[Job]:
    terms = filters.essential_terms(params.query) + [s for s in params.skills if s.strip()][:1]
    query = {"limit": 100}
    if terms:
        query["search"] = " ".join(terms[:3])
    data = _get_json(settings.REMOTIVE_API_URL, query)
    items = data.get("jobs")
    if not isinstance(items, list):
        raise JobSourceError("response did not contain a 'jobs' list")
    return [j for j in (normalize_remotive(i) for i in items if isinstance(i, dict)) if j]


def fetch_arbeitnow(params: SearchParams) -> list[Job]:
    jobs: list[Job] = []
    for page in range(1, settings.ARBEITNOW_MAX_PAGES + 1):
        try:
            data = _get_json(settings.ARBEITNOW_API_URL, {"page": page})
        except JobSourceError:
            if jobs:     # keep what we already have if a later page fails
                break
            raise
        items = data.get("data")
        if not isinstance(items, list):
            raise JobSourceError("response did not contain a 'data' list")
        jobs.extend(j for j in (normalize_arbeitnow(i) for i in items if isinstance(i, dict)) if j)
        if not (data.get("links") or {}).get("next"):
            break
    return jobs


SOURCES = {"Remotive": fetch_remotive, "Arbeitnow": fetch_arbeitnow}


def search_jobs(params: SearchParams, sources: dict | None = None) -> SearchResult:
    """Query every source in parallel, then filter, de-duplicate and sort the combined results."""
    sources = sources if sources is not None else SOURCES
    result = SearchResult()
    collected: list[Job] = []

    def run(name: str, fn):
        try:
            return name, fn(params), None
        except JobSourceError as exc:
            return name, [], str(exc)
        except Exception:  # noqa: BLE001 - one broken source must never take the app down
            log.exception("Unexpected error in source %s", name)
            return name, [], "unexpected error (see data/searchro.log)"

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        outcomes = list(pool.map(lambda item: run(*item), sources.items()))

    for name, jobs, error in outcomes:
        if error:
            result.errors[name] = error
            log.warning("Source %s failed: %s", name, error)
        else:
            result.source_counts[name] = len(jobs)
            collected.extend(jobs)

    result.fetched_total = len(collected)
    filtered = filters.apply_filters(collected, params)
    result.jobs = filters.sort_jobs(filters.deduplicate_jobs(filtered), params)
    log.info("Search finished: fetched=%d kept=%d errors=%d", result.fetched_total, len(result.jobs), len(result.errors))
    return result
