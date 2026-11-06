"""Interview preparation: a built-in question bank (offline) plus optional AI-generated questions."""
from __future__ import annotations

from ai.assistant import SYSTEM_BASE, ask
from job_search.job_details import Job

# (question, short sample answer)
QUESTION_BANK: dict[str, list[tuple[str, str]]] = {
    "Python": [
        ("What is the difference between a list and a tuple?",
         "Lists are mutable, tuples are immutable. Tuples are hashable (if their items are), slightly faster, "
         "and suit fixed records; lists suit collections that change."),
        ("Explain how Python manages memory.",
         "Objects live on a private heap managed by Python. Reference counting frees objects when the count "
         "reaches zero, and a cyclic garbage collector handles reference cycles."),
        ("What are decorators and when would you use one?",
         "A decorator is a function that wraps another function to add behaviour without changing its code, "
         "e.g. logging, timing, caching, access checks. Syntax: @decorator above the function."),
        ("What is the difference between `is` and `==`?",
         "`==` compares values; `is` compares object identity (same object in memory). Use `is` for None checks."),
        ("What are generators and why are they useful?",
         "Functions using `yield` that produce values lazily, one at a time. They save memory on large or "
         "infinite sequences."),
        ("How do you handle exceptions in Python?",
         "try/except/else/finally. Catch specific exceptions, avoid bare except, use finally or context "
         "managers for cleanup, and raise custom exceptions for domain errors."),
    ],
    "SQL": [
        ("What is the difference between INNER JOIN and LEFT JOIN?",
         "INNER JOIN returns only matching rows from both tables; LEFT JOIN returns all rows from the left "
         "table and matching rows from the right (NULLs where there is no match)."),
        ("What is the difference between WHERE and HAVING?",
         "WHERE filters rows before grouping; HAVING filters groups after aggregation (e.g. HAVING COUNT(*) > 5)."),
        ("What is a primary key vs a foreign key?",
         "A primary key uniquely identifies each row. A foreign key references a primary key in another table to "
         "enforce relationships and referential integrity."),
        ("What is normalization?",
         "Organising tables to reduce redundancy and update anomalies (1NF, 2NF, 3NF). Trade-off: more joins; "
         "sometimes denormalise for read performance."),
        ("How would you find the second highest salary?",
         "SELECT MAX(salary) FROM emp WHERE salary < (SELECT MAX(salary) FROM emp); or use DENSE_RANK() "
         "OVER (ORDER BY salary DESC) and pick rank 2."),
    ],
    "Machine Learning": [
        ("What is overfitting and how do you prevent it?",
         "The model memorises training data and generalises poorly. Use more data, cross-validation, "
         "regularisation, simpler models, early stopping, or dropout."),
        ("Explain the bias–variance trade-off.",
         "High bias = underfitting (too simple); high variance = overfitting (too sensitive to training data). "
         "Good models balance both."),
        ("How do you evaluate a classification model?",
         "Accuracy, precision, recall, F1, ROC-AUC, confusion matrix. Pick metrics by cost of errors; accuracy "
         "misleads on imbalanced data."),
        ("What is cross-validation?",
         "Split data into k folds, train on k-1 and validate on the remaining one, rotate, and average the "
         "scores for a more reliable estimate."),
        ("How do you handle missing values and categorical features?",
         "Impute (mean/median/mode/model) or drop; encode categories with one-hot, ordinal or target encoding "
         "depending on the model and cardinality. Fit transformers on training data only."),
    ],
    "HR / Behavioral": [
        ("Tell me about yourself.",
         "60-90 seconds: education, key skills, one or two projects with outcomes, and why this role."),
        ("Why do you want to work for this company?",
         "Reference something specific (product, domain, tech stack) and connect it to your skills and goals."),
        ("Describe a challenge in a project and how you handled it.",
         "Use STAR: Situation, Task, Action, Result. Pick a real technical problem and focus on your actions."),
        ("What are your strengths and weaknesses?",
         "Give strengths backed by examples; for a weakness, choose a real one and explain what you are doing "
         "to improve it."),
        ("Where do you see yourself in five years?",
         "Show growth: deepen technical skills, take ownership of projects, and contribute to the team."),
    ],
    "Technical (General)": [
        ("What is the difference between a process and a thread?",
         "A process has its own memory space; threads share their process's memory and are lighter to create "
         "but need synchronisation."),
        ("Explain REST APIs.",
         "An architectural style using HTTP methods (GET, POST, PUT, DELETE) on resources identified by URLs, "
         "stateless, usually exchanging JSON."),
        ("What is Git and how do branching and merging work?",
         "A distributed version control system. Branches isolate work; merging (or rebasing) combines changes, "
         "and conflicts are resolved manually."),
        ("What is the difference between OOP concepts: inheritance, polymorphism, encapsulation, abstraction?",
         "Inheritance reuses behaviour, polymorphism lets one interface have many implementations, "
         "encapsulation hides internal state, abstraction exposes only essentials."),
        ("What happens when you type a URL into a browser?",
         "DNS lookup, TCP (and TLS) connection, HTTP request, server response, browser parses HTML/CSS/JS and "
         "renders the page."),
    ],
}
CATEGORIES = list(QUESTION_BANK)

_ML_SKILLS = {"Machine Learning", "Deep Learning", "NLP", "Scikit-learn", "TensorFlow", "PyTorch", "Pandas",
              "NumPy", "Data Analysis", "Computer Vision", "Keras"}
_SQL_SKILLS = {"SQL", "MySQL", "PostgreSQL", "SQLite", "SQL Server", "Oracle"}


def questions_for_category(category: str) -> list[tuple[str, str]]:
    return QUESTION_BANK.get(category, [])


def categories_for_job(job: Job | dict) -> list[str]:
    job = Job.from_dict(job) if isinstance(job, dict) else job
    skills = set(job.skills)
    cats = []
    if "Python" in skills:
        cats.append("Python")
    if skills & _SQL_SKILLS:
        cats.append("SQL")
    if skills & _ML_SKILLS:
        cats.append("Machine Learning")
    cats += ["Technical (General)", "HR / Behavioral"]
    return cats


def job_skill_questions(job: Job | dict, limit: int = 8) -> list[tuple[str, str]]:
    """Questions built from the skills named in the job description (offline, template based)."""
    job = Job.from_dict(job) if isinstance(job, dict) else job
    outline = ("Structure your answer: 1) define it simply, 2) give a real example from a project or "
               "course, 3) mention a trade-off or limitation. If you have not used it, say how you would learn it.")
    return [
        (f"Explain {skill} and describe where you have used it (or would use it) in a project.", outline)
        for skill in job.skills[:limit]
    ]


def generate_ai_questions(job: Job | dict | None, categories: list[str], resume_skills: list[str],
                          count: int = 8, with_answers: bool = True) -> str:
    focus = ""
    if job is not None:
        job = Job.from_dict(job) if isinstance(job, dict) else job
        focus = f"Tailor them to this job.\nJOB TITLE: {job.title}\nCOMPANY: {job.company}\n" \
                f"JOB DESCRIPTION:\n{job.description[:3500]}\n\n"
    prompt = (
        f"Generate {count} interview questions for a fresher/junior candidate covering: "
        f"{', '.join(categories) or 'technical and HR topics'}. {focus}"
        f"Candidate skills: {', '.join(resume_skills) or 'not provided'}.\n"
        + ("For each question add a concise sample answer and a one-line explanation of what the "
           "interviewer is testing." if with_answers else "Give questions only.")
        + " Format as a numbered markdown list."
    )
    return ask(prompt, system=SYSTEM_BASE, max_tokens=2200)
