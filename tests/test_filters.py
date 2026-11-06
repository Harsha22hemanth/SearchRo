"""Tests for entry-level filtering, duplicate removal, URL generation and resilient searching."""
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from config import settings
from job_search import search as search_module
from job_search.filters import (
    SearchParams, apply_filters, classify_experience, deduplicate_jobs, fresher_signals, is_fresher_friendly,
    sort_jobs,
)
from job_search.job_details import Job, normalize_arbeitnow, normalize_remotive
from job_search.linkedin import build_linkedin_url
from job_search.naukri import build_naukri_url


def job(title, company="Acme", description="", **kw) -> Job:
    return Job(title=title, company=company, description=description, **kw)


# ------------------------------------------------------------------ entry-level filtering
@pytest.mark.parametrize("j", [
    job("Junior Python Developer"),
    job("Graduate Trainee Engineer"),
    job("Software Engineering Intern"),
    job("Associate Software Engineer"),
    job("Python Developer", description="Freshers welcome to apply."),
    job("Data Analyst", description="0-1 years of experience required."),
])
def test_entry_level_jobs_are_detected(j):
    assert is_fresher_friendly(j) and classify_experience(j) == "Entry-level"


@pytest.mark.parametrize("j", [
    job("Senior Python Developer"),
    job("Lead Data Engineer", description="Fresher friendly team"),          # senior title wins
    job("Python Developer", description="Requires 5+ years of experience in Python."),
    job("Junior Developer", description="Minimum 3 years of professional experience."),
    job("Python Developer", description="Build APIs with Django."),            # no signal either way
])
def test_non_entry_level_jobs_are_not_labelled_fresher(j):
    assert not is_fresher_friendly(j)


def test_fresher_signals_explain_decision():
    sig = fresher_signals(job("Junior Developer", description="3+ years of experience needed"))
    assert "junior" in sig["positives"] and any("3+" in b for b in sig["blockers"]) and not sig["is_entry_level"]


def test_experience_level_classification():
    assert classify_experience(job("Senior Engineer")) == "Senior"
    assert classify_experience(job("Developer", description="2 years of experience")) == "Mid-level"
    assert classify_experience(job("Developer", description="Nice team")) == "Unspecified"


def test_fresher_only_filter_removes_other_jobs():
    jobs = [job("Junior Python Developer", description="python"), job("Senior Python Developer", description="python"),
            job("Python Developer", company="B", description="python, 4 years of experience")]
    kept = apply_filters(jobs, SearchParams(query="python", fresher_only=True))
    assert [j.title for j in kept] == ["Junior Python Developer"]


def test_other_filters():
    jobs = [job("Python Dev", "A", "python", remote=True, location="Worldwide", job_type="Full-time"),
            job("Python Dev", "B", "python", remote=False, location="Berlin, Germany", job_type="Contract"),
            job("Python Intern", "C", "python", location="Hyderabad, India")]
    p = lambda **k: [j.company for j in apply_filters([Job.from_dict(x.to_dict()) for x in jobs], SearchParams(query="python", **k))]  # noqa: E731
    assert p(work_mode="Remote") == ["A"]
    assert p(work_mode="Onsite") == ["B", "C"]
    assert p(employment_type="Contract") == ["B"]
    assert p(employment_type="Internship") == ["C"]
    assert p(company="b") == ["B"]
    assert p(country="Germany") == ["A", "B"]          # worldwide remote jobs also match any country
    assert p(location="hyderabad") == ["A", "C"]


def test_query_requires_specific_terms_but_ignores_generic_words():
    jobs = [job("Python Developer", description="python"), job("Java Developer", description="java")]
    assert [j.title for j in apply_filters(jobs, SearchParams(query="python developer"))] == ["Python Developer"]
    assert len(apply_filters(jobs, SearchParams(query="developer"))) == 2


def test_skills_filter_matches_any_listed_skill():
    jobs = [job("Developer", description="uses SQL"), job("Developer", "B", "uses Excel")]
    assert [j.company for j in apply_filters(jobs, SearchParams(skills=["sql", "python"]))] == ["Acme"]


def test_sorting_by_relevance_and_date():
    jobs = [job("Developer", "A", "python", posted_date="2026-11-05"),
            job("Python Developer", "B", "python python", posted_date="2026-10-01")]
    assert sort_jobs(jobs, SearchParams(query="python"))[0].company == "B"
    assert sort_jobs(jobs, SearchParams(query="python", sort_by="Newest"))[0].company == "A"


# ------------------------------------------------------------------ duplicate removal
def test_duplicates_removed_by_title_and_company_across_sources():
    a = job("Python Developer", "Acme", "short", source="Remotive", url="https://a.example/1")
    b = job("Python  Developer!", "ACME", "a much longer description", source="Arbeitnow", url="https://b.example/9")
    c = job("Data Analyst", "Acme", source="Remotive", url="https://a.example/2")
    result = deduplicate_jobs([a, b, c])
    assert len(result) == 2
    kept = next(j for j in result if "Python" in j.title)
    assert kept.description == "a much longer description" and "Remotive" in kept.also_listed_on


def test_duplicates_removed_by_url():
    a = job("Python Developer", "Acme", url="https://x.example/job/1?utm=1")
    b = job("Backend Python Engineer", "Acme Inc", url="https://x.example/job/1/")
    assert len(deduplicate_jobs([a, b])) == 1


# ------------------------------------------------------------------ URL generation
def test_linkedin_url_is_encoded_and_preserves_query():
    url = build_linkedin_url("Python Developer", "Hyderabad, India")
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.linkedin.com/jobs/search/"
    assert parse_qs(parsed.query) == {"keywords": ["Python Developer"], "location": ["Hyderabad, India"]}
    assert " " not in url


def test_linkedin_url_handles_special_characters_and_missing_location():
    url = build_linkedin_url("C++ & ML Engineer", "")
    assert parse_qs(urlparse(url).query)["keywords"] == ["C++ & ML Engineer"]
    assert "location" not in parse_qs(urlparse(url).query)
    assert "keywords=C%2B%2B%20%26%20ML%20Engineer" in url


def test_linkedin_optional_filters_are_off_by_default():
    assert "f_E" not in build_linkedin_url("Dev", "Pune")
    assert "f_E=1%2C2" in build_linkedin_url("Dev", "Pune", entry_level=True)
    assert "f_WT=2" in build_linkedin_url("Dev", "", remote=True)


def test_naukri_url_variants():
    assert build_naukri_url("Python Developer", "Hyderabad") == "https://www.naukri.com/python-developer-jobs-in-hyderabad"
    assert build_naukri_url("Python Developer") == "https://www.naukri.com/python-developer-jobs"
    assert build_naukri_url("", "Pune") == "https://www.naukri.com/jobs-in-pune"
    assert build_naukri_url("") == settings.NAUKRI_FALLBACK_URL
    assert build_naukri_url("ML Engineer", "Navi Mumbai / Thane", fresher=True) == \
        "https://www.naukri.com/ml-engineer-fresher-jobs-in-navi-mumbai-thane"


def test_naukri_template_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "NAUKRI_URL_TEMPLATES", {
        "role_location": "https://example.test/{location}/{role}", "role_only": "https://example.test/{role}",
        "location_only": "https://example.test/in/{location}"})
    assert build_naukri_url("Data Analyst", "Delhi") == "https://example.test/delhi/data-analyst"
    monkeypatch.setattr(settings, "NAUKRI_URL_TEMPLATES", {"role_location": "https://bad/{nope}"})
    assert build_naukri_url("Data Analyst", "Delhi") == settings.NAUKRI_FALLBACK_URL


# ------------------------------------------------------------------ normalisation & resilient search
def test_normalize_remotive_and_arbeitnow():
    r = normalize_remotive({"title": "Python Dev", "company_name": "Acme", "url": "https://r/1", "job_type": "full_time",
                            "candidate_required_location": "Worldwide", "publication_date": "2026-11-01T10:00:00",
                            "description": "<p>Python &amp; SQL</p>", "tags": ["python"], "category": "Software Development"})
    assert (r.source, r.remote, r.job_type, r.posted_date) == ("Remotive", True, "Full-time", "2026-11-01")
    assert r.description == "Python & SQL" and "Software Development" in r.tags
    a = normalize_arbeitnow({"title": "Dev", "company_name": "B", "url": "https://a/1", "remote": False, "location": "Berlin",
                             "created_at": 1760000000, "job_types": ["Full Time"], "description": "<b>x</b>", "tags": []})
    assert (a.source, a.remote, a.job_type, a.location) == ("Arbeitnow", False, "Full-time", "Berlin")
    assert normalize_remotive({"title": ""}) is None


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self.payload


def test_search_survives_timeout_and_http_error(monkeypatch):
    remotive = {"jobs": [{"title": "Junior Python Developer", "company_name": "Acme", "url": "https://r/1",
                          "description": "Python", "tags": [], "candidate_required_location": "Worldwide"}]}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "remotive" in url:
            return FakeResponse(remotive)
        raise requests.Timeout()

    monkeypatch.setattr(search_module.requests, "get", fake_get)
    result = search_module.search_jobs(SearchParams(query="python"))
    assert [j.title for j in result.jobs] == ["Junior Python Developer"]
    assert "timed out" in result.errors["Arbeitnow"] and "Remotive" not in result.errors

    monkeypatch.setattr(search_module.requests, "get", lambda *a, **k: FakeResponse({}, status=503))
    result = search_module.search_jobs(SearchParams(query="python"))
    assert result.jobs == [] and set(result.errors) == {"Remotive", "Arbeitnow"}


def test_search_handles_malformed_json_and_dedupes_across_sources(monkeypatch):
    shared = {"title": "Python Developer", "company_name": "Acme", "url": "https://r/1", "description": "python"}
    payloads = {"remotive": {"jobs": [shared]},
                "arbeitnow": {"data": [{"title": "Python Developer", "company_name": "Acme", "url": "https://a/1",
                                        "description": "python and more detail", "tags": [], "location": "Berlin"}],
                              "links": {"next": None}}}
    monkeypatch.setattr(search_module.requests, "get",
                        lambda url, **k: FakeResponse(payloads["remotive" if "remotive" in url else "arbeitnow"]))
    result = search_module.search_jobs(SearchParams(query="python"))
    assert len(result.jobs) == 1 and result.fetched_total == 2 and not result.errors

    monkeypatch.setattr(search_module.requests, "get", lambda *a, **k: FakeResponse(["not", "a", "dict"]))
    assert set(search_module.search_jobs(SearchParams(query="python")).errors) == {"Remotive", "Arbeitnow"}
