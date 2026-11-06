"""SearchRo 2.0 - AI-powered job search and career assistant (Streamlit app).

Run with:  python -m streamlit run app.py
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from ai import assistant
from ai.assistant import AIError, AIUnavailableError, is_ai_enabled
from ai.cover_letter import generate_cover_letter
from ai.interview import (
    CATEGORIES, categories_for_job, generate_ai_questions, job_skill_questions, questions_for_category,
)
from ai.skill_gap import ai_roadmap, analyze_skill_gap, build_roadmap
from config import settings
from database import db
from database.models import PROFILE_FIELDS
from job_search.filters import SearchParams, fresher_signals, is_fresher_friendly
from job_search.job_details import Job
from job_search.linkedin import LIMITATION_NOTE as LINKEDIN_NOTE, build_linkedin_url
from job_search.naukri import LIMITATION_NOTE as NAUKRI_NOTE, build_naukri_url
from job_search.search import search_jobs
from resume import matcher
from resume.analyzer import analyze_resume, resume_quality_report
from resume.parser import ResumeParseError, extract_text
from tracker import applications as tracker
from utils.helpers import get_logger, parse_skill_list, rows_to_csv, setup_logging
from utils.validators import (
    clean_text, is_valid_email, is_valid_phone, is_valid_url, parse_iso_date, validate_search_query,
)

st.set_page_config(page_title="SearchRo 2.0", page_icon="🔎", layout="wide", initial_sidebar_state="expanded")
log = get_logger("app")

PAGES = ["📊 Dashboard", "🔎 Job Search", "📄 Resume", "🎯 Match & Compare", "🗂️ Tracker",
         "📝 Application Prep", "🤖 AI Assistant"]
STATUS_COLORS = {"Saved": "gray", "Preparing": "amber", "Applied": "blue", "Assessment": "purple",
                 "Interview": "purple", "Offer": "green", "Rejected": "red", "Withdrawn": "gray"}
LEVEL_COLORS = {"Entry-level": "green", "Mid-level": "amber", "Senior": "red", "Unspecified": "gray"}
esc = html.escape


# ============================================================ startup / session
@st.cache_resource(show_spinner=False)
def _startup() -> bool:
    setup_logging()
    db.init_db()
    return True


def _inject_css() -> None:
    css_path = settings.ASSETS_DIR / "style.css"
    try:
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    except OSError:
        log.warning("style.css not found; using default styling")


def _init_state() -> None:
    ss = st.session_state
    defaults = {
        "nav": PAGES[0], "f_query": "", "f_skills": "", "f_company": "", "f_location": "", "f_country": "",
        "f_mode": "Any", "f_type": "Any", "f_level": "Any", "f_fresher": False, "f_sort": "Relevance",
        "f_preset": "", "page_no": 0, "search_result": None, "custom_jobs": [], "chat": [],
        "prep_job_id": None, "resume_loaded": False, "resume_text": "", "resume_analysis": {},
        "resume_name": "", "p_skills": "", "last_upload": None,
    }
    for key, value in defaults.items():
        ss.setdefault(key, value)
    if not ss.resume_loaded:
        profile = db.get_profile()
        resume = db.get_latest_resume()
        if resume:
            ss.resume_text, ss.resume_analysis, ss.resume_name = resume["raw_text"], resume["analysis"], resume["filename"]
        from_analysis = {"full_name": "name", "email": "email", "phone": "phone"}
        for field in PROFILE_FIELDS:
            value = profile.get(field) or ""
            if not value and field in from_analysis:
                value = ss.resume_analysis.get(from_analysis[field], "")
            ss[f"p_{field}"] = value
        ss.p_skills = ", ".join(profile["skills"] or ss.resume_analysis.get("skills", []))
        ss.resume_loaded = True


def go(page: str, prep_job_id: int | None = None) -> None:
    """Button callback: switch page (optionally preselecting a job on the prep page)."""
    st.session_state.nav = page
    if prep_job_id is not None:
        st.session_state.prep_job_id = prep_job_id


def current_skills() -> list[str]:
    return parse_skill_list(st.session_state.get("p_skills", ""))


def current_profile() -> dict:
    ss = st.session_state
    profile = {f: ss.get(f"p_{f}", "") for f in ("full_name", "email", "phone", "location", "headline",
                                                  "education", "summary", "linkedin_url", "github_url")}
    profile["skills"] = current_skills()
    return profile


def run_ai(fn, *args, **kwargs):
    """Call an AI function; return (result, error_message)."""
    try:
        return fn(*args, **kwargs), None
    except (AIUnavailableError, AIError) as exc:
        return None, str(exc)


# ============================================================ UI building blocks
def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"<div class='sr-page-title'>{esc(title)}</div><div class='sr-page-sub'>{esc(subtitle)}</div>",
                unsafe_allow_html=True)


def metric_cards(items: list[tuple[str, int | str, str]]) -> None:
    cards = "".join(
        f"<div class='sr-metric sr-metric-{accent}'><div class='sr-metric-label'>{esc(label)}</div>"
        f"<div class='sr-metric-value'>{esc(str(value))}</div></div>" for label, value, accent in items)
    st.markdown(f"<div class='sr-metrics'>{cards}</div>", unsafe_allow_html=True)


def empty_state(icon: str, title: str, text: str) -> None:
    st.markdown(f"<div class='sr-empty'><div class='sr-empty-icon'>{icon}</div>"
                f"<div class='sr-empty-title'>{esc(title)}</div><div>{esc(text)}</div></div>", unsafe_allow_html=True)


def badge(text: str, color: str = "") -> str:
    return f"<span class='sr-badge {color}'>{esc(text)}</span>"


def badges_html(items: list[str], color: str = "") -> str:
    return "<div class='sr-badges'>" + "".join(badge(i, color) for i in items) + "</div>"


def job_card_html(job: Job) -> str:
    meta = " · ".join(x for x in (job.company, job.location) if x)
    chips = [badge(job.source, "blue")]
    chips += [badge(f"also on {s}", "gray") for s in job.also_listed_on]
    chips.append(badge("Remote", "green") if job.remote else badge("Onsite / unspecified", "gray"))
    if job.job_type:
        chips.append(badge(job.job_type, ""))
    chips.append(badge(job.experience_level, LEVEL_COLORS.get(job.experience_level, "gray")))
    if is_fresher_friendly(job):
        chips.append(badge("Fresher-friendly", "purple"))
    if job.salary:
        chips.append(badge(job.salary, "amber"))
    if job.posted_date:
        chips.append(badge(f"Posted {job.posted_date}", "gray"))
    return (f"<div class='sr-card'><div class='sr-job-title'>{esc(job.title)}</div>"
            f"<div class='sr-job-meta'>{esc(meta)}</div><div class='sr-badges'>{''.join(chips)}</div></div>")


def match_bar(result: matcher.MatchResult) -> None:
    st.progress(min(max(result.overall, 0), 100) / 100, text=f"Match: {result.overall}% · {result.label}")


def render_match_details(result: matcher.MatchResult) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Skills", "n/a" if result.skill_score is None else f"{result.skill_score}%")
    c2.metric("Keyword overlap", "n/a" if result.keyword_score is None else f"{result.keyword_score}%")
    c3.metric("Title relevance", "n/a" if result.title_score is None else f"{result.title_score}%")
    if result.matched_skills:
        st.markdown("**Skills you match**")
        st.markdown(badges_html(result.matched_skills, "green"), unsafe_allow_html=True)
    if result.missing_skills:
        st.markdown("**Skills the job mentions that are not in your list**")
        st.markdown(badges_html(result.missing_skills, "red"), unsafe_allow_html=True)
    if result.matched_keywords:
        st.markdown("**Relevant keywords found in your resume**")
        st.markdown(badges_html(result.matched_keywords[:15], "blue"), unsafe_allow_html=True)
    st.markdown("**Suggested improvements**")
    for tip in result.suggestions:
        st.markdown(f"- {tip}")
    st.caption(matcher.DISCLAIMER)


def jobs_to_rows(jobs: list[Job]) -> list[dict]:
    return [{"title": j.title, "company": j.company, "location": j.location, "remote": "Yes" if j.remote else "No",
             "job_type": j.job_type, "experience_level": j.experience_level, "source": j.source,
             "posted_date": j.posted_date, "salary": j.salary, "url": j.url} for j in jobs]


def job_label(job: Job) -> str:
    return f"{job.title} — {job.company or 'Unknown company'} ({job.source})"


# ============================================================ Dashboard
def page_dashboard() -> None:
    page_header("Dashboard", "Your job search at a glance. Every number comes from your local database.")
    stats = db.get_dashboard_stats()
    metric_cards([
        ("Jobs found", stats["jobs_found"], "accent"), ("Saved jobs", stats["saved_jobs"], "accent"),
        ("Applications submitted", stats["submitted"], "purple"), ("Interviews", stats["interviews"], "amber"),
        ("Offers", stats["offers"], "green"), ("Rejected", stats["rejected"], "red"),
    ])
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Application status")
        if stats["applications_total"]:
            counts = pd.DataFrame({"Applications": stats["status_counts"]})
            st.bar_chart(counts)
        else:
            empty_state("🗂️", "No applications yet", "Save a job from Job Search and it will appear here.")
        st.subheader("Recent activity")
        activity = db.get_recent_activity()
        if activity:
            rows = "".join(
                f"<div class='sr-activity'><div class='sr-activity-time'>{esc(a['created_at'].replace('T', ' '))}</div>"
                f"<div><b>{esc(a['title'])}</b>{' · ' + esc(a['company']) if a['company'] else ''}<br>"
                f"<span class='sr-note'>{esc(a['note'].replace('[status] ', ''))}</span></div></div>" for a in activity)
            st.markdown(f"<div class='sr-card'>{rows}</div>", unsafe_allow_html=True)
        else:
            empty_state("🕒", "Nothing yet", "Status changes and notes will show up here.")
    with right:
        st.subheader("Recommended next actions")
        actions = tracker.recommend_next_actions(stats, db.get_profile(), bool(st.session_state.resume_text),
                                                 db.get_upcoming_dates())
        for action in actions:
            st.markdown(f"<div class='sr-action'>{esc(action)}</div>", unsafe_allow_html=True)
        st.subheader("Search history")
        history = db.get_search_history(8)
        if history:
            st.dataframe(pd.DataFrame([{"When": h["created_at"].replace("T", " "), "Search": h["query"] or "(any)",
                                        "Location": h["location"], "Results": h["results_count"]} for h in history]),
                         hide_index=True)
        else:
            empty_state("🔎", "No searches yet", "Your recent searches will be listed here.")


# ============================================================ Job search
def _apply_preset() -> None:
    preset = st.session_state.get("f_preset", "")
    if preset:
        st.session_state.f_query = preset
        st.session_state.f_fresher = True


def _params_from_state() -> SearchParams:
    ss = st.session_state
    return SearchParams(
        query=validate_search_query(ss.f_query), skills=parse_skill_list(ss.f_skills),
        company=clean_text(ss.f_company, 100), location=clean_text(ss.f_location, 100),
        country=clean_text(ss.f_country, 100), work_mode=ss.f_mode, employment_type=ss.f_type,
        experience_level=ss.f_level, fresher_only=bool(ss.f_fresher), sort_by=ss.f_sort)


def page_job_search() -> None:
    page_header("Job Search", "Search live public job APIs, then jump to LinkedIn and Naukri with the same search.")
    ss = st.session_state
    with st.container(border=True):
        st.selectbox("Fresher quick searches", [""] + settings.FRESHER_PRESETS, key="f_preset", on_change=_apply_preset,
                     format_func=lambda x: x or "Choose a preset (optional)…")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Job title / keywords", key="f_query", placeholder="e.g. Python Developer")
        c2.text_input("Skills (comma separated)", key="f_skills", placeholder="e.g. python, sql")
        c3.text_input("Company", key="f_company")
        c4, c5, c6 = st.columns(3)
        c4.text_input("Location / city", key="f_location", placeholder="e.g. Hyderabad")
        c5.text_input("Country", key="f_country", placeholder="e.g. India")
        c6.selectbox("Remote or onsite", settings.WORK_MODES, key="f_mode")
        c7, c8, c9 = st.columns(3)
        c7.selectbox("Employment type", ["Any"] + settings.EMPLOYMENT_TYPES, key="f_type")
        c8.selectbox("Experience level", ["Any"] + settings.EXPERIENCE_LEVELS, key="f_level")
        c9.selectbox("Sort by", settings.SORT_OPTIONS, key="f_sort")
        st.toggle("Fresher / entry-level only (keyword based)", key="f_fresher")
        search_clicked = st.button("🔎 Search jobs", type="primary")

    params = _params_from_state()
    role = params.query or " ".join(params.skills)
    place = params.location or params.country
    linkedin_url = build_linkedin_url(role, place, entry_level=params.fresher_only, remote=params.work_mode == "Remote")
    naukri_url = build_naukri_url(role, params.location or params.country, fresher=params.fresher_only)
    l1, l2, l3 = st.columns([1, 1, 3])
    l1.link_button("Open LinkedIn Jobs ↗", linkedin_url)
    l2.link_button("Open Naukri ↗", naukri_url)
    l3.caption("These are external search links, not API integrations. " + LINKEDIN_NOTE + " " + NAUKRI_NOTE)

    if search_clicked:
        with st.spinner("Searching Remotive and Arbeitnow…"):
            result = search_jobs(params)
        ss.search_result, ss.page_no = result, 0
        try:
            db.record_search(params.query or " ".join(params.skills), place,
                             f"mode={params.work_mode}; type={params.employment_type}; level={params.experience_level}; "
                             f"fresher={params.fresher_only}", len(result.jobs))
            db.record_found_jobs([j.to_dict() for j in result.jobs])
        except db.DatabaseError as exc:
            st.warning(f"Search worked, but history could not be saved: {exc}")

    result = ss.search_result
    if result is None:
        empty_state("🔎", "Ready when you are",
                    "Enter a role or skills above and click Search. Tip: use a fresher preset for entry-level roles.")
        return
    for source, error in result.errors.items():
        st.warning(f"{source} is unavailable right now ({error}). Results from other sources are still shown.")
    counts = ", ".join(f"{s}: {n}" for s, n in result.source_counts.items()) or "none"
    st.caption(f"{len(result.jobs)} matching jobs · fetched {result.fetched_total} (per source: {counts}). "
               "Remotive lists remote jobs and Arbeitnow mostly European jobs, so for on-site roles in India "
               "use the LinkedIn and Naukri buttons.")
    if not result.jobs:
        empty_state("🫥", "No matching jobs", "Try fewer filters, a broader title, or turn off the fresher-only toggle.")
        return

    st.download_button("⬇️ Export results (CSV)", rows_to_csv(jobs_to_rows(result.jobs), list(jobs_to_rows(result.jobs)[0])),
                       file_name="searchro_results.csv", mime="text/csv")
    pages = max(1, -(-len(result.jobs) // settings.PAGE_SIZE))
    ss.page_no = min(ss.page_no, pages - 1)
    start = ss.page_no * settings.PAGE_SIZE
    saved_keys = db.saved_job_keys()
    skills, text = current_skills(), ss.resume_text
    for job in result.jobs[start:start + settings.PAGE_SIZE]:
        st.markdown(job_card_html(job), unsafe_allow_html=True)
        match = matcher.match_resume_to_job(skills, text, job) if skills or text else None
        if match:
            match_bar(match)
        b1, b2, b3 = st.columns([1, 1, 4])
        if job.url:
            b1.link_button("Open job ↗", job.url)
        if job.job_key in saved_keys:
            b2.button("✓ Saved", key=f"saved_{job.job_key}", disabled=True)
        elif b2.button("💾 Save", key=f"save_{job.job_key}"):
            tracker.track_job(job)
            st.toast(f"Saved “{job.title}” to your tracker")
            st.rerun()
        with st.expander("Details"):
            sig = fresher_signals(job)
            if sig["positives"]:
                st.markdown("**Entry-level signals:** " + ", ".join(sig["positives"]))
            if sig["blockers"]:
                st.markdown("**Senior/experience signals:** " + ", ".join(sig["blockers"]))
            if job.skills:
                st.markdown(badges_html(job.skills, "blue"), unsafe_allow_html=True)
            if match:
                render_match_details(match)
            st.text_area("Description", job.description[:6000] or "No description provided.", height=220,
                         disabled=True, key=f"desc_{job.job_key}", label_visibility="collapsed")
    p1, p2, p3 = st.columns([1, 1, 4])
    if p1.button("← Previous", disabled=ss.page_no == 0):
        ss.page_no -= 1
        st.rerun()
    if p2.button("Next →", disabled=ss.page_no >= pages - 1):
        ss.page_no += 1
        st.rerun()
    p3.caption(f"Page {ss.page_no + 1} of {pages}")


# ============================================================ Resume
def _load_resume_upload(uploaded) -> None:
    ss = st.session_state
    signature = (uploaded.name, uploaded.size)
    if ss.last_upload == signature:
        return
    try:
        data = uploaded.getvalue()
        text = extract_text(uploaded.name, data)
    except ResumeParseError as exc:
        st.error(str(exc))
        return
    analysis = analyze_resume(text)
    ss.resume_text, ss.resume_analysis, ss.resume_name, ss.last_upload = text, analysis, uploaded.name, signature
    for field, key in (("full_name", "name"), ("email", "email"), ("phone", "phone")):
        if analysis.get(key) and not ss.get(f"p_{field}"):
            ss[f"p_{field}"] = analysis[key]
    ss.p_skills = ", ".join(analysis["skills"])
    for link in analysis.get("links", []):
        field = "github_url" if "github" in link.lower() else "linkedin_url"
        if not ss.get(f"p_{field}"):
            ss[f"p_{field}"] = link if link.startswith("http") else "https://" + link
    try:
        db.save_resume_info(uploaded.name, text, analysis)
    except db.DatabaseError as exc:
        st.warning(f"Resume was read but could not be stored: {exc}")
    st.success(f"Read “{uploaded.name}”: {len(text.split())} words, {len(analysis['skills'])} skills detected.")


def page_resume() -> None:
    page_header("Resume", "Upload your resume, review what was extracted, and correct anything that is wrong.")
    uploaded = st.file_uploader("Upload resume (PDF, DOCX or TXT, max 5 MB)", type=["pdf", "docx", "txt"])
    if uploaded is not None:
        _load_resume_upload(uploaded)
    ss = st.session_state
    if not ss.resume_text:
        empty_state("📄", "No resume yet", "Upload a file to extract your details and skills. Nothing is guessed: "
                    "missing items stay blank.")
    else:
        st.caption(f"Current resume: {ss.resume_name}")

    st.subheader("Candidate profile")
    with st.container(border=True):
        a, b, c = st.columns(3)
        a.text_input("Full name", key="p_full_name")
        b.text_input("Email", key="p_email")
        c.text_input("Phone", key="p_phone")
        d, e = st.columns(2)
        d.text_input("Location", key="p_location")
        e.text_input("Target role / headline", key="p_headline", placeholder="e.g. final-year CSE student seeking Python roles")
        f, g = st.columns(2)
        f.text_input("LinkedIn URL", key="p_linkedin_url")
        g.text_input("GitHub URL", key="p_github_url")
        st.text_area("Education", key="p_education", height=80)
        st.text_area("Short summary (used in cover letters)", key="p_summary", height=80)
        st.text_area("Skills (comma separated — edit freely)", key="p_skills", height=90)
        if st.button("💾 Save profile and skills", type="primary"):
            problems = []
            if ss.p_email and not is_valid_email(ss.p_email):
                problems.append("Email looks invalid.")
            if ss.p_phone and not is_valid_phone(ss.p_phone):
                problems.append("Phone number looks invalid.")
            for key, label in (("p_linkedin_url", "LinkedIn URL"), ("p_github_url", "GitHub URL")):
                if ss[key] and not is_valid_url(ss[key]):
                    problems.append(f"{label} must start with http:// or https://")
            if problems:
                for p in problems:
                    st.error(p)
            else:
                profile = current_profile()
                db.save_profile({k: clean_text(v, 2000) for k, v in profile.items() if k != "skills"}, profile["skills"])
                st.success("Profile saved.")

    analysis = ss.resume_analysis
    if not ss.resume_text:
        return
    st.subheader("Extracted details")
    tabs = st.tabs(["Skills", "Projects", "Education", "Experience", "Certifications", "Quality check", "Raw text"])
    with tabs[0]:
        groups = analysis.get("skill_groups", {})
        if groups:
            for category, items in groups.items():
                st.markdown(f"**{category}**")
                st.markdown(badges_html(items, "blue"), unsafe_allow_html=True)
        else:
            st.info("No known technical skills were detected. Add them in the Skills box above.")
        st.caption("Detected by matching a built-in skills vocabulary. Your edited list above is what SearchRo uses.")
    for tab, key, empty in ((tabs[1], "projects", "No Projects section detected."),
                            (tabs[2], "education", "No Education section detected."),
                            (tabs[3], "experience", "No Experience section detected (normal for freshers)."),
                            (tabs[4], "certifications", "No Certifications section detected.")):
        with tab:
            items = analysis.get(key) or []
            if items:
                for item in items:
                    st.markdown(f"- {item}")
            else:
                st.info(empty)
    with tabs[5]:
        report = resume_quality_report(ss.resume_text, analysis)
        st.progress(report["score"] / 100, text=f"Resume checklist score: {report['score']}/100")
        for chk in report["checks"]:
            st.markdown(f"{'✅' if chk['passed'] else '⚠️'} {chk['label']}" + ("" if chk["passed"] else f" — {chk['tip']}"))
        if report["weak_bullets"]:
            st.markdown("**Bullets to rewrite:**")
            for b in report["weak_bullets"]:
                st.markdown(f"- {b}")
        st.caption("Rule-based checks. For deeper rewriting help, use AI Assistant → Resume improvement.")
    with tabs[6]:
        st.text_area("Extracted text", ss.resume_text, height=300, disabled=True, label_visibility="collapsed")


# ============================================================ Match & Compare
def _candidate_jobs() -> dict[str, Job]:
    jobs: dict[str, Job] = {}
    result = st.session_state.search_result
    if result:
        for job in result.jobs[:60]:
            jobs[f"Search · {job_label(job)}"] = job
    for saved in db.list_saved_jobs():
        job = Job.from_dict(saved)
        jobs[f"Saved · {job_label(job)}"] = job
    for job in st.session_state.custom_jobs:
        jobs[f"Pasted · {job_label(job)}"] = job
    return jobs


def page_match() -> None:
    page_header("Match & Compare", "See how your resume overlaps with job descriptions. The scoring method is shown below.")
    ss = st.session_state
    if not ss.resume_text and not current_skills():
        empty_state("🎯", "Add your resume first", "Upload a resume or enter skills on the Resume page.")
        st.button("Go to Resume", on_click=go, args=("📄 Resume",))
        return
    with st.expander("➕ Paste a job description to compare"):
        t1, t2 = st.columns(2)
        title = t1.text_input("Job title", key="cj_title")
        company = t2.text_input("Company", key="cj_company")
        desc = st.text_area("Job description", key="cj_desc", height=160)
        if st.button("Add to comparison"):
            if title.strip() and desc.strip():
                ss.custom_jobs.append(Job(title=clean_text(title, 150), company=clean_text(company, 150),
                                          description=clean_text(desc, 20000), source="Pasted"))
                st.rerun()
            else:
                st.error("Please enter a title and a description.")
    options = _candidate_jobs()
    if not options:
        empty_state("🗂️", "No jobs to compare", "Run a search, save jobs, or paste a job description above.")
        return
    chosen = st.multiselect("Choose jobs to compare", list(options), default=list(options)[:5])
    if not chosen:
        st.info("Select at least one job.")
        return
    ranked = matcher.compare_jobs(current_skills(), ss.resume_text, [options[c] for c in chosen])
    st.dataframe(
        pd.DataFrame([{"Job": j.title, "Company": j.company, "Match %": r.overall, "Rating": r.label,
                       "Skills matched": f"{len(r.matched_skills)}/{len(r.job_skills)}",
                       "Level": j.experience_level} for j, r in ranked]),
        hide_index=True,
        column_config={"Match %": st.column_config.ProgressColumn("Match %", min_value=0, max_value=100, format="%d%%")})
    for job, result in ranked:
        with st.expander(f"{job.title} — {job.company or 'Unknown'} · {result.overall}%"):
            match_bar(result)
            render_match_details(result)
    with st.expander("How the score is calculated"):
        st.markdown(
            "**Overall = 60% skills coverage + 25% keyword overlap + 15% title relevance.**\n\n"
            "- *Skills coverage*: recognised skills in the posting that are also in your skill list.\n"
            "- *Keyword overlap*: how many of the posting's 25 most frequent content words appear in your resume.\n"
            "- *Title relevance*: how many words of the job title appear in your resume.\n"
            "- Components that cannot be computed are dropped and the weights re-scaled.")
        st.caption(matcher.DISCLAIMER)


# ============================================================ Tracker
def page_tracker() -> None:
    page_header("Application Tracker", "Track every application. SearchRo never submits applications for you.")
    with st.expander("➕ Add a job manually (e.g. found on LinkedIn or Naukri)"):
        m1, m2 = st.columns(2)
        title = m1.text_input("Job title", key="mj_title")
        company = m2.text_input("Company", key="mj_company")
        m3, m4 = st.columns(2)
        url = m3.text_input("Job link (https://…)", key="mj_url")
        location = m4.text_input("Location", key="mj_location")
        desc = st.text_area("Job description (optional, improves matching)", key="mj_desc", height=100)
        if st.button("Add to tracker"):
            try:
                tracker.add_manual_job(title, company, url, location, desc)
                st.success("Added.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    f1, f2 = st.columns([1, 2])
    status_filter = f1.selectbox("Filter by status", ["All"] + settings.APPLICATION_STATUSES)
    search = f2.text_input("Search saved applications", placeholder="title, company, notes, contact…")
    rows = db.list_applications(status_filter, search)
    if not rows:
        empty_state("🗂️", "No applications found",
                    "Save jobs from Job Search or add one manually. Adjust the filters if you expected results.")
        return
    top1, top2 = st.columns([4, 1])
    top1.markdown(" ".join(badge(f"{s}: {n}", STATUS_COLORS[s]) for s, n in db.get_status_counts().items() if n),
                  unsafe_allow_html=True)
    top2.download_button("⬇️ Export CSV", tracker.export_applications_csv(rows), file_name="searchro_tracker.csv",
                         mime="text/csv")
    st.dataframe(pd.DataFrame([{"Job": r["title"], "Company": r["company"], "Status": r["status"],
                                "Applied": r["applied_date"], "Interview": r["interview_date"],
                                "Follow-up": r["followup_date"], "Updated": r["updated_at"].replace("T", " ")}
                               for r in rows]), hide_index=True)

    labels = {r["id"]: f"{r['title']} — {r['company'] or 'Unknown'} [{r['status']}]" for r in rows}
    app_id = st.selectbox("Select a record to edit", list(labels), format_func=lambda i: labels[i])
    app = db.get_application(app_id)
    if app is None:
        st.warning("That record no longer exists.")
        return
    st.markdown(f"### {esc(app['title'])}")
    st.caption(f"{app['company']} · {app['location']} · saved from {app['source']}")
    k = f"tr_{app_id}"
    with st.form(f"form_{app_id}"):
        e1, e2 = st.columns(2)
        status = e1.selectbox("Status", settings.APPLICATION_STATUSES,
                              index=settings.APPLICATION_STATUSES.index(app["status"]))
        contact_name = e2.text_input("Recruiter / contact name", app["contact_name"])
        d1, d2, d3 = st.columns(3)
        applied = d1.date_input("Application date", parse_iso_date(app["applied_date"]), key=f"{k}_a")
        interview = d2.date_input("Interview date", parse_iso_date(app["interview_date"]), key=f"{k}_i")
        followup = d3.date_input("Follow-up date", parse_iso_date(app["followup_date"]), key=f"{k}_f")
        c1, c2 = st.columns(2)
        contact_email = c1.text_input("Contact email", app["contact_email"])
        contact_phone = c2.text_input("Contact phone", app["contact_phone"])
        notes = st.text_area("Notes", app["notes"], height=110)
        saved = st.form_submit_button("💾 Save changes", type="primary")
    if saved:
        problems = tracker.save_application_changes(app_id, {
            "status": status, "applied_date": applied, "interview_date": interview, "followup_date": followup,
            "contact_name": contact_name, "contact_email": contact_email, "contact_phone": contact_phone, "notes": notes})
        if problems:
            for p in problems:
                st.error(p)
        else:
            st.success("Saved.")
            st.rerun()
    a1, a2, a3 = st.columns([1, 1, 3])
    if app["url"]:
        a1.link_button("Open job ↗", app["url"])
    a2.button("📝 Prepare", on_click=go, args=("📝 Application Prep", app["job_id"]), key=f"prep_{app_id}")
    with st.expander("Activity log and notes"):
        n1, n2 = st.columns([4, 1])
        new_note = n1.text_input("Add a note", key=f"note_{app_id}", label_visibility="collapsed", placeholder="Add a note…")
        if n2.button("Add note", key=f"addnote_{app_id}"):
            try:
                db.add_note(app_id, new_note)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        for note in db.list_notes(app_id):
            c1, c2 = st.columns([8, 1])
            c1.markdown(f"`{note['created_at'].replace('T', ' ')}` {note['note']}")
            if not note["note"].startswith("[status]") and c2.button("🗑", key=f"delnote_{note['id']}"):
                db.delete_note(note["id"])
                st.rerun()
    with st.expander("🗑 Delete this record"):
        confirm = st.checkbox("Yes, permanently delete this job and its notes", key=f"confirm_{app_id}")
        if st.button("Delete record", disabled=not confirm, key=f"del_{app_id}"):
            db.delete_application(app_id)
            st.rerun()


# ============================================================ Application preparation
def _generate_pending(flag: str, target: str, fn, kind: str, job_id: int | None) -> None:
    """If a generate button set `flag`, run the AI call now (before the target widget is created)."""
    ss = st.session_state
    if not ss.get(flag):
        return
    ss[flag] = False
    with st.spinner("Generating with AI…"):
        text, error = run_ai(fn)
    if error:
        st.error(error)
    else:
        ss[target] = text
        db.add_prep_history(kind, text, job_id)


def _set_flag(key: str) -> None:
    st.session_state[key] = True


def render_interview_section(job: Job | None, key: str, job_id: int | None = None) -> None:
    ss = st.session_state
    cats_default = ["Python", "SQL"] if job is None else categories_for_job(job)[:2]
    cats = st.multiselect("Question categories", CATEGORIES, default=cats_default, key=f"{key}_cats")
    if job is not None and job_skill_questions(job):
        st.markdown("**Questions based on this job's skills**")
        for q, a in job_skill_questions(job):
            with st.expander(q):
                st.write(a)
    for cat in cats:
        st.markdown(f"**{cat}**")
        for q, a in questions_for_category(cat):
            with st.expander(q):
                st.markdown(f"**Sample answer:** {a}")
    st.markdown("**AI-generated questions**")
    count = st.slider("How many questions?", 3, 15, 8, key=f"{key}_count")
    flag, target = f"{key}_pending", f"{key}_ai_out"
    _generate_pending(flag, target, lambda: generate_ai_questions(job, cats, current_skills(), count), "interview", job_id)
    if not is_ai_enabled():
        st.info(assistant.SETUP_HELP)
    st.button("✨ Generate with AI", key=f"{key}_btn", disabled=not is_ai_enabled(), on_click=_set_flag, args=(flag,))
    if ss.get(target):
        st.markdown(ss[target])


def page_prep() -> None:
    page_header("Application Preparation", "Everything you need before you apply. Submit applications yourself on the employer's site.")
    saved = db.list_saved_jobs()
    if not saved:
        empty_state("📝", "No saved jobs yet", "Save a job from Job Search (or add one in the Tracker) to prepare for it.")
        st.button("Go to Job Search", on_click=go, args=("🔎 Job Search",))
        return
    ids = [s["id"] for s in saved]
    if st.session_state.prep_job_id not in ids:
        st.session_state.prep_job_id = ids[0]
    labels = {s["id"]: job_label(Job.from_dict(s)) for s in saved}
    job_id = st.selectbox("Saved job", ids, format_func=lambda i: labels[i], key="prep_job_id")
    record = db.get_saved_job(job_id)
    job = Job.from_dict(record)
    app = db.get_application_for_job(job_id)
    st.markdown(job_card_html(job), unsafe_allow_html=True)
    cols = st.columns([1, 1, 4])
    if job.url:
        cols[0].link_button("Open & apply ↗", job.url)
    if app:
        cols[1].markdown(badge(app["status"], STATUS_COLORS[app["status"]]), unsafe_allow_html=True)
    profile, skills, text = current_profile(), current_skills(), st.session_state.resume_text
    summary = tracker.prep_summary(job, skills, text, profile)
    tabs = st.tabs(["Cover letter", "Resume match", "Interview questions", "Key skills", "Checklist", "History"])
    with tabs[0]:
        key = f"cl_{job_id}"
        _generate_pending(f"{key}_pending", key, lambda: generate_cover_letter(profile, job, text, summary["match"].matched_skills),
                          "cover_letter", job_id)
        if key not in st.session_state:
            st.session_state[key] = summary["cover_letter"]
        st.caption("A template draft built only from your saved profile. Edit freely, or let AI write a tailored version.")
        st.text_area("Cover letter (editable)", key=key, height=340)
        b1, b2, b3 = st.columns([1, 1, 3])
        b1.button("✨ Write with AI", key=f"{key}_ai", disabled=not is_ai_enabled(), on_click=_set_flag, args=(f"{key}_pending",))
        b2.download_button("⬇️ Download .txt", st.session_state[key], file_name=f"cover_letter_{job_id}.txt")
        if not is_ai_enabled():
            st.info(assistant.SETUP_HELP)
        if not (profile.get("full_name") or "").strip():
            st.warning("Add your name on the Resume page so the letter has a signature.")
    with tabs[1]:
        if skills or text:
            match_bar(summary["match"])
            render_match_details(summary["match"])
        else:
            st.info("Upload a resume or add skills to see your match summary.")
    with tabs[2]:
        render_interview_section(job, f"iq_{job_id}", job_id)
    with tabs[3]:
        if summary["important_skills"]:
            st.markdown(badges_html(summary["important_skills"], "blue"), unsafe_allow_html=True)
        else:
            st.info("No known technical skills were recognised in this job description.")
        sig = fresher_signals(job)
        st.markdown("**Entry-level signals:** " + (", ".join(sig["positives"]) or "none found"))
        st.markdown("**Experience / seniority signals:** " + (", ".join(sig["blockers"]) or "none found"))
    with tabs[4]:
        for i, item in enumerate(summary["checklist"]):
            st.checkbox(item, key=f"chk_{job_id}_{i}")
        st.caption("Ticks are kept for this session only.")
    with tabs[5]:
        history = db.list_prep_history(job_id)
        if not history:
            st.info("AI-generated cover letters and questions for this job will be listed here.")
        for h in history:
            with st.expander(f"{h['kind']} · {h['created_at'].replace('T', ' ')}"):
                st.markdown(h["content"])


# ============================================================ AI assistant
def page_ai() -> None:
    page_header("AI Assistant", "Optional OpenAI-powered coaching. The rest of SearchRo works without it.")
    if is_ai_enabled():
        st.success(f"AI enabled · model: {settings.get_openai_model()}")
    else:
        st.info(assistant.SETUP_HELP)
    ss = st.session_state
    tabs = st.tabs(["Resume improvement", "Skill-gap analysis", "Interview prep", "Career chat"])
    with tabs[0]:
        if not ss.resume_text:
            empty_state("📄", "No resume uploaded", "Upload your resume on the Resume page first.")
        else:
            report = resume_quality_report(ss.resume_text, ss.resume_analysis)
            st.progress(report["score"] / 100, text=f"Rule-based checklist score: {report['score']}/100")
            for tip in report["tips"]:
                st.markdown(f"- {tip}")
            role = st.text_input("Target role (optional)", key="ri_role", placeholder="e.g. Python Developer")
            _generate_pending("ri_pending", "ri_out", lambda: assistant.improve_resume(ss.resume_text, role, current_skills()),
                              "resume_review", None)
            st.button("✨ Analyze with AI", disabled=not is_ai_enabled(), on_click=_set_flag, args=("ri_pending",))
            if ss.get("ri_out"):
                st.markdown(ss["ri_out"])
    with tabs[1]:
        options = _candidate_jobs()
        if not options:
            empty_state("🎯", "No jobs to analyze", "Run a search or save jobs, then come back.")
        else:
            chosen = st.multiselect("Compare your skills with these jobs", list(options), default=list(options)[:8], key="sg_jobs")
            gaps = analyze_skill_gap(current_skills(), [options[c] for c in chosen])
            if not chosen:
                st.info("Select at least one job.")
            elif not gaps:
                st.success("No missing skills found among the recognised skills in these jobs.")
            else:
                st.dataframe(pd.DataFrame(gaps).rename(columns={"skill": "Missing skill", "category": "Category",
                             "jobs_requiring": "Jobs requiring", "share": "% of jobs", "priority": "Priority"}), hide_index=True)
                for phase in build_roadmap(gaps):
                    st.markdown(f"**{phase['phase']}**")
                    st.markdown(badges_html(phase["skills"], "amber"), unsafe_allow_html=True)
                    st.caption(phase["how"])
                _generate_pending("sg_pending", "sg_out", lambda: ai_roadmap(current_skills(), gaps, ss.f_query), "skill_roadmap", None)
                st.button("✨ Generate AI roadmap", disabled=not is_ai_enabled(), on_click=_set_flag, args=("sg_pending",))
                if ss.get("sg_out"):
                    st.markdown(ss["sg_out"])
    with tabs[2]:
        saved = db.list_saved_jobs()
        pick = st.selectbox("Tailor to a saved job (optional)", [None] + [s["id"] for s in saved], key="ip_job",
                            format_func=lambda i: "General practice" if i is None else job_label(Job.from_dict(next(s for s in saved if s["id"] == i))))
        job = Job.from_dict(next(s for s in saved if s["id"] == pick)) if pick else None
        render_interview_section(job, f"ai_iq_{pick}", pick)
    with tabs[3]:
        for msg in ss.chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if not ss.chat:
            st.caption("Ask about applications, resume tips, interview preparation, career planning or technical skills.")
        prompt = st.chat_input("Ask the career assistant…", disabled=not is_ai_enabled())
        if prompt:
            ss.chat.append({"role": "user", "content": clean_text(prompt, 2000)})
            context = f"Skills: {', '.join(current_skills())}. Headline: {ss.get('p_headline', '')}. Education: {ss.get('p_education', '')}."
            with st.spinner("Thinking…"):
                reply, error = run_ai(assistant.chat_reply, ss.chat, context)
            ss.chat.append({"role": "assistant", "content": reply or f"⚠️ {error}"})
            st.rerun()
        if ss.chat and st.button("Clear chat"):
            ss.chat = []
            st.rerun()


# ============================================================ main
def main() -> None:
    try:
        _startup()
    except Exception as exc:  # noqa: BLE001
        st.error(f"SearchRo could not start its database: {exc}")
        st.stop()
    _inject_css()
    _init_state()
    with st.sidebar:
        st.markdown("<div class='sr-brand'><div class='sr-logo'>S</div><div><div class='sr-brand-name'>SearchRo</div>"
                    "<div class='sr-brand-sub'>Career assistant 2.0</div></div></div>", unsafe_allow_html=True)
        st.radio("Navigation", PAGES, key="nav", label_visibility="collapsed")
        st.divider()
        st.markdown(badge("AI on", "green") if is_ai_enabled() else badge("AI off · no API key", "gray"), unsafe_allow_html=True)
        st.caption("SearchRo never applies to jobs for you and never scrapes login-protected sites. "
                   "Your data stays in a local SQLite file.")
    pages = {PAGES[0]: page_dashboard, PAGES[1]: page_job_search, PAGES[2]: page_resume, PAGES[3]: page_match,
             PAGES[4]: page_tracker, PAGES[5]: page_prep, PAGES[6]: page_ai}
    try:
        pages[st.session_state.nav]()
    except db.DatabaseError as exc:
        st.error(f"Database problem: {exc}")
    except Exception:  # noqa: BLE001 - never show a raw traceback to the user
        log.exception("Unhandled error on page %s", st.session_state.nav)
        st.error("Something went wrong on this page. Details were written to data/searchro.log. "
                 "Try again, or switch to another page.")


main()
