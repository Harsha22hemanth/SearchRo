# SearchRo 2.0 — AI-Powered Job Search & Career Assistant

SearchRo is a local Streamlit app that helps you (especially fresh graduates) find jobs, match them
against your resume, track applications, and prepare for interviews. Everything runs on your own
laptop and stores data in a local SQLite file. **No paid API key is needed** for the core features.

> SearchRo **never** applies to jobs for you and **never** scrapes login-protected sites.
> You review everything and submit applications yourself on the employer's website.

---

## 1. What you get

| Page | What it does |
|---|---|
| **Dashboard** | Real numbers from your database: jobs found, saved, submitted, interviews, offers, rejections, recent activity, status chart, search history, and recommended next actions. |
| **Job Search** | Searches the **Remotive** and **Arbeitnow** public APIs in parallel, normalises and de-duplicates results, filters (title, skills, company, location, country, remote/onsite, employment type, experience level, fresher-only), sorts by relevance or date, paginates, and exports CSV. Also builds **LinkedIn** and **Naukri** search links from the same search. |
| **Resume** | Upload PDF / DOCX / TXT. Extracts name, email, phone, links, skills (languages, frameworks, databases, tools), projects, education, experience, certifications. You can edit the profile and skills. Includes a rule-based resume quality checklist. |
| **Match & Compare** | Scores your resume against jobs (search results, saved jobs, or a pasted job description) with a transparent formula, matched/missing skills and suggestions. |
| **Tracker** | Save jobs, set status (Saved → Preparing → Applied → Assessment → Interview → Offer / Rejected / Withdrawn), dates, recruiter details, notes, search, filter, edit, delete, CSV export. |
| **Application Prep** | Per saved job: cover-letter draft, match summary, interview questions, key skills, application checklist. |
| **AI Assistant** *(optional)* | Resume improvement, cover letters, interview Q&A, skill-gap roadmap, career chat — needs an OpenAI key. |

### Honest limits (please read)

* **LinkedIn and Naukri are *search links*, not API integrations.** Neither offers a public job-search API
  for individuals, and scraping them would break their terms. The buttons open a normal search
  (same keywords and location) in your browser, where you log in and apply as usual.
* **Remotive** lists remote jobs worldwide and **Arbeitnow** mostly European jobs. For on-site jobs in
  India (for example Hyderabad), use the LinkedIn / Naukri buttons, or add jobs manually in the Tracker.
* **Fresher detection is keyword based** (words like *junior, graduate, trainee, intern, fresher* and
  phrases like *0-1 years*, with senior titles and *3+ years of experience* treated as blockers). The
  reasons are shown on each job, and a job is only labelled fresher-friendly when there is a signal.
* **Match scores are text-overlap indicators**, not hiring probabilities.
* The job APIs need an internet connection. If one is down, SearchRo shows a warning and keeps
  showing results from the other.

---

## 2. Setup on Windows (step by step)

### Step 1 — Install Python
Install Python 3.10 or newer from <https://www.python.org/downloads/> (tick **"Add python.exe to PATH"**).
Check it from PowerShell:

```powershell
py -0
```

This lists installed versions. The commands below use Python 3.13; if you have another version (3.10+),
replace `-3.13` with it (for example `-3.12`).

### Step 2 — Open the project in VS Code
1. Unzip `SearchRo_Advanced.zip`. You will get a folder called `SearchRo`.
2. Open VS Code → **File → Open Folder…** → choose the `SearchRo` folder.
3. Open the built-in terminal: **Terminal → New Terminal** (make sure it is **PowerShell** and that the
   path ends with `SearchRo`).

### Step 3 — Create a virtual environment and install requirements

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

You should now see `(venv)` at the start of the prompt. A virtual environment is just a private box of
packages for this project; you must activate it (the second command) every time you open a new terminal.

If VS Code asks *"We noticed a new environment"*, click **Yes** so it uses `venv`.

### Step 4 — Run the app

```powershell
python -m streamlit run app.py
```

Your browser opens at <http://localhost:8501>. Press `Ctrl+C` in the terminal to stop it.

### Step 5 — (Optional) enable the AI features
1. Get an API key from <https://platform.openai.com/api-keys> (this is a paid OpenAI service; SearchRo works without it).
2. In the `SearchRo` folder, copy `.env.example` to a new file named `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
3. Open `.env` in VS Code and set:
   ```
   OPENAI_API_KEY=paste-your-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```
4. Stop the app (`Ctrl+C`) and start it again. The sidebar badge changes to **AI on**.

Never share `.env` or commit it to Git (it is already listed in `.gitignore`).

### Step 6 — Run the tests

```powershell
python -m pytest
```

All tests run offline and do not need an API key. Expected result: `54 passed`.

---

## 3. How to use SearchRo

1. **Resume page** — upload your resume. Check the extracted details, fix the *Skills* box if needed
   (comma separated), add a headline like *"final-year CSE student seeking Python roles"*, then click
   **Save profile and skills**. Skills you save here are what matching uses.
2. **Job Search page** — pick a *Fresher quick search* preset or type a role. Click **Search jobs**.
   Each result shows source, remote/onsite, type, experience level, a fresher badge (when keywords
   justify it) and your match percentage. Click **Save** to add a job to the tracker, or **Details**
   for the description, skills and match breakdown.
   Use **Open LinkedIn Jobs** and **Open Naukri** to continue the same search on those sites.
   Found a job elsewhere? Use *Add a job manually* on the Tracker page.
3. **Match & Compare** — pick several jobs (or paste a description) and compare scores side by side.
4. **Tracker** — change status, add dates and recruiter details, write notes. The dashboard updates
   automatically. Use **Export CSV** to back up your data.
5. **Application Prep** — choose a saved job, edit the cover-letter draft, review the checklist, then
   click **Open & apply** and submit on the employer's site yourself.
6. **AI Assistant** — with an API key: resume review, AI interview questions, AI learning roadmap,
   and chat. Without a key you still get the rule-based resume checklist, the built-in interview
   question bank and the skill-gap table.

### How the match score works
`Overall = 60% skills coverage + 25% keyword overlap + 15% title relevance`

* *Skills coverage*: skills named in the job that are in your skill list.
* *Keyword overlap*: how many of the posting's 25 most frequent content words appear in your resume.
* *Title relevance*: how many words of the job title appear in your resume.

If a part cannot be computed (for example the posting names no known skills) it is skipped and the
weights are re-scaled.

---

## 4. Project structure

```
SearchRo/
├── app.py                  Streamlit UI (all pages)
├── requirements.txt  .env.example  .gitignore  pytest.ini  README.md
├── .streamlit/config.toml  Dark navy theme
├── assets/style.css        Custom CSS
├── config/settings.py      Paths, API URLs, URL templates, statuses, skills vocabulary
├── job_search/
│   ├── search.py           Remotive + Arbeitnow fetching, error handling, orchestration
│   ├── job_details.py      Normalised Job model + source converters
│   ├── filters.py          Filters, fresher detection, de-duplication, sorting
│   ├── linkedin.py         LinkedIn search-URL generator
│   └── naukri.py           Naukri search-URL generator (templates are configurable)
├── resume/                 parser.py (PDF/DOCX/TXT) · analyzer.py · matcher.py
├── ai/                     assistant.py (OpenAI wrapper) · cover_letter.py · interview.py · skill_gap.py
├── database/               db.py (SQLite CRUD) · models.py (schema)
├── tracker/applications.py Tracker logic, checklist, next-action rules, CSV export
├── utils/                  helpers.py · validators.py
├── data/                   searchro.db and searchro.log are created here at first run
└── tests/                  test_matching.py · test_database.py · test_filters.py
```

Where your data lives: `data/searchro.db` (SQLite) and `data/searchro.log`. To start fresh, stop the
app and delete `data/searchro.db`. The log never contains API keys or resume text.

### Changing the Naukri or LinkedIn link format
If either site changes its URLs, edit the templates in `.env` (see `.env.example`) — for example
`NAUKRI_URL_ROLE_LOCATION=https://www.naukri.com/{role}-jobs-in-{location}` — and restart. No code changes needed.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| `py` is not recognised | Reinstall Python and tick *Add python.exe to PATH*, or use `python -m venv venv`. |
| `py -3.13` says no such version | Run `py -0` and use a version you have, e.g. `py -3.12 -m venv venv`. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`, answer **Y**, then activate again. |
| `No module named streamlit` (or any package) | The virtual environment is not active. Run `.\venv\Scripts\Activate.ps1`, then `pip install -r requirements.txt`. |
| `No module named config` when running tests | Run `python -m pytest` from inside the `SearchRo` folder (not from a sub-folder). |
| Browser did not open | Open <http://localhost:8501> manually. If the port is busy: `python -m streamlit run app.py --server.port 8502`. |
| "Remotive/Arbeitnow is unavailable" | Check your internet connection or firewall; the other source still works. Try again in a minute. |
| "No matching jobs" | Remove filters, use a broader title, turn off *fresher-only*. These APIs have few on-site India jobs, so also use the LinkedIn/Naukri buttons. |
| Resume says "almost no text could be extracted" | The PDF is a scan/image. Export a text-based PDF or upload DOCX/TXT (OCR is not supported). |
| "PDF is password protected" | Save an unprotected copy and upload that. |
| AI buttons are greyed out | No API key found. Follow *Step 5*, then restart the app. |
| "OpenAI rejected the API key" / quota errors | Re-copy the key into `.env` without quotes or spaces, and check your OpenAI billing/usage page. |
| "The model was not found" | Set a model your account can use in `OPENAI_MODEL`. |
| Page looks unstyled | Make sure `assets/style.css` and `.streamlit/config.toml` were not deleted; hard-refresh the browser (`Ctrl+F5`). |
| `database is locked` | Close other copies of the app, then retry. |

---

## 6. Privacy and safety notes

* Resume text and your profile are stored only in the local SQLite file. If you use the optional AI
  features, the text you ask the AI to work on (resume text, job description) is sent to OpenAI.
* API keys come only from `.env` or environment variables. They are never written to logs.
* All database queries are parameterised; uploads are checked for type, size and file signature;
  spreadsheet formulas are neutralised in CSV exports; job text is HTML-escaped before display.
